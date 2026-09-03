# -*- coding: utf-8 -*-
"""把图片加入参照库（相似度≥95%即移动）。
用法：
  python build_ref_lib.py --file <单图>
  python build_ref_lib.py --folder <目录>          # 目录下所有图片
  python build_ref_lib.py --list <txt路径列表>
"""

import os
import sys
import argparse


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_cleaner.ref_lib import RefLib, phash  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None)
    parser.add_argument("--folder", default=None)
    parser.add_argument("--list", default=None)
    args = parser.parse_args()

    files = []
    if args.file:
        files.append(args.file)
    if args.folder:
        files += [os.path.join(args.folder, f) for f in os.listdir(args.folder)
                  if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
    if args.list:
        with open(args.list, encoding="utf-8") as f:
            files += [line.strip() for line in f if line.strip()]

    lib = RefLib()
    added = 0
    for p in files:
        if not os.path.exists(p):
            continue
        h = phash(p)
        if h is not None:
            lib.add(h)
            added += 1
    lib.save()
    print("已加入参照库 %d 条，库总条数 %d" % (added, len(lib.hashes)))


if __name__ == "__main__":
    main()
