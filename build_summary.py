# -*- coding: utf-8 -*-
"""从 report.json 生成整批汇总：应移动总数、规则分布、待审核清单。"""

import os
import json
import csv
from collections import Counter


BATCH = r"D:\图片清理\group_339_76503"
REPORT = os.path.join(BATCH, "clean_report")
REPORT_JSON = os.path.join(REPORT, "report.json")
SUMMARY_TXT = os.path.join(REPORT, "汇总报告.txt")
REVIEW_CSV = os.path.join(REPORT, "待审核清单.csv")


def main():
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("results", [])
    total = len(rows)
    moves = [r for r in rows if r.get("决策") == "MOVE"]
    reviews = [r for r in rows if r.get("决策") == "REVIEW"]
    keeps = total - len(moves) - len(reviews)
    by_rule = Counter(r.get("规则", "-") for r in moves)

    lines = []
    lines.append("=" * 60)
    lines.append("图片清洗整批汇总（group_339_76503）")
    lines.append("生成时间：%s" % data.get("generated_at", ""))
    lines.append("=" * 60)
    lines.append("")
    lines.append("总图片数：%d" % total)
    lines.append("建议移动（应删除）：%d 张" % len(moves))
    lines.append("待审核：%d 张" % len(reviews))
    lines.append("保留：%d 张" % keeps)
    lines.append("")
    lines.append("【规则分布（建议移动的命中原因）】")
    for rule, cnt in by_rule.most_common():
        lines.append("  %s：%d 张" % (rule, cnt))
    lines.append("")
    lines.append("【待审核清单（%d 张，详见 待审核清单.csv）】" % len(reviews))
    for r in reviews[:50]:
        lines.append("  - %s | %s" % (r.get("文件名", ""), "; ".join(r.get("证据", []))[:80]))
    if len(reviews) > 50:
        lines.append("  ... 其余 %d 张见 CSV 明细" % (len(reviews) - 50))
    lines.append("")
    lines.append("建议移动清单：move_plan.txt | 全量明细：report.csv")

    with open(SUMMARY_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(REVIEW_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "证据", "OCR文本"])
        for r in reviews:
            w.writerow([r.get("文件名", ""), "; ".join(r.get("证据", [])), r.get("OCR文本", "")[:500]])

    print("汇总已生成：%s" % SUMMARY_TXT)
    print("待审核清单：%s" % REVIEW_CSV)
    print("应移动总数：%d" % len(moves))
    for rule, cnt in by_rule.most_common():
        print("  %s：%d" % (rule, cnt))


if __name__ == "__main__":
    main()
