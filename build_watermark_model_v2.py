# -*- coding: utf-8 -*-
"""水印模型 v2 训练：用人工审核后的数据（正=确认坏图，负=确认正常图/误报样本）。"""

import os
import sys
import random
import argparse
from datetime import datetime


LOG = r"D:\图片清理\pythonProject1\models\train_v2.log"


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def collect_dirs(paths, exts=(".webp", ".png", ".jpg", ".jpeg")):
    out = []
    for d in paths:
        if not os.path.isdir(d):
            continue
        out += [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(exts)]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-neg", type=int, default=3000)
    args = parser.parse_args()

    log("开始训练水印模型 v2")
    pos = collect_dirs([
        r"D:\图片清理\group_636_58978\ERR",
        r"D:\图片清理\group_339_76503\ERR",
        r"D:\图片清理\pythonProject1\models\qq_pos",
    ])
    neg = collect_dirs([
        r"D:\图片清理\group_636_58978\人工审核\不用移动图片",
        r"D:\图片清理\group_636_58978\人工审核\模型水印候选636",
    ])
    # 补充随机正常图
    random.Random(args.seed).shuffle(pos)
    rng = random.Random(args.seed + 1)
    for d in (r"D:\图片清理\group_636_58978\images", r"D:\图片清理\group_339_76503\images"):
        files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".webp")]
        rng.shuffle(files)
        neg += files[:1200]
    neg = list(set(neg))
    rng.shuffle(neg)
    if len(neg) > args.max_neg:
        neg = neg[: args.max_neg]
    log("正样本 %d | 负样本 %d" % (len(pos), len(neg)))

    import numpy as np
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import transforms, models
    from PIL import Image

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    class ImgDS(Dataset):
        def __init__(self, paths, labels):
            self.paths = paths
            self.labels = labels

        def __len__(self):
            return len(self.paths)

        def __getitem__(self, i):
            img = Image.open(self.paths[i]).convert("RGB")
            return tf(img), self.labels[i]

    paths = pos + neg
    labels = [1] * len(pos) + [0] * len(neg)
    idx = list(range(len(paths)))
    rng.shuffle(idx)
    n_val = int(len(idx) * 0.15)
    val_idx, train_idx = idx[:n_val], idx[n_val:]
    train_ds = ImgDS([paths[i] for i in train_idx], [labels[i] for i in train_idx])
    val_ds = ImgDS([paths[i] for i in val_idx], [labels[i] for i in val_idx])
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False, num_workers=0)
    log("训练集 %d | 验证集 %d" % (len(train_ds), len(val_ds)))

    try:
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        log("已加载预训练权重")
    except Exception as e:
        model = models.mobilenet_v3_small(weights=None)
        log("预训练下载失败，从零训练: %s" % e)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
    model = model.to(device)

    crit = nn.CrossEntropyLoss()
    opt = torch.optim.Adam(model.parameters(), lr=5e-4)
    for ep in range(args.epochs):
        model.train()
        tl = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = crit(model(x), y)
            loss.backward()
            opt.step()
            tl += loss.item() * len(y)
        model.eval()
        tp = fp = tn = fn = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                p = model(x).argmax(1)
                for a, b in zip(p.tolist(), y.tolist()):
                    if a == 1 and b == 1: tp += 1
                    elif a == 1 and b == 0: fp += 1
                    elif a == 0 and b == 0: tn += 1
                    else: fn += 1
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        log("epoch %d | loss %.3f | TP=%d FP=%d TN=%d FN=%d | precision=%.3f recall=%.3f" % (
            ep + 1, tl / len(train_ds), tp, fp, tn, fn, prec, rec))

    model_path = r"D:\图片清理\pythonProject1\models\watermark_model.pth"
    torch.save({"state_dict": model.state_dict(), "classes": ["good", "bad"]}, model_path)
    log("模型已保存: %s" % model_path)
    log("训练完成")


if __name__ == "__main__":
    main()
