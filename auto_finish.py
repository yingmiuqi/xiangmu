# -*- coding: utf-8 -*-
"""整批收尾管家：监控重建进程，挂了自动重启；报告齐全后生成汇总。"""

import os
import time
import json
import subprocess
from datetime import datetime


BATCH = r"D:\图片清理\group_339_76503"
REPORT = os.path.join(BATCH, "clean_report")
REPORT_JSON = os.path.join(REPORT, "report.json")
TOTAL = 60337
PY = r"D:\图片清理\pythonProject1\.venv\Scripts\python.exe"
CWD = r"D:\图片清理\pythonProject1"
RUN_LOG = os.path.join(REPORT, "run_rebuild.log")
RUN_ERR = os.path.join(REPORT, "run_rebuild.err.log")
OPS_LOG = os.path.join(REPORT, "auto_ops.log")
SUMMARY_SCRIPT = os.path.join(CWD, "build_summary.py")


def log(msg):
    with open(OPS_LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")


def report_count():
    try:
        with open(REPORT_JSON, "r", encoding="utf-8") as f:
            return len(json.load(f).get("results", []))
    except Exception:
        return None


def runner_alive():
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get commandline',
            shell=True, text=True, errors="ignore", timeout=30,
        )
        return "image_cleaner.runner" in out
    except Exception:
        return True


def start_runner():
    with open(RUN_LOG, "a", encoding="utf-8") as lf, open(RUN_ERR, "a", encoding="utf-8") as ef:
        p = subprocess.Popen(
            [PY, "-X", "utf8", "-m", "image_cleaner.runner",
             "--input", BATCH, "--force", "--no-dedup"],
            cwd=CWD, stdout=lf, stderr=ef,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    log("已（重新）启动重建进程 PID=%s" % p.pid)
    return p


def main():
    log("收尾管家启动，目标 %d 张" % TOTAL)
    proc = None
    last_restart = 0.0

    while True:
        cnt = report_count()
        if cnt is not None and cnt >= TOTAL:
            log("报告已完整（%d 张），开始生成汇总" % cnt)
            r = subprocess.run([PY, "-X", "utf8", SUMMARY_SCRIPT], cwd=CWD,
                               capture_output=True, text=True, encoding="utf-8")
            log("汇总脚本输出：" + r.stdout.strip()[:500])
            if r.returncode != 0:
                log("汇总脚本失败：" + (r.stderr or "")[:500])
            return

        if not runner_alive():
            if time.time() - last_restart >= 120:
                log("检测到重建进程不在，重启")
                proc = start_runner()
                last_restart = time.time()
            else:
                log("重建进程不在，冷却中")
        elif proc is not None and proc.poll() is not None:
            proc = None

        time.sleep(60)


if __name__ == "__main__":
    main()
