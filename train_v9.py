# -*- coding: utf-8 -*-
"""v9 训练：追加 group_723 人工 ERR（3,144 张）与 723 硬负样本继续学习。

正样本：653 / 654 / 676 / 723 四批人工 ERR（723 重复一份做域加权）
负样本：v8 负样本 + hard_negatives（含 723 人工确认的 182 张误移图）
        + 723 images 人工保留图 + 723 自动清扫ERR 中非人工 ERR 的图
去重：负样本中与正样本同名（同一张图）的剔除。

用法：python train_v9.py
训练完成后模型自动保存到 models/watermark_model.pth，清洗时自动生效。
"""

import io
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from batch_paths import BATCH_653, BATCH_654, BATCH_ACTIVE  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
BATCH_676 = r"E:\图片审核\group_676_59961"
BATCH_723 = r"E:\图片审核\group_723_67240"


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

    pos = []
    for b in (BATCH_653, BATCH_654, BATCH_676, BATCH_723):
        err_dir = os.path.join(b, "ERR")
        pos += collect_dir(err_dir)
    pos_723 = collect_dir(os.path.join(BATCH_723, "ERR"))
    pos += pos_723 * 2  # 723 重复一份：新目标域过采样，提高入选概率
    pos_names = {os.path.basename(p) for p in pos}
    print("正样本(人工ERR, 723加权) %d" % len(pos), flush=True)

    neg = read_list(os.path.join(ROOT, "models", "v8_neg.txt"))
    neg += read_list(os.path.join(ROOT, "models", "hard_negatives.txt"))

    human_names = set(x for x in os.listdir(os.path.join(BATCH_723, "ERR"))
                      if x.lower().endswith((".webp", ".png", ".jpg", ".jpeg")))
    img_dir = os.path.join(BATCH_723, "images")
    for f in os.listdir(img_dir):
        if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human_names:
            neg.append(os.path.join(img_dir, f))

    auto_dir = os.path.join(BATCH_723, "自动清扫ERR")
    for f in os.listdir(auto_dir):
        if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and f not in human_names:
            neg.append(os.path.join(auto_dir, f))

    nm_dir = os.path.join(BATCH_723, "不用移动")
    neg += collect_dir(nm_dir)

    before = len(neg)
    neg = [p for p in neg if os.path.basename(p) not in pos_names]
    rng.shuffle(neg)
    print("负样本 原始 %d | 剔除同名后 %d" % (before, len(neg)), flush=True)

    pos_list = os.path.join(ROOT, "models", "v9_pos.txt")
    neg_list = os.path.join(ROOT, "models", "v9_neg.txt")
    with open(pos_list, "w", encoding="utf-8") as f:
        f.write("\n".join(pos))
    with open(neg_list, "w", encoding="utf-8") as f:
        f.write("\n".join(neg))

    sys.argv = ["train_v9", "--pos-list", pos_list, "--neg-list", neg_list,
                "--epochs", "5", "--max-pos", "15000", "--max-neg", "25000"]
    from train_model import main as train_main
    train_main()


if __name__ == "__main__":
    main()