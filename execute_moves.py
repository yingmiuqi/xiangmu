# -*- coding: utf-8 -*-
"""按整批报告执行移动：把“建议移动”的图片移入 ERR（带日志，可回退）。
用法：python execute_moves.py
"""

import os
import sys
import csv
import json
from collections import Counter


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from image_cleaner.actions import move_to_err  # noqa: E402


BATCH = r"D:\图片清理\group_339_76503"
REPORT = os.path.join(BATCH, "clean_report")
ERR = os.path.join(BATCH, "ERR")
MOVE_LOG = os.path.join(REPORT, "move_log.jsonl")
RESULT_CSV = os.path.join(REPORT, "执行结果.csv")


def main():
    with open(os.path.join(REPORT, "report.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = [r for r in data.get("results", []) if r.get("决策") == "MOVE"]
    print("计划移动：%d 张" % len(rows))

    moved = 0
    skipped = []
    failed = []
    rules = Counter()

    os.makedirs(ERR, exist_ok=True)
    for r in rows:
        fn = r.get("文件名", "")
        src = r.get("_path") or os.path.join(os.path.join(BATCH, "images"), fn)
        if not os.path.exists(src):
            skipped.append((fn, "源文件不在 images（可能已移动/删除）"))
            continue
        try:
            dst = move_to_err(src, ERR, move_log_path=MOVE_LOG)
            moved += 1
            rules[r.get("规则", "-")] += 1
        except Exception as e:
            failed.append((fn, str(e)))

    with open(RESULT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "结果", "说明"])
        for fn, note in skipped:
            w.writerow([fn, "跳过", note])
        for fn, note in failed:
            w.writerow([fn, "失败", note])

    print("实际移动：%d 张" % moved)
    print("跳过（源文件不在）：%d 张" % len(skipped))
    print("失败：%d 张" % len(failed))
    print("--- 移动规则分布 ---")
    for rule, cnt in rules.most_common():
        print("  %s：%d" % (rule, cnt))
    print("明细：%s" % RESULT_CSV)


if __name__ == "__main__":
    main()
