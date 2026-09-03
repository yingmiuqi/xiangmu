import os
os.environ["FLAGS_use_mkldnn"] = "0"

import cv2
import numpy as np
from paddleocr import PaddleOCR
from PIL import Image
import json
import csv
import argparse
from tqdm import tqdm
import warnings
import hashlib
from datetime import datetime

warnings.filterwarnings("ignore")


class WatermarkDetector:
    """通用图片水印检测器，支持文字水印和图形水印检测。"""

    # 默认水印关键词库（中/英文）
    DEFAULT_KEYWORDS = [
        # 中文常见水印
        "样张", "样图", "水印", "版权", "原创", "禁止转载", "未经允许",
        "盗图必究", "摄影", "供图", "视觉中国", "图虫", "站酷",
        "lofter", "小红书", "微博", "抖音", "快手", " bilibili",
        "知乎", "网易", "腾讯", "新浪", "搜狐", "图虫创意",
        "东方ic", "全景", "摄图网", "千图网", "昵图网", "包图网",
        # 英文常见水印
        "sample", "watermark", "copyright", "gettyimages", "shutterstock",
        "adobe stock", "istock", "dreamstime", "rf", "alamy",
        "depositphotos", "logo", "draft", "preview", "proof",
        "bigstock", "canstock", "fotolia", "pond5", "123rf",
        "pixabay", "unsplash", "pexels", "freepik",
        # 常见域名特征
        "www.", ".com", ".cn", ".net", ".org", ".cc",
    ]

    def __init__(self,
                 ocr_lang="ch",
                 watermark_keywords=None,
                 logo_template_path=None,
                 text_threshold=0.7,
                 logo_threshold=0.6,
                 enable_heuristic_logo=True):
        """
        初始化检测器。

        Args:
            ocr_lang: OCR 语言，'ch'为中文，'en'为英文
            watermark_keywords: 自定义水印关键词列表
            logo_template_path: 图形水印模板路径（用于模板匹配）
            text_threshold: 文字水印判定阈值
            logo_threshold: 图形水印判定阈值
            enable_heuristic_logo: 是否启用启发式图形水印检测（无模板时）
        """
        print("正在初始化 OCR 引擎（首次使用会自动下载模型）...")
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=ocr_lang,
            show_log=False,
            use_gpu=False
        )
        self.keywords = [k.lower() for k in (watermark_keywords or self.DEFAULT_KEYWORDS)]
        self.text_threshold = text_threshold
        self.logo_threshold = logo_threshold
        self.enable_heuristic_logo = enable_heuristic_logo

        # 加载图形水印模板
        self.logo_template = None
        self.template_size = None
        if logo_template_path and os.path.exists(logo_template_path):
            tmpl = cv2.imread(logo_template_path, cv2.IMREAD_GRAYSCALE)
            if tmpl is not None:
                self.logo_template = tmpl
                self.template_size = tmpl.shape[::-1]
                print(f"已加载图形水印模板: {logo_template_path}, 尺寸: {self.template_size}")
            else:
                print(f"警告: 无法读取模板图片 {logo_template_path}")

    def _check_text_keywords(self, text_lines):
        """OCR 结果与关键词匹配。"""
        if not text_lines or text_lines[0] is None:
            return False, [], []

        matched_keywords = []
        matched_texts = []

        for line in text_lines:
            for word_info in line:
                text = word_info[1][0].lower().strip()
                confidence = word_info[1][1]
                for kw in self.keywords:
                    if kw in text:
                        matched_keywords.append(kw)
                        matched_texts.append((text, confidence))
                        break

        is_watermarked = len(matched_keywords) > 0
        return is_watermarked, matched_keywords, matched_texts

    def detect_text_watermark(self, image_path, image_array=None):
        """
        检测文字水印。
        返回: (是否检测到, 匹配关键词列表, 匹配文本详情, OCR原始结果)
        """
        try:
            if image_array is not None:
                result = self.ocr.ocr(image_array, cls=True)
            else:
                result = self.ocr.ocr(image_path, cls=True)
            if not result or result[0] is None:
                return False, [], [], []
            is_wtm, kws, texts = self._check_text_keywords(result)
            return is_wtm, kws, texts, result
        except Exception as e:
            print(f"OCR 处理失败 {image_path}: {e}")
            return False, [], [], []

    def detect_logo_by_template(self, gray_img):
        """基于模板匹配检测图形水印（支持多尺度）。"""
        if self.logo_template is None:
            return False, 0.0, None

        h, w = gray_img.shape
        tmpl_h, tmpl_w = self.template_size
        best_val = -1
        best_loc = None
        best_scale = 1.0

        # 多尺度模板匹配
        scales = np.linspace(0.5, 2.0, 15)
        for scale in scales:
            new_w = int(tmpl_w * scale)
            new_h = int(tmpl_h * scale)
            if new_w > w or new_h > h or new_w < 10 or new_h < 10:
                continue
            resized_tmpl = cv2.resize(self.logo_template, (new_w, new_h), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(gray_img, resized_tmpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_scale = scale

        detected = best_val >= self.logo_threshold
        return detected, float(best_val), {"location": best_loc, "scale": best_scale, "confidence": float(best_val)}

    def detect_logo_heuristic(self, image):
        """
        启发式图形水印检测。
        检测策略：
        1. 边缘密度异常区域（可能是叠加的 logo）
        2. 角点密集区（图形文字通常角点密集）
        3. 局部对比度异常（半透明水印通常对比度偏低但边缘清晰）
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 1. 全图 Canny 边缘密度
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = np.count_nonzero(edges) / (h * w)

        # 2. 分块检测边缘密度峰值（网格扫描）
        block_h, block_w = h // 4, w // 4
        max_local_edge_ratio = 0.0
        suspicious_blocks = 0

        for y in range(0, h - block_h, block_h // 2):
            for x in range(0, w - block_w, block_w // 2):
                block = edges[y:y+block_h, x:x+block_w]
                local_ratio = np.count_nonzero(block) / (block_h * block_w)
                max_local_edge_ratio = max(max_local_edge_ratio, local_ratio)
                # 如果局部边缘密度远高于全局平均，视为可疑
                if local_ratio > edge_ratio * 3 and local_ratio > 0.05:
                    suspicious_blocks += 1

        # 3. 拉普拉斯方差（检测高频叠加噪声，如细线水印）
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        lap_var = lap.var()

        # 综合评分
        score = 0.0
        # 局部边缘峰值权重
        if max_local_edge_ratio > 0.15:
            score += 0.3
        if suspicious_blocks >= 3:
            score += 0.3
        # 拉普拉斯方差异常高可能表示细线/网格水印
        if lap_var > 500:
            score += 0.2
        if edge_ratio > 0.08:
            score += 0.2

        detected = score >= self.logo_threshold
        return detected, score, {
            "edge_ratio": edge_ratio,
            "max_local_edge_ratio": max_local_edge_ratio,
            "suspicious_blocks": suspicious_blocks,
            "laplacian_var": lap_var,
            "heuristic_score": score
        }

    def detect_transparent_watermark(self, image):
        """
        检测半透明水印（常见为白色/灰色半透明文字或网格）。
        策略：检测高亮区域中的边缘密度，以及局部对比度异常低的区域。
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 1. 高亮区域边缘检测（半透明水印常呈白色/浅灰细线）
        _, bright = cv2.threshold(gray, 210, 255, cv2.THRESH_BINARY)
        bright_edges = cv2.Canny(bright, 50, 150)
        bright_edge_ratio = np.count_nonzero(bright_edges) / (h * w)

        # 2. 局部对比度异常低的区域（大面积半透明叠加）
        gray_f = np.float32(gray)
        mean_sq = cv2.blur(gray_f ** 2, (21, 21))
        mean = cv2.blur(gray_f, (21, 21))
        local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0))
        low_std_ratio = np.count_nonzero(local_std < 3.0) / (h * w)

        score = 0.0
        if bright_edge_ratio > 0.015:
            score += 0.5
        if low_std_ratio > 0.5:
            score += 0.3

        detected = score >= 0.6
        return detected, score, {
            "bright_edge_ratio": bright_edge_ratio,
            "low_std_ratio": float(low_std_ratio),
            "transparent_score": score
        }

    @staticmethod
    def _read_image(image_path):
        """使用 Pillow 读取图片（兼容 webp 等格式），转为 OpenCV 的 BGR/ BGRA numpy 数组。"""
        try:
            img = Image.open(image_path)
            img_np = np.array(img)
            # Pillow 读出来是 RGB(A)，OpenCV 使用 BGR(A)
            if img_np.ndim == 3:
                if img_np.shape[2] == 3:
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                elif img_np.shape[2] == 4:
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGRA)
            return img_np
        except Exception:
            return None

    def analyze(self, image_path):
        """
        综合分析一张图片。
        返回字典包含各项检测结果。
        """
        try:
            image = self._read_image(image_path)
            if image is None:
                return {"error": "无法读取图片", "path": image_path}
        except Exception as e:
            return {"error": f"读取图片异常: {e}", "path": image_path}

        result = {
            "path": image_path,
            "filename": os.path.basename(image_path),
            "has_watermark": False,
            "watermark_types": [],
            "confidence": 0.0,
            "details": {}
        }

        try:
            # 1. 文字水印检测
            text_detected, matched_kws, matched_texts, ocr_raw = self.detect_text_watermark(image_path, image_array=image)
            if text_detected:
                result["watermark_types"].append("text")
                result["details"]["text"] = {
                    "matched_keywords": list(set(matched_kws)),
                    "matched_texts": matched_texts,
                    "count": len(matched_texts)
                }

            # 2. 图形水印检测
            bgr = image[:, :, :3] if image.ndim == 4 else image
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

            if self.logo_template is not None:
                logo_detected, logo_conf, logo_info = self.detect_logo_by_template(gray)
                result["details"]["logo"] = {
                    "method": "template_matching",
                    "detected": logo_detected,
                    "confidence": logo_conf,
                    "info": logo_info
                }
            elif self.enable_heuristic_logo:
                logo_detected, logo_conf, logo_info = self.detect_logo_heuristic(bgr)
                result["details"]["logo"] = {
                    "method": "heuristic",
                    "detected": logo_detected,
                    "confidence": logo_conf,
                    "info": logo_info
                }
            else:
                logo_detected = False
                logo_conf = 0.0

            if logo_detected:
                result["watermark_types"].append("logo")

            # 3. 半透明水印检测
            trans_detected, trans_conf, trans_info = self.detect_transparent_watermark(bgr)
            result["details"]["transparent"] = {
                "detected": trans_detected,
                "confidence": trans_conf,
                "info": trans_info
            }
            if trans_detected:
                result["watermark_types"].append("transparent")

            # 综合判断
            result["has_watermark"] = text_detected or logo_detected or trans_detected
            confidences = []
            if text_detected:
                avg_conf = np.mean([t[1] for t in matched_texts]) if matched_texts else 0.7
                confidences.append(min(avg_conf / 100, 1.0))
            if logo_detected:
                confidences.append(logo_conf)
            if trans_detected:
                confidences.append(trans_conf)

            result["confidence"] = max(confidences) if confidences else 0.0
            result["watermark_types"] = list(set(result["watermark_types"]))
        except Exception as e:
            result["error"] = f"分析异常: {e}"

        return result

    def batch_process(self, input_dir=None, file_list=None, output_dir=None, visualize=False, recursive=True, move_to_err=True):
        """
        批量处理文件夹中的图片，或直接处理给定的文件列表。

        Args:
            input_dir: 输入文件夹路径
            file_list: 图片路径列表（优先于 input_dir）
            output_dir: 输出目录
            visualize: 是否生成可视化结果图
            recursive: 是否递归子文件夹
            move_to_err: 是否将问题图片移动到 ERR 文件夹
        """
        if file_list:
            image_files = list(file_list)
            if output_dir is None:
                output_dir = os.path.join(os.path.dirname(image_files[0]) if image_files else ".", "watermark_output")
        else:
            if input_dir is None:
                raise ValueError("必须提供 input_dir 或 file_list")
            if output_dir is None:
                output_dir = os.path.join(input_dir, "watermark_output")
            os.makedirs(output_dir, exist_ok=True)

            # 收集图片文件
            extensions = (".webp", ".jpg", ".jpeg", ".png", ".bmp", ".gif")
            image_files = []
            if recursive:
                for root, _, files in os.walk(input_dir):
                    # 跳过输出目录本身
                    if os.path.abspath(root).startswith(os.path.abspath(output_dir)):
                        continue
                    for f in files:
                        if f.lower().endswith(extensions):
                            image_files.append(os.path.join(root, f))
            else:
                image_files = [
                    os.path.join(input_dir, f) for f in os.listdir(input_dir)
                    if f.lower().endswith(extensions)
                ]

        if not image_files:
            print(f"未找到支持的图片文件")
            return

        print(f"共发现 {len(image_files)} 张图片，开始检测...")

        results = []
        watermark_count = 0
        error_count = 0
        checkpoint_interval = 200

        for idx, img_path in enumerate(tqdm(image_files, desc="检测进度")):
            try:
                res = self.analyze(img_path)
            except Exception as e:
                res = {"error": f"未捕获异常: {e}", "path": img_path, "filename": os.path.basename(img_path)}
            results.append(res)
            if res.get("has_watermark"):
                watermark_count += 1
            if "error" in res:
                error_count += 1

            # 可视化
            if visualize and "error" not in res:
                try:
                    self._visualize_result(res, output_dir)
                except Exception:
                    pass

            # 定期保存检查点
            if (idx + 1) % checkpoint_interval == 0:
                wc, tc = self._save_reports(results, output_dir, watermark_count, len(image_files))
                print(f"  [检查点] 已处理 {idx+1}/{len(image_files)} 张，累计水印 {wc} 张，本次错误 {error_count} 张")

        # 保存报告
        watermark_count, total_count = self._save_reports(results, output_dir, watermark_count, len(image_files))

        # 移动问题图片到 ERR 文件夹
        if move_to_err and watermark_count > 0:
            err_dir = os.path.join(output_dir, "ERR")
            os.makedirs(err_dir, exist_ok=True)
            moved_count = 0
            for r in results:
                if r.get("has_watermark"):
                    src = r["path"]
                    fname = os.path.basename(src)
                    dst = os.path.join(err_dir, fname)
                    # 处理重名
                    counter = 1
                    base, ext = os.path.splitext(fname)
                    while os.path.exists(dst):
                        dst = os.path.join(err_dir, f"{base}_{counter}{ext}")
                        counter += 1
                    try:
                        os.rename(src, dst)
                        r["moved_to"] = dst
                        moved_count += 1
                    except Exception as e:
                        print(f"移动文件失败 {src}: {e}")
            print(f"已将 {moved_count} 张问题图片移动至: {err_dir}")

        print(f"\n检测完成！发现水印图片: {watermark_count}/{len(image_files)}，处理错误: {error_count}")
        print(f"结果已保存至: {output_dir}")

    def _visualize_result(self, result, output_dir):
        """生成带标注的可视化图片。"""
        img_path = result["path"]
        image = self._read_image(img_path)
        if image is None:
            return

        h, w = image.shape[:2]
        label = "WATERMARK" if result["has_watermark"] else "CLEAN"
        color = (0, 0, 255) if result["has_watermark"] else (0, 255, 0)

        # 画边框
        cv2.rectangle(image, (0, 0), (w-1, h-1), color, 4)
        # 写标签
        text = f"{label} | conf: {result['confidence']:.2f}"
        cv2.putText(image, text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        # 如果有文字水印，在图中标出大致区域（简单标注）
        if "text" in result.get("details", {}):
            y_offset = 80
            for kw in result["details"]["text"].get("matched_keywords", [])[:3]:
                cv2.putText(image, f"Text: {kw}", (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                y_offset += 30

        out_name = f"{result['filename']}_result.jpg"
        out_path = os.path.join(output_dir, "visualized", out_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        cv2.imwrite(out_path, image)

    def _save_reports(self, results, output_dir, watermark_count, total_count):
        """保存 JSON 和 CSV 报告（自动追加已有结果）。"""
        json_path = os.path.join(output_dir, "report.json")
        existing_results = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                existing_results = old.get("results", [])
            except Exception:
                pass

        # 合并并去重（以 path 为键）
        path_set = {r["path"] for r in existing_results}
        merged = list(existing_results)
        for r in results:
            if r["path"] not in path_set:
                merged.append(r)
                path_set.add(r["path"])

        # 重新统计
        watermark_count = sum(1 for r in merged if r.get("has_watermark"))
        total_count = len(merged)

        # JSON
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": total_count,
                "watermark_found": watermark_count,
                "clean": total_count - watermark_count
            },
            "results": merged
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # CSV
        csv_path = os.path.join(output_dir, "report.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["文件名", "文件路径", "是否有水印", "水印类型", "置信度", "详细信息"])
            for r in merged:
                detail_str = json.dumps(r.get("details", {}), ensure_ascii=False)
                writer.writerow([
                    r.get("filename", ""),
                    r.get("path", ""),
                    "是" if r.get("has_watermark") else "否",
                    "/".join(r.get("watermark_types", [])),
                    f"{r.get('confidence', 0):.4f}",
                    detail_str[:500]
                ])

        # 纯文件列表
        with open(os.path.join(output_dir, "watermark_files.txt"), "w", encoding="utf-8") as f:
            for r in merged:
                if r.get("has_watermark"):
                    f.write(r["path"] + "\n")

        with open(os.path.join(output_dir, "clean_files.txt"), "w", encoding="utf-8") as f:
            for r in merged:
                if not r.get("has_watermark"):
                    f.write(r["path"] + "\n")

        return watermark_count, total_count


def main():
    parser = argparse.ArgumentParser(description="图片水印检测工具")
    parser.add_argument("-i", "--input", required=True, help="输入图片或文件夹路径")
    parser.add_argument("-o", "--output", default=None, help="输出目录（默认: 输入目录/watermark_output）")
    parser.add_argument("-t", "--template", default=None, help="图形水印模板图片路径（可选）")
    parser.add_argument("-k", "--keywords", default=None, help="自定义关键词文件路径（每行一个）")
    parser.add_argument("-v", "--visualize", action="store_true", help="生成可视化结果图")
    parser.add_argument("--no-recursive", action="store_true", help="不递归子文件夹")
    parser.add_argument("--no-move", action="store_true", help="不将问题图片移动到 ERR 文件夹")
    parser.add_argument("--text-threshold", type=float, default=0.7, help="文字水印阈值")
    parser.add_argument("--logo-threshold", type=float, default=0.6, help="图形水印阈值")

    args = parser.parse_args()

    # 加载自定义关键词
    keywords = None
    if args.keywords and os.path.exists(args.keywords):
        with open(args.keywords, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]
        print(f"已加载 {len(keywords)} 个自定义关键词")

    detector = WatermarkDetector(
        watermark_keywords=keywords,
        logo_template_path=args.template,
        text_threshold=args.text_threshold,
        logo_threshold=args.logo_threshold
    )

    if os.path.isfile(args.input):
        # 检测是否是文件列表（txt）
        if args.input.lower().endswith(".txt"):
            with open(args.input, "r", encoding="utf-8") as f:
                file_list = [line.strip() for line in f if line.strip() and os.path.exists(line.strip())]
            detector.batch_process(
                file_list=file_list,
                output_dir=args.output,
                visualize=args.visualize,
                move_to_err=not args.no_move
            )
        else:
            # 单文件模式
            print(f"单文件检测: {args.input}")
            res = detector.analyze(args.input)
            print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        detector.batch_process(
            input_dir=args.input,
            output_dir=args.output,
            visualize=args.visualize,
            recursive=not args.no_recursive,
            move_to_err=not args.no_move
        )


if __name__ == "__main__":
    main()
