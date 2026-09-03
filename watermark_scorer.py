# -*- coding: utf-8 -*-
"""水印识别模型评分器：对图片输出“坏图(水印/商标/营销)”概率。

用法：
  python watermark_scorer.py --image <path>            # 单图
  python watermark_scorer.py --folder <dir> [--out csv]
"""

import os
import sys
import csv
import argparse

import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image


MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "watermark_model.pth")
TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def load_model(path=MODEL_PATH):
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    ckpt = torch.load(path, map_location="cpu")
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def score(model, img_path):
    img = Image.open(img_path).convert("RGB")
    x = TF(img).unsqueeze(0)
    with torch.no_grad():
        prob = torch.softmax(model(x), 1)[0, 1].item()
    return prob


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=None)
    parser.add_argument("--folder", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    model = load_model()
    if args.image:
        p = score(model, args.image)
        print("bad_prob=%.4f 判定=%s" % (p, "坏图" if p >= 0.5 else "正常"))
        return
    if args.folder:
        files = [os.path.join(args.folder, f) for f in os.listdir(args.folder)
                 if f.lower().endswith((".webp", ".jpg", ".png"))]
        rows = []
        for f in files:
            try:
                rows.append((os.path.basename(f), round(score(model, f), 4)))
            except Exception as e:
                rows.append((os.path.basename(f), str(e)))
        if args.out:
            with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["文件名", "bad_prob"])
                w.writerows(rows)
            print("已写出:", args.out)
        else:
            for fn, p in rows:
                print(fn, p)


if __name__ == "__main__":
    main()
