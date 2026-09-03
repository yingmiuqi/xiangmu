# -*- coding: utf-8 -*-
"""v8 训练：追加 group_676 人工 ERR（含新移入的待审核图）与硬负样本继续学习。

正样本：653 / 654 / 676 三批人工 ERR
负样本：v7 负样本 + 676 硬负样本(我们多移、人工保留) + 676 images 人工保留图
        + 676 自动清扫ERR中人工保留图
去重：负样本中与正样本同名（同一张图）的剔除，避免同一张图既当好图又当坏图。

用法：python train_v8.py
训练完成后模型自动保存到 models/watermark_model.pth，清洗时自动生效。
"""

import io
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from batch_paths import BATCH_653, BATCH_654, BATCH_ACTIVE  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def collect_dir(d):
    out = []
    if not os.path.isdir(d):
        return out
    for root, _, files in os.walk(d):
        for f in files:
            if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")):
                out.append(os.path.join(root, f))
    return out


def read_list(p):
    if not p or not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def main():
    rng = random.Random(42)
    err653 = os.path.join(BATCH_653, "ERR")
    err654 = os.path.join(BATCH_654, "ERR")
    err676 = os.path.join(BATCH_ACTIVE, "ERR")

    pos = collect_dir(err653) + collect_dir(err654) + collect_dir(err676)
    pos_names = {os.path.basename(p) for p in pos}
    print("正样本(人工ERR) %d" % len(pos))

    neg = read_list(os.path.join(ROOT, "models", "v7_neg.txt"))
    neg += read_list(os.path.join(ROOT, "models", "hard_negatives.txt"))

    human_err_names = set(os.listdir(err676))
    img_dir = os.path.join(BATCH_ACTIVE, "images")
    for f in os.listdir(img_dir):
        if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human_err_names:
            neg.append(os.path.join(img_dir, f))

    auto_dir = os.path.join(BATCH_ACTIVE, "自动清扫ERR")
    for f in os.listdir(auto_dir):
        if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human_err_names:
            neg.append(os.path.join(auto_dir, f))

    before = len(neg)
    neg = [p for p in neg if os.path.basename(p) not in pos_names]
    rng.shuffle(neg)
    print("负样本 原始 %d | 剔除同名后 %d" % (before, len(neg)))

    pos_list = os.path.join(ROOT, "models", "v8_pos.txt")
    neg_list = os.path.join(ROOT, "models", "v8_neg.txt")
    with open(pos_list, "w", encoding="utf-8") as f:
        f.write("\n".join(pos))
    with open(neg_list, "w", encoding="utf-8") as f:
        f.write("\n".join(neg))

    sys.argv = ["train_v8", "--pos-list", pos_list, "--neg-list", neg_list,
                "--epochs", "5", "--max-pos", "15000", "--max-neg", "25000"]
    from train_model import main as train_main
    train_main()


if __name__ == "__main__":
    main()
