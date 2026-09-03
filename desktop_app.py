# -*- coding: utf-8 -*-
"""图片清洗 桌面窗口版（Tkinter）。
运行：python desktop_app.py
"""

import os
import sys
import json
import glob
import subprocess
import threading
import tkinter as tk
import tkinter.messagebox
from tkinter import ttk, scrolledtext, filedialog


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from batch_paths import BATCH_ACTIVE  # noqa: E402

PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
MONITOR = os.path.join(ROOT, "monitor_full.py")
PAUSE = os.path.join(ROOT, "pause_task.py")
BATCH_FILE = os.path.join(ROOT, "webui_batch.txt")
TRAIN_STD = os.path.join(ROOT, "train_v8.py")
TRAIN_CUSTOM = os.path.join(ROOT, "train_model.py")
TRAIN_LOG = os.path.join(ROOT, "models", "train_v8.stdout.log")
TRAIN_ERR = os.path.join(ROOT, "models", "train_v8.stderr.log")


def current_batch():
    if os.path.exists(BATCH_FILE):
        try:
            with open(BATCH_FILE, encoding="utf-8") as f:
                b = f.read().strip()
            if b and os.path.isdir(b):
                return b
        except Exception:
            pass
    return BATCH_ACTIVE


def images_count(batch):
    d = os.path.join(batch, "images")
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d) if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png")))


def process_alive():
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get processid,commandline',
            shell=True, text=True, errors="ignore", timeout=15,
        )
        return any(k in out for k in ("monitor_full.py", "image_cleaner.runner"))
    except Exception:
        return False


def training_alive():
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get processid,commandline',
            shell=True, text=True, errors="ignore", timeout=15,
        )
        return any(k in out for k in ("train_v8.py", "train_model.py"))
    except Exception:
        return False


def latest_log(batch, n=3000):
    report = os.path.join(batch, "clean_report")
    logs = sorted(glob.glob(os.path.join(report, "run_*.log")), key=os.path.getmtime, reverse=True)
    if not logs:
        return ""
    try:
        with open(logs[0], encoding="utf-8", errors="ignore") as f:
            return f.read()[-n:]
    except Exception:
        return ""


class App:
    def __init__(self, root):
        self.root = root
        root.title("图片清洗工具")
        root.geometry("860x620")
        root.configure(bg="#f5f6fa")

        self.batch_var = tk.StringVar(value=current_batch())

        # 顶部：批次输入
        top = tk.Frame(root, bg="#f5f6fa")
        top.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(top, text="批次目录（含 images 子文件夹）：", bg="#f5f6fa").pack(anchor="w")
        self.entry = tk.Entry(top, textvariable=self.batch_var, font=("Microsoft YaHei", 11))
        self.entry.pack(fill="x", pady=4)

        # 按钮区
        btns = tk.Frame(root, bg="#f5f6fa")
        btns.pack(fill="x", padx=16, pady=4)
        tk.Button(btns, text="设置批次", command=self.save_path, width=12).pack(side="left", padx=2)
        tk.Button(btns, text="启动（仅分析）", command=lambda: self.start(False), width=14).pack(side="left", padx=2)
        tk.Button(btns, text="启动并移动", command=lambda: self.start(True), width=12,
                  bg="#e5484d", fg="white").pack(side="left", padx=2)
        tk.Button(btns, text="暂停", command=self.stop, width=8).pack(side="left", padx=2)
        tk.Button(btns, text="打开ERR", command=lambda: self.open_dir("err")).pack(side="left", padx=2)
        tk.Button(btns, text="打开报告", command=lambda: self.open_dir("report")).pack(side="left", padx=2)
        tk.Button(btns, text="一键训练", command=self.train_standard, width=10).pack(side="left", padx=2)
        tk.Button(btns, text="自选文件夹训练", command=self.train_custom, width=14).pack(side="left", padx=2)

        # 状态区
        self.status_var = tk.StringVar(value="状态：未运行")
        self.progress = ttk.Progressbar(root, maximum=100, length=820)
        self.progress.pack(fill="x", padx=16, pady=8)
        tk.Label(root, textvariable=self.status_var, bg="#f5f6fa",
                 font=("Microsoft YaHei", 11), anchor="w").pack(fill="x", padx=16)

        # 日志区
        tk.Label(root, text="运行日志（末尾）：", bg="#f5f6fa").pack(anchor="w", padx=16)
        self.log = scrolledtext.ScrolledText(root, height=16, bg="#1e1e2e", fg="#cdd6f4",
                                             font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self.root.after(2000, self.refresh)

    def save_path(self):
        p = self.batch_var.get().strip()
        if not os.path.isdir(p):
            self.status_var.set("错误：目录不存在")
            return
        with open(BATCH_FILE, "w", encoding="utf-8") as f:
            f.write(p)
        self.status_var.set("批次已设置：" + p)

    def start(self, move):
        batch = current_batch()
        total = images_count(batch)
        if total == 0:
            self.status_var.set("错误：批次下未找到 images 目录或图片")
            return
        if process_alive():
            self.status_var.set("已有任务在运行，请先暂停")
            return
        if move and not tk.messagebox.askyesno("确认", "启动【真实移动】模式？\n移动后有日志可回退。"):
            return
        cmd = [PY, "-X", "utf8", MONITOR, "--total", str(total),
               "--max-per-run", "3000", "--log-prefix", "run_desktop"]
        if move:
            cmd.append("--move")
        env = dict(os.environ)
        env["CODEX_BATCH_PATH"] = batch
        subprocess.Popen(cmd, cwd=ROOT, env=env,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status_var.set("已启动（%s）" % ("真实移动" if move else "仅分析"))

    def stop(self):
        subprocess.Popen([PY, "-X", "utf8", PAUSE], cwd=ROOT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status_var.set("正在安全暂停...")

    def train_standard(self):
        if training_alive():
            tk.messagebox.showinfo("提示", "已有训练在运行，请先等它完成。")
            return
        if not tk.messagebox.askyesno("确认", "启动【一键训练】？\n"
                                                "会自动收集各批次人工 ERR 当坏图、人工保留图当好图，\n"
                                                "训练约 5 小时，期间请勿关机。"):
            return
        with open(TRAIN_LOG, "w", encoding="utf-8", errors="ignore") as fo, \
                open(TRAIN_ERR, "w", encoding="utf-8", errors="ignore") as fe:
            subprocess.Popen([PY, "-X", "utf8", TRAIN_STD], cwd=ROOT,
                             stdout=fo, stderr=fe,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status_var.set("训练已启动，日志：" + TRAIN_LOG)
        tk.messagebox.showinfo("已启动", "训练已在后台启动。\n完成后模型自动生效。\n日志：models\\train_v8.stdout.log")

    def train_custom(self):
        if training_alive():
            tk.messagebox.showinfo("提示", "已有训练在运行，请先等它完成。")
            return
        bad = filedialog.askdirectory(title="选择坏图文件夹（需要移动的图片，如人工ERR）")
        if not bad:
            return
        good = filedialog.askdirectory(title="选择正常图文件夹（确认没问题的图片）")
        if not good:
            return
        if not tk.messagebox.askyesno("确认", "使用自选文件夹训练？\n坏图：%s\n正常图：%s" % (bad, good)):
            return
        cmd = [PY, "-X", "utf8", TRAIN_CUSTOM,
               "--pos-dir", bad, "--neg-dir", good, "--epochs", "5"]
        log = os.path.join(ROOT, "models", "train_custom.stdout.log")
        err = os.path.join(ROOT, "models", "train_custom.stderr.log")
        with open(log, "w", encoding="utf-8", errors="ignore") as fo, \
                open(err, "w", encoding="utf-8", errors="ignore") as fe:
            subprocess.Popen(cmd, cwd=ROOT, stdout=fo, stderr=fe,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status_var.set("训练已启动，日志：" + log)
        tk.messagebox.showinfo("已启动", "训练已在后台启动。\n完成后模型自动生效。")

    def open_dir(self, target):
        batch = current_batch()
        path = {"err": os.path.join(batch, "自动清扫ERR"),
                "report": os.path.join(batch, "clean_report")}.get(target, batch)
        if os.path.isdir(path):
            os.startfile(path)
        else:
            self.status_var.set("目录不存在：" + path)

    def refresh(self):
        try:
            batch = current_batch()
            report = os.path.join(batch, "clean_report")
            cp = os.path.join(report, "checkpoint.json")
            done = 0
            if os.path.exists(cp):
                try:
                    with open(cp, encoding="utf-8") as f:
                        done = len(json.load(f))
                except Exception:
                    done = 0
            err_dir = os.path.join(batch, "自动清扫ERR")
            err = len(os.listdir(err_dir)) if os.path.isdir(err_dir) else 0
            total = images_count(batch)
            running = process_alive()
            pct = round(100 * done / total) if total else 0
            self.progress["value"] = pct
            self.status_var.set("状态：%s | 批次：%s | 进度：%s / %s | 已移动进ERR：%s 张 | 完成度 %s%%" % (
                "运行中" if running else "未运行", batch, done, total, err, pct))
            log = latest_log(batch)
            if log and log != self.log.get("1.0", "end").strip()[-len(log):]:
                self.log.delete("1.0", "end")
                self.log.insert("1.0", log)
                self.log.see("end")
        except Exception as e:
            self.status_var.set("刷新失败：" + str(e))
        self.root.after(2000, self.refresh)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
