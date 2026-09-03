# -*- coding: utf-8 -*-
"""图片清洗 本地网页界面。
运行：python webui/app.py  → 浏览器打开 http://127.0.0.1:5000
"""

import os
import sys
import json
import glob
import subprocess

from flask import Flask, jsonify, render_template, request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from batch_paths import BATCH_ACTIVE  # noqa: E402

PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
MONITOR = os.path.join(ROOT, "monitor_full.py")
PAUSE = os.path.join(ROOT, "pause_task.py")
BATCH_FILE = os.path.join(ROOT, "webui_batch.txt")

app = Flask(__name__)


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
            shell=True, text=True, errors="ignore", timeout=20,
        )
        return any(k in out for k in ("monitor_full.py", "image_cleaner.runner"))
    except Exception:
        return False


def latest_log(batch):
    report = os.path.join(batch, "clean_report")
    logs = sorted(glob.glob(os.path.join(report, "run_*.log")), key=os.path.getmtime, reverse=True)
    if not logs:
        return ""
    try:
        with open(logs[0], encoding="utf-8", errors="ignore") as f:
            return f.read()[-2000:]
    except Exception:
        return ""


@app.route("/")
def index():
    return render_template("index.html", batch=current_batch())


@app.route("/api/status")
def status():
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
    return jsonify({
        "batch": batch,
        "total": images_count(batch),
        "done": done,
        "err": err,
        "running": process_alive(),
        "log": latest_log(batch),
    })


@app.route("/api/save-path", methods=["POST"])
def save_path():
    data = request.get_json(force=True)
    p = (data.get("path") or "").strip()
    if not os.path.isdir(p):
        return jsonify({"ok": False, "msg": "目录不存在"})
    with open(BATCH_FILE, "w", encoding="utf-8") as f:
        f.write(p)
    return jsonify({"ok": True, "msg": "已设置批次: " + p})


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    batch = current_batch()
    total = images_count(batch)
    if total == 0:
        return jsonify({"ok": False, "msg": "批次下未找到 images 目录或图片"})
    if process_alive():
        return jsonify({"ok": False, "msg": "已有任务在运行，请先暂停"})
    move = bool(data.get("move"))
    cmd = [PY, "-X", "utf8", MONITOR, "--total", str(total),
           "--max-per-run", "3000", "--log-prefix", "run_web"]
    if move:
        cmd.append("--move")
    env = dict(os.environ)
    env["CODEX_BATCH_PATH"] = batch
    subprocess.Popen(cmd, cwd=ROOT, env=env,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return jsonify({"ok": True, "msg": "已启动（%s）" % ("真实移动" if move else "仅分析")})


@app.route("/api/stop")
def stop():
    subprocess.Popen([PY, "-X", "utf8", PAUSE], cwd=ROOT,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return jsonify({"ok": True, "msg": "正在安全暂停..."})


@app.route("/api/open", methods=["POST"])
def open_dir():
    data = request.get_json(force=True)
    target = data.get("target", "err")
    batch = current_batch()
    path = {"err": os.path.join(batch, "自动清扫ERR"),
            "report": os.path.join(batch, "clean_report")}.get(target, batch)
    if os.path.isdir(path):
        os.startfile(path)  # noqa: S606 - 用户主动点击打开
        return jsonify({"ok": True, "msg": path})
    return jsonify({"ok": False, "msg": "目录不存在: " + path})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
