# -*- coding: utf-8 -*-
"""盘点：扫描图片、读取 index.txt、断点续传。"""

import os
import json

from . import config


def _skip_dir(name):
    return name.lower() in config.SKIP_DIR_NAMES


def collect_images(target_dir, recursive=True):
    """收集 target_dir 下的图片路径（跳过缓存/ERR/报告等目录），按路径排序。"""
    files = []
    if recursive:
        for root, dirs, names in os.walk(target_dir):
            dirs[:] = [d for d in dirs if not _skip_dir(d)]
            for n in names:
                if n.lower().endswith(config.IMAGE_EXTENSIONS):
                    files.append(os.path.join(root, n))
    else:
        for n in os.listdir(target_dir):
            p = os.path.join(target_dir, n)
            if os.path.isfile(p) and n.lower().endswith(config.IMAGE_EXTENSIONS):
                files.append(p)
    return sorted(files)


def load_index(index_path):
    """读取 index.txt（每行：文件名<TAB>原始路径）→ {文件名: 原始路径}。"""
    mapping = {}
    if not index_path or not os.path.exists(index_path):
        return mapping
    try:
        with open(index_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    mapping[parts[0]] = parts[1]
                else:
                    mapping[os.path.basename(line)] = line
    except Exception as e:
        print(f"[警告] 读取 index.txt 失败: {e}")
    return mapping


class Checkpoint:
    """断点续传：记录已处理文件的绝对路径。"""

    def __init__(self, path):
        self.path = path
        self.done = set()
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.done = set(json.load(f))
            except Exception:
                self.done = set()

    def is_done(self, path):
        return path in self.done

    def mark(self, path):
        self.done.add(path)

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        data = json.dumps(sorted(self.done), ensure_ascii=False)
        # 重试写入：桌面版/看门狗可能正打开 checkpoint 读取，os.replace 会撞
        # Windows 文件锁（WinError 5，曾导致 group_723 收尾崩溃）。
        last_err = None
        for attempt in range(5):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp, self.path)
                return
            except PermissionError as e:
                last_err = e
                import time
                time.sleep(0.2 * (attempt + 1))
        # 最终降级：直接覆盖写（不再原子替换，避免任务崩溃）
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            print(f"[警告] 断点保存失败: {e} (原始: {last_err})")
