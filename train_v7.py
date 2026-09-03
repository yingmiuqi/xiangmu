# -*- coding: utf-8 -*-
"""v7 训练：追加 group_654 人工 ERR（12,509 张）继续学习。
正样本：654 人工 ERR + 653 人工 ERR；负样本：654 人工保留图 + 654 我们多移的图（人工保留）。
"""

import os
import sys
import random

from batch_paths import BATCH_654, HUMAN_ERR_654, HUMAN_ERR_653


ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    rng = random.Random(42)

    # 正样本：两个批次的人工 ERR
    pos = [os.path.join(HUMAN_ERR_654, f) for f in os.listdir(HUMAN_ERR_654)
           if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
    pos += [os.path.join(HUMAN_ERR_653, f) for f in os.listdir(HUMAN_ERR_653)
            if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]

    # 负样本：654 images（人工保留）+ 654 我们多移但人工保留的图（自动清扫ERR 减去人工 ERR）
    human654 = set(os.listdir(HUMAN_ERR_654))
    neg = [os.path.join(os.path.join(BATCH_654, "images"), f)
           for f in os.listdir(os.path.join(BATCH_654, "images"))
           if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human654]
    our_err = os.path.join(BATCH_654, "自动清扫ERR")
    neg += [os.path.join(our_err, f) for f in os.listdir(our_err)
            if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human654]
    rng.shuffle(neg)

    pos_list = os.path.join(ROOT, "models", "v7_pos.txt")
    neg_list = os.path.join(ROOT, "models", "v7_neg.txt")
    os.makedirs(os.path.dirname(pos_list), exist_ok=True)
    with open(pos_list, "w", encoding="utf-8") as f:
        f.write("\n".join(pos))
    with open(neg_list, "w", encoding="utf-8") as f:
        f.write("\n".join(neg))
    print("正样本 %d | 负样本 %d" % (len(pos), len(neg)))

    sys.argv = ["train_v7", "--pos-list", pos_list, "--neg-list", neg_list,
                "--epochs", "5", "--max-pos", "15000", "--max-neg", "25000"]
    from train_model import main as train_main
    train_main()


if __name__ == "__main__":
    main()
