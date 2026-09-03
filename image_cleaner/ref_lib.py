# -*- coding: utf-8 -*-
"""参照库：感知哈希（pHash），相似度 ≥ 阈值即判定移动。

用途：盲测对照时发现“人工移动了但我们规则没抓到”的图 → 记入参照库；
以后清扫遇到与库中图片相似度 ≥95% 的图 → 直接移动。
"""

import os
import json

import numpy as np
from PIL import Image

from . import config


def phash(path, size=32):
    """DCT 感知哈希，返回 64 位整数。失败返回 None。"""
    try:
        img = Image.open(path).convert("L").resize((size, size), Image.BILINEAR)
        arr = np.asarray(img, dtype=np.float64)
        n = np.arange(size)
        basis = np.empty((size, 8))
        for u in range(8):
            cu = np.sqrt(1.0 / size) if u == 0 else np.sqrt(2.0 / size)
            basis[:, u] = cu * np.cos((2 * n + 1) * u * np.pi / (2 * size))
        dct_low = basis.T @ arr @ basis  # 8x8
        med = np.median(dct_low)
        bits = (dct_low > med).flatten()
        h = 0
        for b in bits:
            h = (h << 1) | int(b)
        return h
    except Exception:
        return None


def similarity(h1, h2):
    """64 位哈希的相似度 [0,1]。"""
    if h1 is None or h2 is None:
        return 0.0
    return 1.0 - bin(h1 ^ h2).count("1") / 64.0


class RefLib:
    def __init__(self, path=None):
        self.path = path or config.REF_LIB_PATH
        self.hashes = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.hashes = json.load(f)
            except Exception:
                self.hashes = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(list(set(self.hashes)), f)

    def add(self, hash_int):
        if hash_int is not None:
            self.hashes.append(int(hash_int))

    def best_match(self, hash_int, threshold=None):
        threshold = config.REF_SIM_THRESHOLD if threshold is None else threshold
        best = 0.0
        for h in self.hashes:
            s = similarity(hash_int, h)
            if s > best:
                best = s
        # 用户口径（2026-08-27）：相似度严格大于阈值才移动（>98%）
        return best > threshold, best
