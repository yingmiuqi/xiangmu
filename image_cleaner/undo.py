# -*- coding: utf-8 -*-
"""回退工具：按 move_log.jsonl 把移入 ERR 的文件移回原位。

用法：
  python -m image_cleaner.undo --log D:\\图片清理\\group_X\\clean_report\\move_log.jsonl
"""

import os
import json
import shutil
import argparse


def main():
    parser = argparse.ArgumentParser(description="回退 ERR 移动")
    parser.add_argument("--log", required=True, help="move_log.jsonl 路径")
    parser.add_argument("--dry-run", action="store_true", help="只列出将回退的文件")
    args = parser.parse_args()

    if not os.path.exists(args.log):
        raise SystemExit(f"日志不存在: {args.log}")
    entries = []
    with open(args.log, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    restored = 0
    skipped = 0
    print(f"共 {len(entries)} 条移动记录，按逆序回退")
    for e in reversed(entries):
        src, dst = e["src"], e["dst"]
        if not os.path.exists(dst):
            print(f"  [跳过] 目标不存在: {dst}")
            skipped += 1
            continue
        if os.path.exists(src):
            print(f"  [跳过] 原位已有文件: {src}")
            skipped += 1
            continue
        print(f"  [回退] {dst} → {src}")
        if not args.dry_run:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
            restored += 1

    if args.dry_run:
        print("\n[dry-run] 未执行回退")
    else:
        print(f"\n回退完成: {restored}，跳过: {skipped}")


if __name__ == "__main__":
    main()
