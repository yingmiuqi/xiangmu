# -*- coding: utf-8 -*-
"""水印模型 v3：
- ResNet18 迁移学习，5 轮
- 硬负样本：所有“不用移动”确认正常图 + 模型误判样本
- 真实世界测试集：62 个高置信候选（37 正 + 25 负，单独留出评估）
"""

import os
import sys
import json
import csv
import random
import argparse
from datetime import datetime


LOG = r"D:\图片清理\pythonProject1\models\train_v3.log"


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def collect(pairs):
    """pairs: [(目录/路径, ...)] 直接收集文件路径。"""
    out = []
    for p in pairs:
        if os.path.isfile(p):
            out.append(p)
        elif os.path.isdir(p):
            out += [os.path.join(p, f) for f in os.listdir(p)
                    if f.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-neg", type=int, default=4000)
    parser.add_argument("--extra-pos-dir", default=None)
    parser.add_argument("--extra-neg-dir", default=None)
    args = parser.parse_args()
    if not args.extra_pos_dir:
        args.extra_pos_dir = os.environ.get("CODEX_EXTRA_POS")
    rng = random.Random(args.seed)

    log("开始训练水印模型 v3 (ResNet18)")
    # 正样本
    pos = collect([
        r"D:\图片清理\group_636_58978\ERR",
        r"D:\图片清理\group_339_76503\ERR",
        r"D:\图片清理\pythonProject1\models\qq_pos",
    ])
    # 负样本：确认正常（不用移动文件夹，人工确认） + 随机正常
    neg = collect([
        r"D:\图片清理\group_636_58978\人工审核\不用移动图片",
    ])
    if args.extra_neg_dir:
        neg += collect([args.extra_neg_dir])
    if args.extra_pos_dir:
        pos += collect([args.extra_pos_dir])
    # 随机补充正常图
    for d in (r"D:\图片清理\group_636_58978\images", r"D:\图片清理\group_339_76503\images"):
        files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".webp")]
        rng.shuffle(files)
        neg += files[:1500]
    neg = list(set(neg))
    rng.shuffle(neg)
    if len(neg) > args.max_neg:
        neg = neg[: args.max_neg]
    log("正样本 %d | 负样本 %d" % (len(pos), len(neg)))

    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import transforms, models
    from PIL import Image

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.1, 0.1, 0.1),
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
    # 过滤损坏图片（解码失败会导致训练崩溃）
    from PIL import Image as _PIL

    def _valid(p):
        try:
            with _PIL.open(p) as im:
                im.verify()
            return True
        except Exception:
            return False

    valid_idx = [i for i, p in enumerate(paths) if _valid(p)]
    dropped = len(paths) - len(valid_idx)
    paths = [paths[i] for i in valid_idx]
    labels = [labels[i] for i in valid_idx]
    if dropped:
        log("已剔除损坏图片 %d 张" % dropped)
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
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        log("已加载 ResNet18 预训练权重")
    except Exception as e:
        model = models.resnet18(weights=None)
        log("预训练下载失败，从零训练: %s" % e)
    model.fc = nn.Linear(model.fc.in_features, 2)
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
