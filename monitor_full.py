# -*- coding: utf-8 -*-
"""整批任务看门狗 v2：
- 每 5 分钟记录进度/内存/进程状态到 monitor.log；
- 识别进程跑满 MAX_PER_RUN 张后以退出码 77 自我轮换，看门狗立即拉起新进程（内存封顶）；
- 进程意外崩溃自动重启（带冷却防死循环）；
- 内存超限（> MAX_WORKER_MB）主动杀掉重启，双保险。
"""

import os
import argparse
import time
import json
import ctypes
import subprocess
from datetime import datetime


PY = r"D:\图片清理\pythonProject1\.venv\Scripts\python.exe"
CWD = r"D:\图片清理\pythonProject1"
INTERVAL = 300           # 状态日志间隔：5 分钟
POLL = 20                # 内部轮询间隔：20 秒
MAX_WORKER_MB = 8000     # 工作进程内存上限（双保险；本机 15.7GB，PaddleOCR+torch 同进程需要余量，6000 曾导致 125 次重启）
MIN_RESTART_GAP = 120    # 崩溃后重启冷却（秒）
ROTATE_CODE = 77         # 主动轮换退出码
STALL_LIMIT = 2          # 连续 N 个状态周期无进度即视为卡住，杀掉重启


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def mem_mb():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys // (1024 * 1024), m.ullAvailPageFile // (1024 * 1024)


def ckpt_count():
    try:
        with open(CKPT, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return None


def current_file():
    try:
        with open(CURRENT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def worker_mb():
    """runner 工作进程（含子进程）的最大工作集（MB）。"""
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get processid,commandline,workingsetsize',
            shell=True, text=True, errors="ignore", timeout=30,
        )
        best = 0
        for line in out.splitlines():
            if "image_cleaner.runner" not in line:
                continue
            parts = line.split()
            for part in parts:
                if part.isdigit() and len(part) >= 7:
                    best = max(best, int(part) // (1024 * 1024))
        return best
    except Exception:
        return 0


def start_runner(batch, total, max_per_run, run_log, run_err, move, force, err_dir):
    cmd = [PY, "-X", "utf8", "-m", "image_cleaner.runner",
           "--no-dedup", "--max-per-run", str(max_per_run)]
    if move:
        cmd.append("--move")
    if force:
        cmd.append("--force")
    if err_dir:
        cmd += ["--err-dir", err_dir]
    with open(run_log, "a", encoding="utf-8") as lf, open(run_err, "a", encoding="utf-8") as ef:
        return subprocess.Popen(
            cmd,
            cwd=CWD, stdout=lf, stderr=ef,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def kill_tree(pid):
    subprocess.run("taskkill /F /T /PID %d" % pid, shell=True)


def log(msg):
    with open(MONITOR_LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=None, help="缺省用环境变量 CODEX_BATCH_PATH")
    parser.add_argument("--total", type=int, default=60337)
    parser.add_argument("--max-per-run", type=int, default=2000)
    parser.add_argument("--move", action="store_true", help="识别进程带 --move 执行移动")
    parser.add_argument("--force", action="store_true", help="忽略断点重新处理全部")
    parser.add_argument("--err-dir", default=None, help="自定义 ERR 目录（默认批次根目录/ERR）")
    parser.add_argument("--log-prefix", default="run_full3")
    args = parser.parse_args()
    if not args.input:
        args.input = os.environ.get("CODEX_BATCH_PATH")
    if not args.input:
        try:
            from batch_paths import BATCH_ACTIVE
            args.input = BATCH_ACTIVE
        except Exception:
            pass
    if not args.input:
        raise SystemExit("未指定 --input，且环境变量 CODEX_BATCH_PATH 为空")
    os.environ["CODEX_BATCH_PATH"] = args.input
    if not args.err_dir:
        args.err_dir = os.path.join(args.input, "自动清扫ERR")

    global MONITOR_LOG, CKPT, CURRENT_FILE
    BATCH = args.input
    TOTAL = args.total
    MAX_PER_RUN = args.max_per_run
    REPORT = os.path.join(BATCH, "clean_report")
    CKPT = os.path.join(REPORT, "checkpoint.json")
    MONITOR_LOG = os.path.join(REPORT, "monitor.log")
    RUN_LOG = os.path.join(REPORT, args.log_prefix + ".log")
    RUN_ERR = os.path.join(REPORT, args.log_prefix + ".err.log")
    CURRENT_FILE = os.path.join(REPORT, "current.txt")
    QUARANTINE_DIR = os.path.join(BATCH, "卡住文件")

    os.makedirs(REPORT, exist_ok=True)
    log("看门狗 v2 启动：单轮上限 %d 张，状态日志每 %ds，总目标 %d" % (MAX_PER_RUN, INTERVAL, TOTAL))
    proc = None
    last_restart = 0.0
    last_status = 0.0
    last_count = ckpt_count()
    stall_count = 0
    last_stall_file = ""

    while True:
        if proc is None:
            proc = start_runner(BATCH, TOTAL, MAX_PER_RUN, RUN_LOG, RUN_ERR,
                                args.move, args.force, args.err_dir)
            last_restart = time.time()
            log("已启动识别进程 PID=%s" % proc.pid)

        rc = proc.poll()
        if rc is not None:
            proc = None
            if rc == ROTATE_CODE:
                log("本轮完成（退出码 77），立即轮换新进程")
                continue
            if rc == 0:
                cnt = ckpt_count()
                if cnt is not None and cnt >= TOTAL:
                    log("识别进程正常退出（退出码 0）且已完成全部，看门狗退出")
                    return
                log("识别进程正常退出（退出码 0），但任务未完成，等待下个周期重启")
                time.sleep(30)
                continue
            now = time.time()
            if now - last_restart >= MIN_RESTART_GAP:
                log("检测到崩溃（退出码 %s），自动重启" % rc)
                continue
            log("检测到崩溃（退出码 %s），冷却中，稍后重试" % rc)
            time.sleep(30)
            continue

        wmb = worker_mb()
        if wmb > MAX_WORKER_MB:
            log("工作进程内存 %dMB 超限，主动杀掉重启" % wmb)
            kill_tree(proc.pid)
            proc = None
            last_restart = time.time()
            continue

        if time.time() - last_status >= INTERVAL:
            cnt = ckpt_count()
            cf = current_file()
            avail_ram, avail_pf = mem_mb()
            log("checkpoint=%s alive=1 workerMB=%d availRAM=%dMB availPageFile=%dMB current=%s" % (
                cnt, wmb, avail_ram, avail_pf, os.path.basename(cf) if cf else "-"))
            last_status = time.time()
            if cnt is not None and cnt >= TOTAL:
                log("整批完成，看门狗退出")
                return
            if cnt is not None and cnt == last_count:
                stall_count += 1
                log("警告：断点进度未增长（第 %d 次），卡住文件: %s" % (
                    stall_count, os.path.basename(cf) if cf else "-"))
                if stall_count >= STALL_LIMIT:
                    log("连续无进度，杀掉并重启；若同文件再次卡住将隔离")
                    if cf and cf == last_stall_file:
                        os.makedirs(QUARANTINE_DIR, exist_ok=True)
                        try:
                            dst = os.path.join(QUARANTINE_DIR, os.path.basename(cf))
                            if os.path.exists(cf) and not os.path.exists(dst):
                                os.replace(cf, dst)
                                log("已隔离顽固卡住文件: %s" % os.path.basename(cf))
                        except Exception as e:
                            log("隔离失败: %s" % e)
                    last_stall_file = cf
                    kill_tree(proc.pid)
                    proc = None
                    stall_count = 0
                    continue
            else:
                stall_count = 0
            last_count = cnt

        time.sleep(POLL)


if __name__ == "__main__":
    main()
