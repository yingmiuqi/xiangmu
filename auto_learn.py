# -*- coding: utf-8 -*-
"""自动学习回路：清洗对照后自动收集“学习资料”。

用法：python auto_learn.py
默认读取 batch_paths.BATCH_ACTIVE 对应的批次，
对照 自动清扫ERR vs ERR，然后：
  1) FN（人工移动我们没移，且按口径不移动：网址/弱促销/弱联系）→ 加入参照库
  2) FP（我们多移、人工保留）→ 追加到 models/hard_negatives.txt（下一轮训练硬负样本）
  3) 人工 ERR 路径 → 追加到 models/train_pos_dirs.txt（下一轮训练正样本来源）
  4) 生成复盘报告 clean_report/复盘报告.txt
"""

import os
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_paths import BATCH_ACTIVE  # noqa: E402
from image_cleaner.text_rules import analyze  # noqa: E402
from image_cleaner.ref_lib import RefLib, phash  # noqa: E402


def main():
    batch = os.environ.get("CODEX_BATCH_PATH") or BATCH_ACTIVE
    ours_dir = os.path.join(batch, "自动清扫ERR")
    human_dir = os.path.join(batch, "ERR")
    report_dir = os.path.join(batch, "clean_report")

    ours = set(f for f in os.listdir(ours_dir) if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png")))
    human = set(f for f in os.listdir(human_dir) if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png")))
    tp = ours & human
    fp = ours - human
    fn = human - ours
    prec = len(tp) / len(ours) if ours else 0
    rec = len(tp) / len(human) if human else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0

    print("我们移动 %d | 人工移动 %d | TP %d | FP %d | FN %d" % (len(ours), len(human), len(tp), len(fp), len(fn)))
    print("精确率 %.3f | 召回率 %.3f | F1 %.3f" % (prec, rec, f1))

    # OCR 缓存（用于 FN 分类）
    cache = {}
    ocr = os.path.join(report_dir, "ocr_cache.jsonl")
    if os.path.exists(ocr):
        with open(ocr, encoding="utf-8") as f:
            for line in f:
                o = json.loads(line)
                cache[o["path"]] = o["lines"]

    # 1) FN 分类：按口径不移动（网址/弱促销/弱联系）→ 参照库；模型漏识别 → 仅统计
    lib = RefLib()
    fn_added = 0
    fn_model_miss = 0
    for f in sorted(fn):
        lines = cache.get(os.path.join(batch, "images", f)) or []
        if not lines:
            fn_model_miss += 1
            continue
        ta = analyze(lines)
        if ta["urls"] or ta["promo_weak"] or ta["contact_weak"]:
            h = phash(os.path.join(human_dir, f))
            if h is not None:
                lib.add(h)
                fn_added += 1
        else:
            fn_model_miss += 1
    lib.save()
    print("参照库：本轮新增 %d（按口径不移动的漏判）；模型漏识别 %d（靠训练解决）" % (fn_added, fn_model_miss))

    # 2) FP → 硬负样本清单
    neg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "hard_negatives.txt")
    os.makedirs(os.path.dirname(neg_file), exist_ok=True)
    with open(neg_file, "a", encoding="utf-8") as f:
        for x in sorted(fp):
            f.write(os.path.join(ours_dir, x) + "\n")
    print("硬负样本：本轮追加 %d 条" % len(fp))

    # 3) 正样本来源
    pos_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "train_pos_dirs.txt")
    with open(pos_file, "a", encoding="utf-8") as f:
        f.write(human_dir + "\n")

    # 4) 复盘报告
    lines = []
    lines.append("group_676 复盘报告")
    lines.append("我们移动 %d | 人工移动 %d | TP %d | FP %d | FN %d" % (len(ours), len(human), len(tp), len(fp), len(fn)))
    lines.append("精确率 %.1f%% | 召回率 %.1f%% | F1 %.3f" % (100 * prec, 100 * rec, f1))
    lines.append("参照库新增 %d | 硬负样本新增 %d | 模型漏识别 %d" % (fn_added, len(fp), fn_model_miss))
    lines.append("建议：FP 占比 %.1f%%，若希望更高精确率可提高模型移动阈值；" % (100 * len(fp) / len(ours) if ours else 0))
    lines.append("      若希望更高召回率，可把模型待审核(0.5~0.9)里人工确认的移动样本补入训练集。")
    with open(os.path.join(report_dir, "复盘报告.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("复盘报告已写: %s" % os.path.join(report_dir, "复盘报告.txt"))


if __name__ == "__main__":
    main()
