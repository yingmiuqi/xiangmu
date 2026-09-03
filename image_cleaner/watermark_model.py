# -*- coding: utf-8 -*-
"""水印识别模型封装：惰性加载、单图打分（失败自动重试，避免内存压力下静默漏分）。"""

import os

from . import config


class WatermarkScorer:
    _model = None
    fail_count = 0  # 累计打分失败次数（供 runner 汇总输出）

    def __init__(self):
        self.path = config.WATERMARK_MODEL_PATH

    def _ensure(self):
        if WatermarkScorer._model is None:
            import torch
            import torch.nn as nn
            from torchvision import transforms, models
            from PIL import Image

            self._tf = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
            model = models.resnet18(weights=None)
            model.fc = nn.Linear(model.fc.in_features, 2)
            ckpt = torch.load(self.path, map_location="cpu")
            model.load_state_dict(ckpt["state_dict"])
            model.eval()
            WatermarkScorer._model = model
        return WatermarkScorer._model

    def score(self, path):
        """返回坏图概率 [0,1]；多次尝试仍失败返回 None。"""
        import time
        last = None
        for attempt in range(3):  # 内存压力/临时错误时自动重试，避免静默漏分
            try:
                import torch
                from PIL import Image
                model = self._ensure()
                img = Image.open(path).convert("RGB")
                x = self._tf(img).unsqueeze(0)
                with torch.no_grad():
                    return float(torch.softmax(model(x), 1)[0, 1].item())
            except Exception as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        WatermarkScorer.fail_count += 1
        print(f"[警告] 水印模型打分失败(3次): {path} -> {last}", flush=True)
        return None
