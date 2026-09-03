# -*- coding: utf-8 -*-
"""与参考 ERR 对比评估（用于调优）。

用法：
  python -m image_cleaner.evaluate --report <report.csv> --reference <ERR目录>

说明：reference 目录里的文件名视为“应移动”的真值标签（由参考工具/人工产生）。
统计口径：
  TP  我们判定移动，参考也判定移动
  FP  我们判定移动，参考未判定（误删风险，需要重点看）
  FN  参考判定移动，我们未判定（漏删，里程碑2 文本规则补齐后下降）
"""

import os
import csv
import json
import argparse


def load_reference(ref_dirs):
    names = set()
    for d in ref_dirs:
        for root, _, files in os.walk(d):
            for f in files:
                names.add(f.lower())
    return names


def load_report(path):
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("results", [])
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="本脚本生成的 report.csv 或 report.json")
    parser.add_argument("--reference", nargs="+", required=True, help="参考 ERR 目录（可多个）")
    parser.add_argument("--out", default=None, help="不一致明细输出路径（默认与 report 同目录）")
    args = parser.parse_args()

    ref = load_reference(args.reference)
    rows = load_report(args.report)
    print(f"参考 ERR 文件名: {len(ref)} | 报告行数: {len(rows)}")

    tp = fp = fn = tn = 0
    mismatches = []
    for r in rows:
        fname = r.get("文件名", "").lower()
        in_ref = fname in ref
        ours = r.get("决策", "") == "MOVE"
        if ours and in_ref:
            tp += 1
        elif ours and not in_ref:
            fp += 1
            mismatches.append((fname, "我们移动/参考保留", r.get("规则", "")))
        elif not ours and in_ref:
            fn += 1
            mismatches.append((fname, "参考移动/我们保留", r.get("规则", "")))
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    agreement = (tp + tn) / len(rows) if rows else 0.0

    print(f"\nTP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"精确率(移动的图里有多少与参考一致): {precision:.1%}")
    print(f"召回率(参考的图里我们抓住多少):     {recall:.1%}")
    print(f"F1: {f1:.3f} | 整体一致率: {agreement:.1%}")

    if mismatches:
        out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.report)), "mismatch_report.csv")
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["文件名", "类型", "我们的规则"])
            w.writerows(mismatches)
        print(f"\n不一致明细（{len(mismatches)} 条）: {out}")
        fp_list = [m for m in mismatches if m[1] == "我们移动/参考保留"]
        fn_list = [m for m in mismatches if m[1] == "参考移动/我们保留"]
        print(f"  误删风险(我们移动/参考保留): {len(fp_list)}")
        print(f"  漏删(参考移动/我们保留): {len(fn_list)}")


if __name__ == "__main__":
    main()
