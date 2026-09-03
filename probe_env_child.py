# -*- coding: utf-8 -*-
import os

p = os.environ.get("CODEX_BATCH_PATH", "")
print("env repr:", repr(p))
print("isdir:", os.path.isdir(p))
imgs = os.path.join(p, "images")
print("images isdir:", os.path.isdir(imgs))
if os.path.isdir(imgs):
    print("images count:", len(os.listdir(imgs)))
else:
    print("images count: N/A")
