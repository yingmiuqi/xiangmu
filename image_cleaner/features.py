# -*- coding: utf-8 -*-
"""图像快速特征：解码、尺寸、纯色/空白、模糊、边缘、色彩数、二维码。"""

import os

import numpy as np
from PIL import Image, ImageFile

from . import config

ImageFile.LOAD_TRUNCATED_IMAGES = True


def decode(path):
    """返回 (ok, img, error)。ok=False 表示无法解码（规则4：损坏/加载失败）。"""
    try:
        img = Image.open(path)
        img.load()
        return True, img, None
    except Exception as e:
        return False, None, str(e)


def quick_stats(img):
    """灰度统计：亮度均值/标准差、边缘密度、量化色彩数、均匀像素占比。"""
    # 先缩放到最大边 512，降低内存与耗时，统计结果基本不变
    scale = 512.0 / max(img.size)
    small_img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR) if scale < 1 else img
    g = np.asarray(small_img.convert("L"), dtype=np.float32)
    if g.size == 0:
        return {"error": "empty image"}
    mean = float(g.mean())
    std = float(g.std())
    gy, gx = np.gradient(g)
    edge = float(np.sqrt(gx ** 2 + gy ** 2).mean())
    small = small_img.convert("RGB").resize((32, 32))
    try:
        ncolors = len(small.quantize(colors=16).getcolors(1024) or [])
    except Exception:
        ncolors = 16
    uniform_pct = float((np.abs(g - mean) < 6).mean())
    return {
        "lum_mean": round(mean, 2),
        "lum_std": round(std, 2),
        "edge_mean": round(edge, 3),
        "ncolors16": ncolors,
        "uniform_pct": round(uniform_pct, 4),
    }


def blur_score(img):
    """拉普拉斯方差：值越小越模糊。依赖 OpenCV，失败返回 None。"""
    try:
        import cv2

        scale = 512.0 / max(img.size)
        small = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR) if scale < 1 else img
        arr = np.asarray(small.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return float(lap.var())
    except Exception:
        return None


def detect_qr(img):
    """本地二维码检测（OpenCV）。返回检测到的文本列表。"""
    try:
        import cv2

        scale = 1024.0 / max(img.size)
        small = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR) if scale < 1 else img
        arr = np.asarray(small.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        det = cv2.QRCodeDetector()
        data, points, _ = det.detectAndDecode(gray)
        return [data] if data else []
    except Exception:
        return []


def watermark_cv_scores(img):
    """半透明水印 + 图形水印启发式（移植自 watermark_detector.py）。
    返回 (transparent_score, logo_score)，失败返回 (None, None)。"""
    try:
        import cv2

        arr = np.asarray(img.convert("RGB"))
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        if h < 40 or w < 40:
            return None, None

        # 半透明水印：高亮区域边缘密度 + 低对比度区域占比
        _, bright = cv2.threshold(gray, 210, 255, cv2.THRESH_BINARY)
        bright_edges = cv2.Canny(bright, 50, 150)
        ber = np.count_nonzero(bright_edges) / (h * w)
        gray_f = np.float32(gray)
        msq = cv2.blur(gray_f ** 2, (21, 21))
        mn = cv2.blur(gray_f, (21, 21))
        local_std = np.sqrt(np.maximum(msq - mn ** 2, 0))
        low_std_ratio = np.count_nonzero(local_std < 3.0) / (h * w)
        ts = 0.5 * (ber > 0.015) + 0.3 * (low_std_ratio > 0.5)

        # 图形水印启发式：局部边缘密度峰值
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = np.count_nonzero(edges) / (h * w)
        block_h, block_w = h // 4, w // 4
        max_local = 0.0
        susp = 0
        for y in range(0, h - block_h, block_h // 2):
            for x in range(0, w - block_w, block_w // 2):
                block = edges[y:y + block_h, x:x + block_w]
                lr = np.count_nonzero(block) / (block_h * block_w)
                max_local = max(max_local, lr)
                if lr > edge_ratio * 3 and lr > 0.05:
                    susp += 1
        lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        ls = 0.0
        if max_local > 0.15:
            ls += 0.3
        if susp >= 3:
            ls += 0.3
        if lap > 500:
            ls += 0.2
        if edge_ratio > 0.08:
            ls += 0.2
        return round(ts, 3), round(ls, 3)
    except Exception:
        return None, None


def collect_features(path):
    """一次性取回该文件的全部快检特征（未做 OCR）。"""
    feats = {
        "path": path,
        "filename": os.path.basename(path),
        "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
    }
    ok, img, err = decode(path)
    feats["ok"] = ok
    feats["error"] = err
    if not ok:
        return feats
    feats["w"], feats["h"] = img.size
    feats["stats"] = quick_stats(img)
    feats["blur_var"] = blur_score(img)
    feats["transparent_score"], feats["logo_score"] = watermark_cv_scores(img)
    if config.ENABLE_QR_DETECT:
        feats["qr_texts"] = detect_qr(img)
    else:
        feats["qr_texts"] = []
    return feats
