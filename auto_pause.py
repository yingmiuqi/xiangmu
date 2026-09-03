# -*- coding: utf-8 -*-
"""定时暂停：明早 07:30 前未完成则安全停止 group_653 清洗（断点保存，可续跑）。"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timedelta


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_paths import BATCH_653  # noqa: E402


REPORT = os.path.join(BATCH_653, "clean_report")
CKPT = os.path.join(REPORT, "checkpoint.json")
LOG = os.path.join(REPORT, "auto_pause.log")
TOTAL = 64040


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def next_deadline():
    now = datetime.now()
    d = now.replace(hour=7, minute=30, second=0, microsecond=0)
    if d <= now:
        d += timedelta(days=1)
    return d


def ckpt_count():
    try:
        with open(CKPT, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


def stop_workers():
    me = os.getpid()
    killed = 0
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get processid,commandline',
            shell=True, text=True, errors="ignore", timeout=30,
        )
        for line in out.splitlines():
            if "monitor_full.py" in line or "image_cleaner.runner" in line:
                tokens = line.split()
                if not tokens:
                    continue
                try:
                    pid = int(tokens[-1])  # wmic 输出最后一列为 PID
                except ValueError:
                    continue
                if pid == me:
                    continue
                subprocess.run("taskkill /F /T /PID %d" % pid, shell=True)
                killed += 1
                log("已停止 PID %d" % pid)
    except Exception as e:
        log("停止进程异常: %s" % e)
    return killed


def main():
    deadline = next_deadline()
    log("定时暂停已启动：截止 %s，目标 %d" % (deadline.strftime("%Y-%m-%d %H:%M"), TOTAL))
    while True:
        cnt = ckpt_count()
        if cnt >= TOTAL:
            log("任务已完成（%d 张），无需暂停" % cnt)
            return
        now = datetime.now()
        if now >= deadline:
            log("到截止时间仍未完成（当前 %d / %d），开始暂停" % (cnt, TOTAL))
            k = stop_workers()
            log("已停止 %d 个进程，断点 %d 已保存，可续跑" % (k, cnt))
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
