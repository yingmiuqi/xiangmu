# -*- coding: utf-8 -*-
"""PaddleOCR 封装：惰性初始化、结果解析、本地缓存、C 盘占用重定向。"""

import os
import json
import shutil

from . import config


# 在导入 Paddle 之前把临时目录重定向到 D 盘（tempfile 首次调用前生效）
for _var in ("TMP", "TEMP", "TMPDIR"):
    os.environ[_var] = config.OCR_TEMP_DIR
os.makedirs(config.OCR_TEMP_DIR, exist_ok=True)
# 关闭 MKLDNN，降低推理内存占用（与既有 watermark_detector 的做法一致）
os.environ.setdefault("FLAGS_use_mkldnn", "0")


def _prepare_model_dir():
    """把已有的 ~/.paddleocr 模型拷到 D 盘目录（一次性，17MB），
    之后 PaddleOCR 从 D 盘读取，不再触碰 C 盘缓存。"""
    target = config.OCR_MODEL_DIR
    os.makedirs(target, exist_ok=True)
    src_whl = os.path.join(os.path.expanduser("~"), ".paddleocr", "whl")
    dst_whl = os.path.join(target, "whl")
    if not os.path.isdir(dst_whl) and os.path.isdir(src_whl):
        print(f"正在把 OCR 模型从 C 盘缓存复制到 {dst_whl}（一次性）...")
        shutil.copytree(src_whl, dst_whl)


def _parse_result(raw):
    """把 PaddleOCR 原始结果解析成 [(text, conf), ...]。兼容 2.x 返回格式。"""
    lines = []
    if not raw:
        return lines
    if isinstance(raw, dict):
        raw = raw.get("res", raw.get("result"))
    page = raw[0] if isinstance(raw, (list, tuple)) and raw else raw
    if not page:
        return lines
    for item in page:
        try:
            info = item[1]
            text = str(info[0]).strip()
            conf = float(info[1])
            if text:
                lines.append((text, conf))
        except Exception:
            continue
    return lines


class OCRCache:
    """按文件路径缓存 OCR 结果，避免断点重跑时重复识别。"""

    def __init__(self, path):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        obj = json.loads(line)
                        self.data[obj["path"]] = obj["lines"]
            except Exception:
                self.data = {}

    def get(self, path):
        return self.data.get(path)

    def put(self, path, lines):
        self.data[path] = lines

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for path, lines in self.data.items():
                f.write(json.dumps({"path": path, "lines": lines}, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)


class OCR:
    """惰性初始化 PaddleOCR。CPU 推理。"""

    _engine = None

    def __init__(self, cache=None):
        self.cache = cache
        self.last_error = None

    def _ensure_engine(self):
        if OCR._engine is None:
            print("正在初始化 PaddleOCR（首次较慢）...")
            _prepare_model_dir()
            from paddleocr import PaddleOCR
            # 把模型目录从 ~/.paddleocr 重定向到 D 盘
            try:
                import paddleocr.paddleocr as _po
                import paddleocr.ppocr.utils.network as _pn
                _po.BASE_DIR = config.OCR_MODEL_DIR
                _pn.MODELS_DIR = config.OCR_MODEL_DIR
            except Exception:
                pass
            OCR._engine = PaddleOCR(
                use_angle_cls=True,
                lang=config.OCR_LANG,
                show_log=False,
                use_gpu=False,
                cpu_threads=4,
                det_limit_side_len=640,
            )
        return OCR._engine

    def recognize(self, path):
        if self.cache:
            hit = self.cache.get(path)
            if hit is not None:
                return list(hit)
        try:
            engine = self._ensure_engine()
            result = engine.ocr(path, cls=True)
            lines = _parse_result(result)
        except Exception as e:
            lines = []
            self.last_error = str(e)
        if self.cache:
            self.cache.put(path, lines)
        return lines
