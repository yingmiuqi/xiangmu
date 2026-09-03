# -*- coding: utf-8 -*-
"""CLI 主入口：扫描 → 快检 → OCR → 决策 → 指纹去重 → （dry-run 报告 / 移动+报告）。

用法示例：
  python -m image_cleaner.runner --input D:\\图片清理\\group_636_58978
  python -m image_cleaner.runner --input D:\\图片清理\\group_636_58978 --limit 500
  python -m image_cleaner.runner --input D:\\图片清理\\group_636_58978 --move
"""

import os
import sys
import argparse
import csv
import random
import json
from collections import Counter
from datetime import datetime

from . import config
from .inventory import collect_images, load_index, Checkpoint
from .features import collect_features
from .decision import decide
from .actions import resolve_err_dir, move_to_err, save_report, read_rows_jsonl, rebuild_report
from .ocr import OCRCache
from .dedup import Deduper


def _use_progress_bar():
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def resolve_targets(input_path):
    """把输入目录解析为 (目标图片文件夹, 批次根目录)。

    规则：
      - 传入批次根目录（含 images 子目录）→ 目标 = 根/images，ERR 在根/ERR
      - 传入 images 目录本身 → 目标 = images，ERR 在上级/ERR
      - 传入普通图片目录 → 目标 = 该目录，ERR 在上级/ERR
    """
    abs_in = os.path.abspath(input_path)
    if not os.path.isdir(abs_in):
        raise SystemExit(f"输入目录不存在: {input_path}")
    base = os.path.basename(abs_in).lower()
    if base not in ("images", "pass") and os.path.isdir(os.path.join(abs_in, "images")):
        return os.path.join(abs_in, "images"), abs_in
    if base in ("images", "pass"):
        return abs_in, os.path.dirname(abs_in)
    return abs_in, abs_in


def build_row(feats, decision, index_map, now, md5_hex=None):
    stats = feats.get("stats") or {}
    text_analysis = decision.get("text_analysis") or {}
    return {
        "文件名": feats.get("filename", ""),
        "原始路径": index_map.get(feats.get("filename", ""), feats.get("path", "")),
        "决策": decision["decision"],
        "规则": decision.get("rule", ""),
        "证据": decision.get("evidence", []),
        "得分": decision.get("score", 0),
        "宽": feats.get("w", ""),
        "高": feats.get("h", ""),
        "字节": feats.get("bytes", ""),
        "亮度均值": stats.get("lum_mean", ""),
        "亮度标准差": stats.get("lum_std", ""),
        "边缘密度": stats.get("edge_mean", ""),
        "色彩数": stats.get("ncolors16", ""),
        "均匀度": stats.get("uniform_pct", ""),
        "模糊分": feats.get("blur_var", ""),
        "半透明水印分": feats.get("transparent_score", ""),
        "图形水印分": feats.get("logo_score", ""),
        "二维码": ";".join(feats.get("qr_texts", []))[:200],
        "指纹": (md5_hex or "")[:16],
        "水印模型分": decision.get("wm_prob", ""),
        "OCR文本": " | ".join(text_analysis.get("texts", []))[:800],
        "OCR低置信中文": "是" if text_analysis.get("low_conf_chinese") else "",
        "时间": now,
        "_path": feats.get("path", ""),
        "_md5": md5_hex,
        "_wm": decision.get("wm_prob"),
    }


def load_user_decisions(report_dir):
    """读取用户的审核结果（审核结果.csv），返回 {文件名: MOVE/KEEP}。
    用户已拍板的图片不再由规则重复判定。"""
    path = os.path.join(report_dir, config.USER_DECISIONS_FILE)
    if not os.path.exists(path):
        return {}
    out = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                fn = (r.get("文件名") or "").strip()
                dec = (r.get("用户决定") or "").strip()
                if not fn or not dec:
                    continue
                if "移动" in dec:
                    out[fn] = "MOVE"
                elif "保留" in dec:
                    out[fn] = "KEEP"
    except Exception as e:
        print(f"[警告] 读取审核结果失败: {e}")
    return out


def _move_phase(rows, err_dir, move_log_path, dry_run):
    """把判定 MOVE 的行真正移入 ERR（跳过已不在原位的文件）。返回移动数。"""
    moved = 0
    skipped_missing = 0
    for r in rows:
        if r.get("决策") != "MOVE":
            continue
        src = r.get("_path") or ""
        if not src or not os.path.exists(src):
            skipped_missing += 1
            continue
        if dry_run:
            moved += 1
            continue
        try:
            move_to_err(src, err_dir, move_log_path=move_log_path)
            moved += 1
        except Exception as e:
            print(f"[错误] 移动失败 {src}: {e}", flush=True)
    return moved, skipped_missing


def run(input_path, dry_run=True, err_dir=None, limit=None, checkpoint_path=None,
        index_path=None, move_log_path=None, enable_qr=True, enable_ocr=True,
        force=False, no_dedup=False, sample_seed=None, max_per_run=None, enable_wm=True):
    target_dir, batch_root = resolve_targets(input_path)
    print(f"目标图片目录: {target_dir}", flush=True)
    print(f"批次根目录:   {batch_root}", flush=True)

    err_dir = resolve_err_dir(batch_root, err_dir)
    report_dir = os.path.join(batch_root, config.REPORT_DIR_NAME)
    print(f"ERR 目录:     {err_dir}", flush=True)
    print(f"报告目录:     {report_dir}", flush=True)

    if checkpoint_path is None:
        checkpoint_path = os.path.join(report_dir, "checkpoint.json")
    if move_log_path is None:
        move_log_path = os.path.join(report_dir, "move_log.jsonl")
    ocr_cache_path = os.path.join(report_dir, "ocr_cache.jsonl")
    rows_jsonl_path = os.path.join(report_dir, "report_rows.jsonl")

    index_map = load_index(index_path or os.path.join(batch_root, "index.txt"))
    print(f"index.txt 映射: {len(index_map)} 条", flush=True)

    if not enable_qr:
        config.ENABLE_QR_DETECT = False

    image_files = collect_images(target_dir)
    if limit:
        if sample_seed is not None:
            rng = random.Random(sample_seed)
            image_files = rng.sample(image_files, min(limit, len(image_files)))
        else:
            image_files = image_files[:limit]
    print(f"待处理图片: {len(image_files)} 张", flush=True)

    if not image_files:
        print("未找到图片", flush=True)
        return

    ckpt = Checkpoint(checkpoint_path)
    if force:
        ckpt.done = set()
    if ckpt.done:
        print(f"断点已有 {len(ckpt.done)} 条记录，续跑", flush=True)

    # ---- 阶段 1：分析（快检 + OCR + 决策），不做任何移动 ----
    rows = []
    errors = 0
    now = datetime.now().isoformat(timespec="seconds")
    ocr_engine = None
    ocr_cache = OCRCache(ocr_cache_path)
    ocr_count = 0
    deduper = Deduper()
    rows_jsonl = open(rows_jsonl_path, "a", encoding="utf-8")
    wm = None
    ref_lib = None

    # 预热顺序必须【先 torch 后 paddle】：PaddleOCR 先加载会污染 DLL 搜索路径，
    # 导致 torch 的 shm.dll 加载失败（WinError 127），水印模型打分将全部静默失败。
    if enable_wm:
        from .watermark_model import WatermarkScorer
        wm = WatermarkScorer()
        try:
            wm._ensure()  # 提前触发 torch 加载
        except Exception as e:
            print(f"[警告] 水印模型预热失败: {e}", flush=True)
            wm = None
    if enable_ocr:
        # 只导入模块，不初始化引擎（仍惰性加载，但确保 torch 已先加载完）
        from .ocr import OCR as _OCR_module  # noqa: F401

    iterator = image_files
    if _use_progress_bar():
        from tqdm import tqdm
        iterator = tqdm(image_files, desc="分析", unit="张")

    for path in iterator:
        if ckpt.is_done(path):
            continue
        try:
            with open(os.path.join(report_dir, "current.txt"), "w", encoding="utf-8") as cf:
                cf.write(path)
        except Exception:
            pass
        try:
            feats = collect_features(path)
            decision, text_analysis = decide(feats)
            if enable_ocr and decision["decision"] != "MOVE":
                if ocr_engine is None:
                    from .ocr import OCR
                    ocr_engine = OCR(cache=ocr_cache)
                lines = ocr_engine.recognize(path)
                decision, text_analysis = decide(feats, ocr_lines=lines)
                ocr_count += 1
                if ocr_count % 50 == 0:
                    ocr_cache.save()
            decision = dict(decision)
            decision["text_analysis"] = text_analysis
            if enable_wm and decision["decision"] != "MOVE":
                if wm is None:
                    from .watermark_model import WatermarkScorer
                    wm = WatermarkScorer()
                prob = wm.score(path)
                if prob is not None:
                    decision["wm_prob"] = round(prob, 4)
                    if prob >= config.WATERMARK_MODEL_MOVE_THRESHOLD:
                        decision = {"decision": "MOVE",
                                    "rule": "9-水印图片(模型高置信)",
                                    "evidence": [f"水印模型高置信(概率{prob:.2f})"],
                                    "score": 1.0, "wm_prob": round(prob, 4),
                                    "text_analysis": text_analysis}
                    elif prob >= config.WATERMARK_MODEL_REVIEW_THRESHOLD:
                        ev = f"水印模型候选(概率{prob:.2f})"
                        if decision["decision"] == "KEEP":
                            decision = {"decision": "REVIEW", "rule": "待审核",
                                        "evidence": [ev], "score": 0.5, "wm_prob": round(prob, 4),
                                        "text_analysis": text_analysis}
                        else:
                            decision["evidence"] = list(decision.get("evidence", [])) + [ev]
            else:
                decision.setdefault("wm_prob", "")
            if config.ENABLE_REF_LIB and decision["decision"] != "MOVE":
                if ref_lib is None:
                    from .ref_lib import RefLib, phash
                    ref_lib = RefLib()
                ph = phash(path)
                if ph is not None:
                    hit, sim = ref_lib.best_match(ph)
                    if hit:
                        decision = {"decision": "MOVE",
                                    "rule": "参照库相似图(>=95%)",
                                    "evidence": [f"与参照库相似度{sim:.2%}"],
                                    "score": 1.0, "text_analysis": text_analysis}
        except Exception as e:
            errors += 1
            feats = {"path": path, "filename": os.path.basename(path),
                     "bytes": 0, "ok": False, "error": str(e)}
            decision = {"decision": "MOVE", "rule": "4-无效图片(未捕获异常)",
                        "evidence": [f"异常: {e}"], "score": 1.0, "text_analysis": None}

        md5_hex = None
        if not no_dedup:
            md5_hex = deduper.fingerprint(path)
        rows.append(build_row(feats, decision, index_map, now, md5_hex))
        rows_jsonl.write(json.dumps(rows[-1], ensure_ascii=False) + "\n")
        if len(rows) % 100 == 0:
            rows_jsonl.flush()
        # 立即移动（不等轮换/结束），被杀进程也不丢已判定移动的图
        if not dry_run and rows[-1]["决策"] == "MOVE":
            try:
                move_to_err(path, err_dir, move_log_path=move_log_path)
            except Exception as e:
                errors += 1
                print(f"[错误] 移动失败 {path}: {e}", flush=True)
        ckpt.mark(path)
        if len(rows) % 500 == 0:
            ckpt.save()
            moved_so_far = sum(1 for r in rows if r["决策"] == "MOVE")
            review_so_far = sum(1 for r in rows if r["决策"] == "REVIEW")
            print(
                f"[进度] {len(rows)}/{len(image_files)} | 移动 {moved_so_far} | 审核 {review_so_far} | {datetime.now().strftime('%H:%M:%S')}",
                flush=True,
            )
        if max_per_run and len(rows) >= max_per_run:
            rows_jsonl.flush()
            rows_jsonl.close()
            ckpt.save()
            if ocr_engine is not None:
                ocr_cache.save()
            m, s = _move_phase(rows, err_dir, move_log_path, dry_run)
            print(
                f"[轮换] 本进程已处理 {len(rows)} 张，移动 {m}（跳过 {s}），退出释放内存",
                flush=True,
            )
            sys.exit(77)

    ckpt.save()
    if ocr_engine is not None:
        ocr_cache.save()
    rows_jsonl.flush()
    rows_jsonl.close()

    # 从流水线读取全部结果，生成正式报告（进程被杀也不丢数据）
    rows = read_rows_jsonl(rows_jsonl_path)

    # ---- 阶段 2：指纹去重联动 ----
    dedup_changed = 0
    if not no_dedup:
        dedup_changed = Deduper.propagate(rows)

    # ---- 套用用户审核结论（用户决定优先于规则） ----
    user_dec = load_user_decisions(report_dir)
    user_override = 0
    if user_dec:
        for r in rows:
            want = user_dec.get(r.get("文件名", ""))
            if want and r["决策"] != want:
                r["决策"] = want
                r["规则"] = "用户审核确认(移动)" if want == "MOVE" else "用户审核确认(保留)"
                r["证据"] = ["套用用户审核结论"]
                r["得分"] = 1.0 if want == "MOVE" else 0.0
                user_override += 1

    # ---- 阶段 3：执行移动（仅非 dry-run） ----
    moved, skipped_missing = _move_phase(rows, err_dir, move_log_path, dry_run)

    summary = {
        "total": len(rows),
        "moved": moved,
        "keep": sum(1 for r in rows if r["决策"] == "KEEP"),
        "review": sum(1 for r in rows if r["决策"] == "REVIEW"),
        "errors": errors,
        "ocr_count": ocr_count,
        "dedup_changed": dedup_changed,
        "user_override": user_override,
        "dry_run": dry_run,
    }
    by_rule = Counter(r["规则"] for r in rows if r["决策"] == "MOVE")
    summary["by_rule"] = dict(by_rule)
    save_report(report_dir, rows, summary=summary, dry_run=dry_run, merge=False)

    print("\n===== 汇总 =====")
    print(f"处理: {summary['total']} 张 | 移动: {summary['moved']} | 保留: {summary['keep']} | 审核: {summary['review']} | 异常: {summary['errors']}")
    for rule, cnt in by_rule.most_common():
        print(f"  {rule}: {cnt}")
    if dedup_changed:
        print(f"指纹去重联动改判: {dedup_changed} 张")
    if user_override:
        print(f"套用用户审核结论: {user_override} 张")
    if dry_run:
        print(f"\n[dry-run] 未移动任何文件；待移动清单: {os.path.join(report_dir, 'move_plan.txt')}")
    else:
        print(f"\n已移动文件至: {err_dir}（回退: python -m image_cleaner.undo --log {move_log_path}）")
    print(f"报告: {os.path.join(report_dir, 'report.csv')}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="图片数据清洗")
    parser.add_argument("--input", default=None, help="批次根目录或图片目录（缺省用环境变量 CODEX_BATCH_PATH）")
    parser.add_argument("--rebuild", action="store_true", help="仅从 report_rows.jsonl 重建报告")
    parser.add_argument("--move", action="store_true", help="执行移动（默认 dry-run 只出报告）")
    parser.add_argument("--err-dir", default=None, help="自定义 ERR 目录（默认在批次根目录下）")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张（调试用）")
    parser.add_argument("--index", default=None, help="index.txt 路径（默认自动找批次根目录下的 index.txt）")
    parser.add_argument("--no-qr", action="store_true", help="跳过二维码检测（提速）")
    parser.add_argument("--no-ocr", action="store_true", help="跳过 OCR 文本规则（只做快检）")
    parser.add_argument("--no-wm", action="store_true", help="跳过水印识别模型打分")
    parser.add_argument("--no-dedup", action="store_true", help="关闭指纹去重联动")
    parser.add_argument("--force", action="store_true", help="忽略断点，重新处理全部")
    parser.add_argument("--sample-seed", type=int, default=None, help="随机抽样种子（与 --limit 配合，可复现）")
    parser.add_argument("--max-per-run", type=int, default=None, help="单进程最多处理 N 张后自动退出（配合看门狗轮换，控制内存）")
    args = parser.parse_args(argv)
    if not args.input:
        args.input = os.environ.get("CODEX_BATCH_PATH")
    if not args.input:
        raise SystemExit("未指定 --input，且环境变量 CODEX_BATCH_PATH 为空")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if args.rebuild:
        target_dir, batch_root = resolve_targets(args.input)
        report_dir = os.path.join(batch_root, config.REPORT_DIR_NAME)
        summary = rebuild_report(report_dir, dry_run=True)
        print("重建完成:", summary)
        return

    run(
        args.input,
        dry_run=not args.move,
        err_dir=args.err_dir,
        limit=args.limit,
        index_path=args.index,
        enable_qr=not args.no_qr,
        enable_ocr=not args.no_ocr,
        force=args.force,
        no_dedup=args.no_dedup,
        sample_seed=args.sample_seed,
        max_per_run=args.max_per_run,
        enable_wm=not args.no_wm,
    )


if __name__ == "__main__":
    main()
