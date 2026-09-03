# -*- coding: utf-8 -*-
"""离线全量重判引擎 v2（分片并行 + 打分缓存）：
用 OCR 缓存 + 报告特征 + 新模型，复刻 runner 判定流水线。

用法：
  python offline_rerun.py <批次路径> --shard K/N
  （N 个进程并行，每个处理 1/N，判定结果写 offline_rerun_shard_K.jsonl）
  python offline_rerun.py <批次路径> --merge   （合并分片并出报告）
"""
import json, os, sys, time
from collections import Counter

sys.path.insert(0, r"D:\图片清理\pythonProject1")

BATCH = sys.argv[1]
RPT = os.path.join(BATCH, "clean_report")
ROWS = os.path.join(RPT, "report_rows.jsonl")
CACHE = os.path.join(RPT, "ocr_cache.jsonl")
SCORE_CACHE = os.path.join(RPT, "offline_scores.jsonl")  # path -> prob 累积缓存

args = sys.argv[2:]
MERGE = "--merge" in args
SHARD_K = SHARD_N = None
for a in args:
    if a.startswith("--shard"):
        try:
            k, n = args[args.index(a) + 1].split("/")
            SHARD_K, SHARD_N = int(k), int(n)
        except Exception:
            pass

human = set(x for x in os.listdir(os.path.join(BATCH, "ERR")) if x.lower().endswith(".webp"))

def load_scores():
    s = {}
    if os.path.exists(SCORE_CACHE):
        with open(SCORE_CACHE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    o = json.loads(line)
                    s[o["path"]] = o["prob"]
                except Exception:
                    continue
    return s

def save_scores(scores):
    with open(SCORE_CACHE, "a", encoding="utf-8") as f:
        for p, prob in scores.items():
            f.write(json.dumps({"path": p, "prob": prob}, ensure_ascii=False) + "\n")

if MERGE:
    # ---------- 合并分片 + 对照报告 ----------
    all_dec = {}
    shard_files = [x for x in os.listdir(RPT) if x.startswith("offline_rerun_shard_") and x.endswith(".jsonl")]
    for sf in shard_files:
        with open(os.path.join(RPT, sf), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    o = json.loads(line)
                    all_dec[o["_k"]] = o
                except Exception:
                    continue
    tp = fp = fn_c = 0
    fp_rules = Counter(); fn_cat = Counter(); fn_wm = Counter()
    fn_samples = []
    for fn, d in all_dec.items():
        in_h = fn in human
        if d.get("decision") == "MOVE":
            if in_h: tp += 1
            else:
                fp += 1
                fp_rules[d.get("rule") or "-"] += 1
        elif in_h:
            fn_c += 1
            wmv = d.get("wm_prob")
            if d.get("decision") == "REVIEW": fn_cat["REVIEW(审核带)"] += 1
            else: fn_cat["KEEP(完全漏判)"] += 1
            if wmv is None: fn_wm["无模型分"] += 1
            elif wmv < 0.15: fn_wm["<0.15"] += 1
            elif wmv < 0.2: fn_wm["0.15-0.2"] += 1
            else: fn_wm[">=0.2"] += 1
            if len(fn_samples) < 40:
                fn_samples.append((fn, d.get("decision"), d.get("rule") or "-", wmv, d.get("ocr") or ""))
    tot_h = tp + fn_c
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / tot_h if tot_h else 0
    f1 = 2 * p * r / (p + r) if p + r else 0
    out = ["=== 离线重判合并结果 (%s) ===" % os.path.basename(BATCH)]
    out.append("总判定 %d | 人工ERR对照 %d | TP %d | FP %d | FN %d" % (len(all_dec), tot_h, tp, fp, fn_c))
    out.append("精确率 %.3f | 召回率 %.3f | F1 %.3f" % (p, r, f1))
    out.append("\n=== FP 规则分布 ===")
    for k, v in fp_rules.most_common(14): out.append("  %-28s %d" % (k, v))
    out.append("\n=== FN 构成 ===")
    for k, v in fn_cat.most_common(): out.append("  %-20s %d" % (k, v))
    out.append("=== FN 模型分 ===")
    for k, v in fn_wm.most_common(): out.append("  %-12s %d" % (k, v))
    out.append("\n=== FN 样例 (前40) ===")
    for fn, dec, rule, wmv, ocr in fn_samples:
        out.append("--- %s | %s | wm=%s | %s" % (fn, dec, wmv, (ocr or "")[:100]))
    report_path = os.path.join(RPT, "offline_rerun_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out))
    print("\n报告已写入: %s" % report_path)
    sys.exit(0)

# ---------- 分片重判 ----------
from image_cleaner import config
from image_cleaner.decision import decide

ocr_by_path = {}
if os.path.exists(CACHE):
    with open(CACHE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                o = json.loads(line)
                ocr_by_path[o.get("path")] = o.get("lines") or []
            except Exception:
                continue
print("OCR 缓存: %d 条" % len(ocr_by_path), flush=True)

rows = {}
with open(ROWS, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: o = json.loads(line)
        except Exception: continue
        fn = o.get("文件名") or ""
        if fn: rows[fn] = o
print("报告行: %d | 分片 %d/%d" % (len(rows), SHARD_K, SHARD_N), flush=True)

if SHARD_N:
    items = list(rows.items())
    per = (len(items) + SHARD_N - 1) // SHARD_N
    items = items[SHARD_K * per: min(len(items), (SHARD_K + 1) * per)]
else:
    items = list(rows.items())

scores = load_scores()
from image_cleaner.watermark_model import WatermarkScorer
wm = WatermarkScorer()

def rebuild_feats(o):
    feats = {"path": o.get("_path") or "", "filename": o.get("文件名") or "",
             "bytes": o.get("字节") or 0}
    w, h = o.get("宽"), o.get("高")
    try:
        w = int(w) if w not in ("", None) else None
        h = int(h) if h not in ("", None) else None
    except Exception: w = h = None
    if not w or not h:
        feats["ok"] = False
        feats["error"] = "无尺寸"
        return feats
    feats["ok"] = True
    feats["w"], feats["h"] = w, h
    stats = {}
    for col, key in (("亮度标准差", "lum_std"), ("均匀度", "uniform_pct"), ("色彩数", "ncolors16")):
        v = o.get(col)
        if v not in ("", None):
            try: stats[key] = float(v) if key != "ncolors16" else int(v)
            except Exception: pass
    feats["stats"] = stats
    bv = o.get("模糊分")
    if bv not in ("", None):
        try: feats["blur_var"] = float(bv)
        except Exception: pass
    qr = o.get("二维码")
    feats["qr_texts"] = [qr] if qr else []
    return feats

new_scores = {}
t0 = time.time()
n = 0
for fn, o in items:
    n += 1
    path = o.get("_path") or ""
    feats = rebuild_feats(o)
    lines = ocr_by_path.get(path) or []
    d, ta = decide(feats, ocr_lines=lines)
    d = dict(d)
    if d["decision"] != "MOVE":
        # 文件可能已被移动（人工ERR/自动清扫ERR/不用移动），回退查找
        p_abs = path
        if not p_abs or not os.path.exists(p_abs):
            for cand in (os.path.join(BATCH, "ERR", fn),
                         os.path.join(BATCH, "自动清扫ERR", fn),
                         os.path.join(BATCH, "不用移动", fn),
                         os.path.join(BATCH, "images", fn)):
                if os.path.exists(cand):
                    p_abs = cand
                    break
        if p_abs and os.path.exists(p_abs):
            prob = scores.get(p_abs)
            if prob is None:
                prob = wm.score(p_abs)
                if prob is not None:
                    new_scores[p_abs] = prob
            if prob is not None:
                d["wm_prob"] = round(prob, 4)
                if prob >= config.WATERMARK_MODEL_MOVE_THRESHOLD:
                    d = {"decision": "MOVE", "rule": "9-水印图片(模型高置信)",
                         "evidence": [], "score": 1.0, "wm_prob": round(prob, 4)}
                elif prob >= config.WATERMARK_MODEL_REVIEW_THRESHOLD and d["decision"] == "KEEP":
                    d = {"decision": "REVIEW", "rule": "待审核",
                         "evidence": [], "score": 0.5, "wm_prob": round(prob, 4)}
    texts = []
    if d.get("text_analysis"):
        texts = [t for t in d["text_analysis"].get("texts", []) if t][:12]
    rec = {"_k": fn, "decision": d["decision"], "rule": d.get("rule") or "-",
           "wm_prob": d.get("wm_prob"), "ocr": " | ".join(texts)[:150]}
    out_shard = os.path.join(RPT, "offline_rerun_shard_%d.jsonl" % (SHARD_K or 0))
    with open(out_shard, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if n % 3000 == 0:
        print("分片 %d/%d: %d 张 (%ds)" % (SHARD_K, SHARD_N, n, time.time() - t0), flush=True)
    if len(new_scores) >= 300:
        save_scores(new_scores)
        new_scores = {}

save_scores(new_scores)
print("分片 %d/%d 完成：%d 张" % (SHARD_K, SHARD_N, n), flush=True)