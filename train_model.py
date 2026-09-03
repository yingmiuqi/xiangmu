# -*- coding: utf-8 -*-
"""通用自助训练入口：用你自己的数据训练水印识别模型。

用法（在项目目录下，用 .venv 里的 python 运行）：
  python train_model.py --pos-dir <坏图文件夹> --neg-dir <正常图文件夹> --epochs 5

说明：
  - pos-dir：你确认“需要移动”的图片文件夹（如人工 ERR）
  - neg-dir：你确认“正常”的图片文件夹（如正常产品图）
  - 训练完成后模型保存到 models/watermark_model.pth，清洗时自动使用
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime


def log(msg):
    print(datetime.now().strftime("%H:%M:%S") + " | " + msg, flush=True)


def collect_dir(d, exts=(".webp", ".png", ".jpg", ".jpeg")):
    out = []
    for root, _, files in os.walk(d):
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.join(root, f))
    return out


def main():
    parser = argparse.ArgumentParser(description="水印识别模型自助训练")
    parser.add_argument("--pos-dir", default=None, help="坏图文件夹（必需，或环境变量 CODEX_POS_DIR）")
    parser.add_argument("--neg-dir", default=None, help="正常图文件夹（必需，或环境变量 CODEX_NEG_DIR）")
    parser.add_argument("--pos-list", default=None, help="坏图路径列表文件（每行一个路径）")
    parser.add_argument("--neg-list", default=None, help="正常图路径列表文件（每行一个路径）")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-neg", type=int, default=10000)
    parser.add_argument("--max-pos", type=int, default=None)
    args = parser.parse_args()

    pos_dir = args.pos_dir or os.environ.get("CODEX_POS_DIR")
    neg_dir = args.neg_dir or os.environ.get("CODEX_NEG_DIR")

    def read_list(p):
        if not p or not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and os.path.exists(l.strip())]

    pos = read_list(args.pos_list) if args.pos_list else (collect_dir(pos_dir) if pos_dir else [])
    neg = read_list(args.neg_list) if args.neg_list else (collect_dir(neg_dir) if neg_dir else [])
    if not pos:
        raise SystemExit("正样本为空：请提供有效的 --pos-dir 或 --pos-list（坏图）")
    if not neg:
        raise SystemExit("负样本为空：请提供有效的 --neg-dir 或 --neg-list（正常图）")
    if args.max_pos and len(pos) > args.max_pos:
        pos = random.Random(args.seed).sample(pos, args.max_pos)
    log("坏图 %d 张 | 正常图 %d 张" % (len(pos), len(neg)))
    if not pos or not neg:
        raise SystemExit("正/负样本不能为空")

    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import transforms, models
    from PIL import Image

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log("设备: %s" % device)

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
            try:
                img = Image.open(self.paths[i]).convert("RGB")
                return tf(img), self.labels[i]
            except Exception:
                # 文件在训练途中被移动/删除时返回占位零张量，避免整个训练崩溃
                return torch.zeros(3, 224, 224), self.labels[i]

    def _valid(p):
        try:
            with Image.open(p) as im:
                im.verify()
            return True
        except Exception:
            return False

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        pos_ok = list(ex.map(_valid, pos))
        neg_ok = list(ex.map(_valid, neg))
    paths = [p for p, ok in zip(pos, pos_ok) if ok] + [p for p, ok in zip(neg, neg_ok) if ok]
    labels = [1] * sum(pos_ok) + [0] * sum(neg_ok)
    if len(neg) > args.max_neg:
        rng = random.Random(args.seed)
        neg_idx = [i for i, l in enumerate(labels) if l == 0]
        keep = set(rng.sample(neg_idx, args.max_neg))
        paths = [p for i, p in enumerate(paths) if i in keep or labels[i] == 1]
        labels = [labels[i] for i in range(len(labels)) if i in keep or labels[i] == 1]
    log("过滤后：坏图 %d | 正常图 %d" % (sum(labels), len(labels) - sum(labels)))

    idx = list(range(len(paths)))
    random.Random(args.seed).shuffle(idx)
    n_val = max(1, int(len(idx) * 0.15))
    val_idx, train_idx = idx[:n_val], idx[n_val:]
    train_ds = ImgDS([paths[i] for i in train_idx], [labels[i] for i in train_idx])
    val_ds = ImgDS([paths[i] for i in val_idx], [labels[i] for i in val_idx])
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False, num_workers=0)
    log("训练集 %d | 验证集 %d" % (len(train_ds), len(val_ds)))

    try:
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    except Exception:
        model = models.resnet18(weights=None)
        log("预训练权重下载失败，从零训练")
    model.fc = nn.Linear(model.fc.in_features, 2)
    model = model.to(device)

    crit = nn.CrossEntropyLoss()
    opt = torch.optim.Adam(model.parameters(), lr=5e-4)

    # ---- 断点续训：每轮结束保存模型 + 轮次元数据，崩溃后从已保存轮次继续 ----
    # 断点必须绑定数据签名：数据变了（新批次/新正负样本组合）就不能复用旧断点，
    # 否则会像 v10→v11 那样 0 轮训练直接"完成"。
    out = r"D:\图片清理\pythonProject1\models\watermark_model.pth"
    meta_path = r"D:\图片清理\pythonProject1\models\train_checkpoint.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data_sig = str(abs(hash(tuple(sorted(labels)))) + len(paths))

    def _save_meta(ep, prec, rec):
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump({"done_epochs": ep, "prec": prec, "rec": rec, "data_sig": data_sig}, mf)

    start_ep = 0
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
            if meta.get("data_sig") != data_sig:
                log("数据已变化（签名不符），忽略旧断点，从头训练")
            else:
                start_ep = int(meta.get("done_epochs", 0))
                if start_ep >= args.epochs:
                    log("断点显示训练已完成（%d/%d），从头重训" % (start_ep, args.epochs))
                    start_ep = 0
                elif start_ep > 0 and os.path.exists(out):
                    ck = torch.load(out, map_location="cpu")
                    model.load_state_dict(ck["state_dict"])
                    log("断点恢复：从 epoch %d 继续（已加载之前轮次权重）" % (start_ep + 1))
        except Exception as e:
            start_ep = 0
            log("断点恢复失败，从头训练: %s" % e)

    for ep in range(start_ep, args.epochs):
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
        log("epoch %d | loss %.3f | 精确率 %.3f | 召回率 %.3f" % (
            ep + 1, tl / len(train_ds), prec, rec))
        # 每轮结束立即保存（原子写），崩溃不丢前面轮次
        tmp = out + ".tmp"
        torch.save({"state_dict": model.state_dict(), "classes": ["good", "bad"],
                    "epoch": ep + 1, "prec": prec, "rec": rec}, tmp)
        os.replace(tmp, out)
        _save_meta(ep + 1, prec, rec)
        log("已保存断点 epoch %d -> %s" % (ep + 1, out))

    torch.save({"state_dict": model.state_dict(), "classes": ["good", "bad"]}, out)
    log("模型已保存: %s" % out)
    log("训练完成")


if __name__ == "__main__":
    main()
