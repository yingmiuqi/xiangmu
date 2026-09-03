# -*- coding: utf-8 -*-
"""安全暂停当前批次清洗（杀进程、报告断点）。"""

import os
import json
import subprocess

from batch_paths import BATCH_ACTIVE


def main():
    # 杀掉与本任务相关的 python 进程
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
                    pid = int(tokens[-1])
                except ValueError:
                    continue
                subprocess.run("taskkill /F /T /PID %d" % pid, shell=True)
                killed += 1
    except Exception as e:
        print("kill error:", e)
    print("killed:", killed)

    cp = os.path.join(BATCH_ACTIVE, "clean_report", "checkpoint.json")
    if os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            cnt = len(json.load(f))
        print("checkpoint:", cnt)
    err = os.path.join(BATCH_ACTIVE, "自动清扫ERR")
    if os.path.isdir(err):
        print("ERR files:", len(os.listdir(err)))
    print("done")


if __name__ == "__main__":
    main()
