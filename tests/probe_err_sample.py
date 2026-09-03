# -*- coding: utf-8 -*-
"""在参考 ERR 目录抽样跑完整分析，估算召回率（只读，不写任何文件到 ERR）。

用法：python tests/probe_err_sample.py <ERR目录> [样本数] [OCR缓存jsonl]
"""

import os
import sys
import random
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_cleaner.features import collect_features
from image_cleaner.ocr import OCR, OCRCache
from image_cleaner.decision import decide


def main():
    err_dir = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    cache_path = sys.argv[3] if len(sys.argv) > 3 else None
    files = [f for f in os.listdir(err_dir) if f.lower().endswith(".webp")]
    random.seed(11)
    sample = random.sample(files, min(n, len(files)))
    print(f"样本: {len(sample)} 张（来自 {err_dir}）")

    cache = OCRCache(cache_path) if cache_path else None
    ocr = OCR(cache=cache)
    dec_c = Counter()
    rule_c = Counter()
    missed = []
    for i, fn in enumerate(sample):
        path = os.path.join(err_dir, fn)
        feats = collect_features(path)
        dec, ta = decide(feats)
        if dec["decision"] != "MOVE":
            lines = ocr.recognize(path)
            dec, ta = decide(feats, ocr_lines=lines)
        dec_c[dec["decision"]] += 1
        rule_c[dec.get("rule", "-")] += 1
        if dec["decision"] == "KEEP":
            texts = [t for t, _ in lines][:8]
            missed.append((fn, texts))
        if cache and (i + 1) % 50 == 0:
            cache.save()

    print("决策分布:", dict(dec_c))
    print("移动原因:", dict(rule_c))
    print(f"召回率(样本中被判定移动的比例): {dec_c['MOVE'] / len(sample):.1%}")
    print("\n漏掉的样例（KEEP 且其 OCR 文本）：")
    for fn, texts in missed[:15]:
        print(" -", fn, "|", " / ".join(texts)[:180])
    if cache:
        cache.save()


if __name__ == "__main__":
    main()
