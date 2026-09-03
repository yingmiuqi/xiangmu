# -*- coding: utf-8 -*-
import os

p = os.environ.get("CODEX_BATCH_PATH", "")
print("env path:", p)
print("isdir:", os.path.isdir(p))
if p:
    try:
        print("batch items:", len(os.listdir(p)))
    except Exception as e:
        print("listdir batch err:", e)
    imgs = os.path.join(p, "images")
    print("images isdir:", os.path.isdir(imgs))
    try:
        print("images count:", len(os.listdir(imgs)))
    except Exception as e:
        print("listdir images err:", e)
    try:
        with open(os.path.join(p, "index.txt"), encoding="utf-8", errors="ignore") as f:
            print("index lines:", len(f.readlines()))
    except Exception as e:
        print("index err:", e)
