# -*- coding: utf-8 -*-
"""把 group_676 待审核清单(review.csv)中的图片移入人工 ERR，作为下一轮训练正样本。

用法：
  python move_review_to_err.py            # 只读核对，不移动
  python move_review_to_err.py --apply    # 执行移动
"""

import csv
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = r"E:\图片审核\group_676_59961"
REVIEW_CSV = os.path.join(BASE, "clean_report", "review.csv")
IMAGES = os.path.join(BASE, "images")
ERR = os.path.join(BASE, "ERR")
APPLY = "--apply" in sys.argv


def main():
    rows = list(csv.DictReader(open(REVIEW_CSV, encoding="utf-8-sig")))
    os.makedirs(ERR, exist_ok=True)
    err_names = set(os.listdir(ERR))
    moved = already = missing = 0
    for r in rows:
        fn = r["文件名"]
        if fn in err_names:
            already += 1
            continue
        src = os.path.join(IMAGES, fn)
        if not os.path.exists(src):
            missing += 1
            continue
        dst = os.path.join(ERR, fn)
        if APPLY:
            os.rename(src, dst)
            err_names.add(fn)
        moved += 1
    print("总计 %d | 待移入 %d | 原本已在ERR %d | 源缺失 %d | apply=%s"
          % (len(rows), moved, already, missing, APPLY))


if __name__ == "__main__":
    main()
