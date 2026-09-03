# -*- coding: utf-8 -*-
"""按新口径重建参照库：
只收录“按口径不移动”的漏判图（网址/促销弱/联系弱信号）；
模型漏识别的纯图形水印图不收录（靠模型训练解决）。"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_cleaner.text_rules import analyze  # noqa: E402
from image_cleaner.ref_lib import RefLib, phash  # noqa: E402


BASE = r"E:\图片审核\group_653_64039"
REPORT = os.path.join(BASE, "clean_report")


def main():
    human_dir = os.path.join(BASE, "ERR")
    ours_dir = os.path.join(BASE, "自动清扫ERR")
    human = set(f for f in os.listdir(human_dir) if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png")))
    ours = set(f for f in os.listdir(ours_dir) if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png")))
    fn = human - ours

    cache = {}
    with open(os.path.join(REPORT, "ocr_cache.jsonl"), encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            cache[o["path"]] = o["lines"]

    include = []
    excluded = 0
    for f in sorted(fn):
        lines = cache.get(os.path.join(BASE, "images", f)) or []
        if not lines:
            excluded += 1
            continue
        ta = analyze(lines)
        if ta["urls"] or ta["promo_weak"] or ta["contact_weak"]:
            include.append(os.path.join(human_dir, f))
        else:
            excluded += 1

    print("漏判总数:", len(fn), "| 收录(按口径不移动):", len(include), "| 排除(模型漏识别/无信号):", excluded)

    # 重建参照库
    lib_path = r"D:\图片清理\pythonProject1\models\ref_lib.json"
    if os.path.exists(lib_path):
        os.remove(lib_path)
    lib = RefLib()
    added = 0
    for p in include:
        h = phash(p)
        if h is not None:
            lib.add(h)
            added += 1
    lib.save()
    print("参照库重建完成: 哈希数", len(lib.hashes))


if __name__ == "__main__":
    main()
