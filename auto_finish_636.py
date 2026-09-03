# -*- coding: utf-8 -*-
"""group_636 清扫到 20,000 张自动收尾：
停任务 → 补移未落盘的判定移动图 → 生成汇总与疑问清单。"""

import os
import sys
import json
import time
import csv
import subprocess
from collections import Counter
from datetime import datetime


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image_cleaner.actions import move_to_err  # noqa: E402


BASE = r"D:\图片清理\group_636_58978"
REPORT = os.path.join(BASE, "clean_report")
CKPT = os.path.join(REPORT, "checkpoint.json")
ROWS = os.path.join(REPORT, "report_rows.jsonl")
ERR = os.path.join(BASE, "ERR")
MOVE_LOG = os.path.join(REPORT, "move_log.jsonl")
LOG_FILE = os.path.join(REPORT, "auto_finish_636.log")
TARGET = 20000
DEADLINE_HOURS = 9


def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | " + msg + "\n")
    print(msg, flush=True)


def ckpt_count():
    try:
        with open(CKPT, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


def kill_workers():
    """杀掉识别进程与看门狗（保留本脚本自身）。"""
    me = os.getpid()
    try:
        out = subprocess.check_output(
            'wmic process where "name=\'python.exe\'" get processid,commandline',
            shell=True, text=True, errors="ignore", timeout=30,
        )
        for line in out.splitlines():
            if ("image_cleaner.runner" in line or "monitor_full.py" in line) and \
               "auto_finish_636.py" not in line:
                parts = line.split()
                pid = int(parts[0])
                if pid == me:
                    continue
                subprocess.run("taskkill /F /T /PID %d" % pid, shell=True)
                log("已停止 PID %d" % pid)
    except Exception as e:
        log("停止进程失败: %s" % e)


def flush_moves():
    moved = skipped = 0
    seen = {}
    with open(ROWS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            key = obj.get("文件名") or obj.get("_path")
            if key:
                seen[key] = obj
    for obj in seen.values():
        if obj.get("决策") != "MOVE":
            continue
        src = obj.get("_path") or os.path.join(os.path.join(BASE, "images"), obj.get("文件名", ""))
        if not os.path.exists(src):
            skipped += 1
            continue
        move_to_err(src, ERR, move_log_path=MOVE_LOG)
        moved += 1
    log("补移 %d 张（跳过 %d）" % (moved, skipped))
    return moved


def build_summary():
    seen = {}
    with open(ROWS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            key = obj.get("文件名") or obj.get("_path")
            if key:
                seen[key] = obj
    rows = list(seen.values())
    moves = [r for r in rows if r.get("决策") == "MOVE"]
    revs = [r for r in rows if r.get("决策") == "REVIEW"]
    by_rule = Counter(r.get("规则") for r in moves)
    wm_hi = [r for r in revs if (r.get("水印模型分") or 0) >= 0.7]
    lines = []
    lines.append("group_636 清扫汇总（到 20,000 张自动收尾）")
    lines.append("生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("已处理（去重）：%d 张" % len(rows))
    lines.append("移动进 ERR：%d 张" % len(moves))
    lines.append("待审核：%d 张（其中水印模型≥0.7：%d）" % (len(revs), len(wm_hi)))
    lines.append("保留：%d 张" % (len(rows) - len(moves) - len(revs)))
    lines.append("")
    lines.append("【移动规则分布】")
    for rule, c in by_rule.most_common():
        lines.append("  %s：%d" % (rule, c))
    lines.append("")
    lines.append("【待审核原因分布】")
    rev_by = Counter()
    for r in revs:
        if (r.get("水印模型分") or 0) >= 0.7:
            rev_by["水印模型≥0.7"] += 1
        else:
            rev_by["；".join(r.get("证据", []))[:40]] += 1
    for k, c in rev_by.most_common():
        lines.append("  %s：%d" % (k, c))
    lines.append("")
    lines.append("ERR 当前文件总数：%d" % len(os.listdir(ERR)))
    with open(os.path.join(REPORT, "汇总报告_636_20000.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(REPORT, "待审核清单_636_20000.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件名", "证据", "水印模型分"])
        for r in sorted(revs, key=lambda x: -(float(x.get("水印模型分") or 0))):
            w.writerow([r.get("文件名"), "; ".join(r.get("证据", [])), r.get("水印模型分", "")])
    log("汇总已写出：汇总报告_636_20000.txt / 待审核清单_636_20000.csv")


def main():
    log("自动收尾已启动，目标 %d 张" % TARGET)
    deadline = time.time() + DEADLINE_HOURS * 3600
    while True:
        cnt = ckpt_count()
        if cnt >= TARGET:
            log("已达到 %d 张，开始收尾" % cnt)
            break
        if time.time() > deadline:
            log("超时（%d 小时）仍未到 %d，当前 %d，继续等待" % (DEADLINE_HOURS, TARGET, cnt))
            deadline = time.time() + DEADLINE_HOURS * 3600
        time.sleep(60)
    kill_workers()
    time.sleep(3)
    flush_moves()
    build_summary()
    log("全部完成")


if __name__ == "__main__":
    main()
