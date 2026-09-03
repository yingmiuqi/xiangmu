# -*- coding: utf-8 -*-
"""训练“水印/商标/营销图”识别模型（v1）。

正样本：用户手动移入 ERR 的图（913 张，来自 group_339）
负样本：images 中随机正常图（同数量）
模型：MobileNetV3-Small 微调，二分类（bad=1 / good=0）
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime


BASE = r"D:\图片清理\group_339_76503"
REPORT = os.path.join(BASE, "clean_report")
ERR = os.path.join(BASE, "ERR")
IMAGES = os.path.join(BASE, "images")
MOVE_LOG = os.path.join(REPORT, "move_log.jsonl")
MODEL_DIR = os.path.join(r"D:\图片清理\pythonProject1", "models")
TRAIN_LOG = os.path.join(MODEL_DIR, "train.log")


def log(msg):
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(TRAIN_LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def collect_dataset(seed=42, max_pos=None, max_neg=None, extra_pos_dir=None):
    ours = set()
    with open(MOVE_LOG, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            fn = os.path.basename(obj.get("dst") or "")
            if fn:
                ours.add(fn)
    # 正样本：ERR 中用户手动放入的（不在我们的移动日志里）
    pos = [os.path.join(ERR, f) for f in os.listdir(ERR)
           if f.lower().endswith(".webp") and f not in ours]
    if extra_pos_dir and os.path.isdir(extra_pos_dir):
        extra = [os.path.join(extra_pos_dir, f) for f in os.listdir(extra_pos_dir)
                 if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        pos += extra
    # 负样本：images 中随机（不在 ERR）
    err_set = set(os.listdir(ERR))
    neg_all = [os.path.join(IMAGES, f) for f in os.listdir(IMAGES)
               if f.lower().endswith(".webp") and f not in err_set]
    rng = random.Random(seed)
    if max_pos:
        pos = rng.sample(pos, min(max_pos, len(pos)))
    if max_neg:
        neg_all = rng.sample(neg_all, min(max_neg, len(neg_all)))
    neg = rng.sample(neg_all, len(pos))
    return pos, neg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-pretrained", action="store_true", help="不使用预训练权重")
    parser.add_argument("--extra-pos-dir", default=None, help="额外正样本文件夹（如 QQ 截图提取的样例）")
    args = parser.parse_args()

    log("开始训练水印识别模型 v1")
    pos, neg = collect_dataset(seed=args.seed, extra_pos_dir=args.extra_pos_dir)
    log("正样本(用户确认坏图): %d | 负样本(正常图): %d" % (len(pos), len(neg)))

    import numpy as np
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import transforms
    from PIL import Image

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log("设备: %s" % device)

    tf = transforms.Compose([
        transforms.Resize((224, 224)),
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
    random.Random(args.seed).shuffle(idx)
    n_val = int(len(idx) * 0.15)
    val_idx, train_idx = idx[:n_val], idx[n_val:]
    train_ds = ImgDS([paths[i] for i in train_idx], [labels[i] for i in train_idx])
    val_ds = ImgDS([paths[i] for i in val_idx], [labels[i] for i in val_idx])
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False, num_workers=0)
    log("训练集 %d | 验证集 %d" % (len(train_ds), len(val_ds)))

    from torchvision import models
    if args.no_pretrained:
        model = models.mobilenet_v3_small(weights=None)
    else:
        try:
            model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
            log("已加载 ImageNet 预训练权重")
        except Exception as e:
            log("预训练权重下载失败，改为从零训练: %s" % e)
            model = models.mobilenet_v3_small(weights=None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
    model = model.to(device)

    crit = nn.CrossEntropyLoss()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
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
        # 验证
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
        log("epoch %d | loss %.3f | val TP=%d FP=%d TN=%d FN=%d | precision=%.3f recall=%.3f" % (
            ep + 1, tl / len(train_ds), tp, fp, tn, fn, prec, rec))

    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, "watermark_model.pth")
    torch.save({"state_dict": model.state_dict(), "classes": ["good", "bad"]}, model_path)
    log("模型已保存: %s" % model_path)
    log("训练完成")


if __name__ == "__main__":
    main()
