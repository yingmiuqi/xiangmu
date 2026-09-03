# -*- coding: utf-8 -*-
"""用已训练的水印模型扫描整批图片，输出高概率水印/商标候选。
支持断点续跑（结果流水 scan_scores.jsonl）。"""

import os
import sys
import json
import shutil
import csv
import argparse
from datetime import datetime


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_cleaner.watermark_model import WatermarkScorer  # noqa: E402


BASE = r"D:\图片清理\group_339_76503"
IMAGES = os.path.join(BASE, "images")
REPORT = os.path.join(BASE, "clean_report")
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
LOG = os.path.join(MODEL_DIR, "scan.log")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=os.path.join(MODEL_DIR, "scan_scores_v2.jsonl"))
    parser.add_argument("--out-csv", default=os.path.join(REPORT, "水印扫描结果_v2.csv"))
    parser.add_argument("--cand-dir", default=os.path.join(BASE, "人工审核", "模型水印候选_v2"))
    args = parser.parse_args()
    CACHE = args.cache
    OUT_CSV = args.out_csv
    CAND_DIR = args.cand_dir

    os.makedirs(MODEL_DIR, exist_ok=True)
    log("开始扫描：%s" % IMAGES)
    scorer = WatermarkScorer()
    log("模型加载完成")

    scores = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                scores[obj["path"]] = obj["prob"]
        log("已有缓存 %d 条，续跑" % len(scores))

    files = [os.path.join(IMAGES, f) for f in sorted(os.listdir(IMAGES))
             if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))]
    todo = [p for p in files if p not in scores]
    log("待扫描 %d 张" % len(todo))

    done = 0
    with open(CACHE, "a", encoding="utf-8") as f:
        for i, p in enumerate(todo, 1):
            prob = scorer.score(p)
            if prob is None:
                prob = -1
            scores[p] = prob
            f.write(json.dumps({"path": p, "prob": prob}) + "\n")
            done += 1
            if done % 500 == 0:
                f.flush()
                log("进度 %d / %d" % (done, len(todo)))

    hi = [(p, s) for p, s in scores.items() if s >= 0.6]
    hi.sort(key=lambda x: -x[1])
    log("扫描完成：共 %d 张；prob>=0.6: %d | >=0.7: %d | >=0.8: %d | >=0.9: %d" % (
        len(scores),
        sum(1 for _, s in hi if s >= 0.6),
        sum(1 for _, s in hi if s >= 0.7),
        sum(1 for _, s in hi if s >= 0.8),
        sum(1 for _, s in hi if s >= 0.9)))

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "坏图概率"])
        for p, s in hi:
            w.writerow([os.path.basename(p), round(s, 4)])
    log("结果已写出: %s（%d 条）" % (OUT_CSV, len(hi)))

    os.makedirs(CAND_DIR, exist_ok=True)
    copied = 0
    for p, s in hi:
        if s < 0.7 or copied >= 200:
            break
        dst = os.path.join(CAND_DIR, os.path.basename(p))
        if not os.path.exists(dst):
            shutil.copy2(p, dst)
            copied += 1
    log("已复制 %d 张候选到 %s" % (copied, CAND_DIR))
    log("全部完成")


if __name__ == "__main__":
    main()
