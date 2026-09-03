# -*- coding: utf-8 -*-
"""主动学习确认集生成器：
模型训练后，从未标注图片里抽“最高置信正样本 + 临界样本”，供人工标注后再部署。

用法：python gen_confirmset.py --sample 4000 --out <目录>
"""

import os
import sys
import csv
import random
import shutil
import argparse


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from watermark_scorer import load_model, score  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=4000)
    parser.add_argument("--out", default=r"D:\图片清理\group_636_58978\人工审核\模型确认集")
    args = parser.parse_args()
    rng = random.Random(2026)

    model = load_model()
    files = []
    for d, errd in [
        (r"D:\图片清理\group_636_58978\images", r"D:\图片清理\group_636_58978\ERR"),
        (r"D:\图片清理\group_339_76503\images", r"D:\图片清理\group_339_76503\ERR"),
    ]:
        errset = set(os.listdir(errd))
        files += [os.path.join(d, f) for f in os.listdir(d)
                  if f.lower().endswith(".webp") and f not in errset]
    rng.shuffle(files)
    files = files[: args.sample]

    scored = []
    for f in files:
        try:
            p = score(model, f)
        except Exception:
            continue
        if p >= 0.5:
            scored.append((f, p))
    scored.sort(key=lambda x: -x[1])

    os.makedirs(args.out, exist_ok=True)
    rows = []
    # 最高置信的 60 个
    for f, p in scored[:60]:
        rows.append((os.path.basename(f), p, "高置信"))
        shutil.copy2(f, os.path.join(args.out, os.path.basename(f)))
    # 临界样本 40 个（0.5~0.7 之间随机）
    border = [x for x in scored if 0.5 <= x[1] <= 0.75]
    rng.shuffle(border)
    for f, p in border[:40]:
        rows.append((os.path.basename(f), round(p, 4), "临界"))
        dst = os.path.join(args.out, "border_" + os.path.basename(f))
        shutil.copy2(f, dst)

    with open(os.path.join(args.out, "确认清单.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "概率", "类型", "你的判断(移动/保留)"])
        for fn, p, kind in rows:
            w.writerow([fn, p, kind, ""])
    print("已生成确认集: %s（高置信 %d + 临界 %d）" % (args.out, len(scored[:60]), min(40, len(border))))


if __name__ == "__main__":
    main()
