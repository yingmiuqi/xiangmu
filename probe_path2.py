# -*- coding: utf-8 -*-
import os

paths = [
    "E:/图片审核/group_653_64039",
    "E:\\图片审核\\group_653_64039",
]
for p in paths:
    print("== path:", p)
    print("   isdir:", os.path.isdir(p))
    try:
        items = os.listdir(p)
        print("   items:", len(items), items)
    except Exception as e:
        print("   ERR:", e)
    imgs = os.path.join(p, "images")
    print("   images isdir:", os.path.isdir(imgs))
    if os.path.isdir(imgs):
        print("   images count:", len(os.listdir(imgs)))
