# -*- coding: utf-8 -*-
"""移动与报告：ERR 移动（防重名）、回退日志、CSV/JSON 报告、审核清单。"""

import os
import csv
import json
import shutil
from datetime import datetime

from . import config


def resolve_err_dir(batch_root, err_dir=None):
    """ERR 默认放在批次根目录（即目标图片文件夹的同级）。"""
    if err_dir is None:
        err_dir = os.path.join(batch_root, config.ERR_DIR_NAME)
    os.makedirs(err_dir, exist_ok=True)
    return err_dir


def move_to_err(src, err_dir, move_log_path=None):
    """移动文件到 ERR；重名自动加后缀。返回目标路径。"""
    os.makedirs(err_dir, exist_ok=True)
    base = os.path.basename(src)
    dst = os.path.join(err_dir, base)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(base)
        counter = 1
        while os.path.exists(dst):
            dst = os.path.join(err_dir, f"{stem}_{counter}{ext}")
            counter += 1
    try:
        os.replace(src, dst)
    except OSError:
        shutil.move(src, dst)
    if move_log_path:
        _append_move_log(move_log_path, src, dst)
    return dst


def _append_move_log(path, src, dst):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "src": src,
        "dst": dst,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


REPORT_COLUMNS = [
    "文件名",
    "原始路径",
    "决策",
    "规则",
    "证据",
    "得分",
    "宽",
    "高",
    "字节",
    "亮度均值",
    "亮度标准差",
    "边缘密度",
    "色彩数",
    "均匀度",
    "模糊分",
    "半透明水印分",
    "图形水印分",
    "二维码",
    "指纹",
    "水印模型分",
    "OCR文本",
    "OCR低置信中文",
    "时间",
]


def _writable_path(path):
    """文件被占用时自动换名（如 review_1.csv），避免整个流程中断。"""
    try:
        with open(path, "a", encoding="utf-8"):
            pass
        return path
    except PermissionError:
        stem, ext = os.path.splitext(path)
        i = 1
        while True:
            cand = f"{stem}_{i}{ext}"
            try:
                with open(cand, "a", encoding="utf-8"):
                    pass
                return cand
            except PermissionError:
                i += 1


def save_report(report_dir, rows, summary=None, dry_run=True, merge=False):
    """保存 report.csv / report.json / review.csv / move_plan.txt。
    merge=True 时与已有 report.json 按路径合并（断点续跑/进程被杀时不丢结果）。"""
    os.makedirs(report_dir, exist_ok=True)
    summary = summary or {}
    now = datetime.now().isoformat(timespec="seconds")

    if merge:
        json_path_prev = os.path.join(report_dir, "report.json")
        prev = {}
        if os.path.exists(json_path_prev):
            try:
                with open(json_path_prev, "r", encoding="utf-8") as f:
                    old = json.load(f)
                for r in old.get("results", []):
                    key = r.get("_path") or r.get("文件名") or r.get("原始路径")
                    if key:
                        prev[key] = r
            except Exception:
                prev = {}
        for r in rows:
            key = r.get("_path") or r.get("文件名") or r.get("原始路径")
            if key:
                prev[key] = r
        rows = list(prev.values())
        summary = dict(summary)
        summary["total"] = len(rows)
        from collections import Counter
        summary["moved"] = sum(1 for r in rows if r.get("决策") == "MOVE")
        summary["keep"] = sum(1 for r in rows if r.get("决策") == "KEEP")
        summary["review"] = sum(1 for r in rows if r.get("决策") == "REVIEW")
        summary["by_rule"] = dict(Counter(r.get("规则", "-") for r in rows if r.get("决策") == "MOVE"))

    csv_path = _writable_path(os.path.join(report_dir, "report.csv"))
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_COLUMNS)
        for r in rows:
            writer.writerow([
                r.get("文件名", ""),
                r.get("原始路径", ""),
                r.get("决策", ""),
                r.get("规则", ""),
                "; ".join(r.get("证据", [])),
                r.get("得分", ""),
                r.get("宽", ""),
                r.get("高", ""),
                r.get("字节", ""),
                r.get("亮度均值", ""),
                r.get("亮度标准差", ""),
                r.get("边缘密度", ""),
                r.get("色彩数", ""),
                r.get("均匀度", ""),
                r.get("模糊分", ""),
                r.get("半透明水印分", ""),
                r.get("图形水印分", ""),
                r.get("二维码", ""),
                r.get("指纹", ""),
                r.get("水印模型分", ""),
                r.get("OCR文本", ""),
                r.get("OCR低置信中文", ""),
                r.get("时间", ""),
            ])

    json_path = _writable_path(os.path.join(report_dir, "report.json"))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": now,
                "dry_run": dry_run,
                "summary": summary,
                "results": rows,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    review_path = _writable_path(os.path.join(report_dir, "review.csv"))
    with open(review_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["文件名", "路径", "证据"])
        for r in rows:
            if r.get("决策") == "REVIEW":
                writer.writerow([r.get("文件名"), r.get("原始路径"), "; ".join(r.get("证据", []))])

    plan_path = _writable_path(os.path.join(report_dir, "move_plan.txt"))
    with open(plan_path, "w", encoding="utf-8") as f:
        for r in rows:
            if r.get("决策") == "MOVE":
                f.write(r.get("原始路径", "") + "\n")

    return csv_path, json_path


def read_rows_jsonl(path):
    """读取实时结果流水 report_rows.jsonl → rows 列表（按路径去重，进程重启不产生重复）。"""
    raw = []
    if not path or not os.path.exists(path):
        return raw
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw.append(json.loads(line))
            except Exception:
                continue
    rows = []
    seen = {}
    for r in raw:
        key = r.get("_path") or r.get("文件名")
        if key:
            seen[key] = r
        else:
            rows.append(r)
    rows.extend(seen.values())
    return rows


def rebuild_report(report_dir, dry_run=True):
    """从 report_rows.jsonl 重建完整报告（进程被杀后恢复用，秒级）。"""
    rows = read_rows_jsonl(os.path.join(report_dir, "report_rows.jsonl"))
    from collections import Counter
    summary = {
        "total": len(rows),
        "moved": sum(1 for r in rows if r.get("决策") == "MOVE"),
        "keep": sum(1 for r in rows if r.get("决策") == "KEEP"),
        "review": sum(1 for r in rows if r.get("决策") == "REVIEW"),
        "errors": 0,
        "dry_run": dry_run,
        "by_rule": dict(Counter(r.get("规则", "-") for r in rows if r.get("决策") == "MOVE")),
    }
    save_report(report_dir, rows, summary=summary, dry_run=dry_run, merge=False)
    return summary
