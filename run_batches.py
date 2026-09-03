import os
import sys
import json
import subprocess
import time

def run_batches(input_dir, batch_size=400):
    """
    自动分批执行水印检测，每批处理完后重启进程以释放 PaddleOCR 内存。
    支持断点续传。
    """
    output_dir = os.path.join(input_dir, "watermark_output")
    checkpoint_file = os.path.join(output_dir, "checkpoint.json")

    # 收集所有图片
    extensions = (".webp", ".jpg", ".jpeg", ".png", ".bmp", ".gif")
    image_files = []
    for root, _, files in os.walk(input_dir):
        if os.path.abspath(root).startswith(os.path.abspath(output_dir)):
            continue
        for f in files:
            if f.lower().endswith(extensions):
                image_files.append(os.path.join(root, f))

    total = len(image_files)
    if total == 0:
        print("未找到图片")
        return

    # 读取已处理记录
    processed = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            processed = set(json.load(f))
        print(f"已处理 {len(processed)} 张，剩余 {total - len(processed)} 张")

    remaining = [p for p in image_files if p not in processed]

    while remaining:
        batch = remaining[:batch_size]
        print(f"\n===== 启动新批次: {len(batch)} 张 (剩余 {len(remaining)} 张) =====")

        # 写入本次批次列表
        batch_list = os.path.join(output_dir, "_batch_list.txt")
        with open(batch_list, "w", encoding="utf-8") as f:
            for p in batch:
                f.write(p + "\n")

        # 调用主程序处理本批次
        script_dir = os.path.dirname(os.path.abspath(__file__))
        detector = os.path.join(script_dir, "watermark_detector.py")
        cmd = [sys.executable, detector, "-i", batch_list, "--no-move"]

        start = time.time()
        proc = subprocess.run(cmd, cwd=script_dir)
        elapsed = time.time() - start
        print(f"本批次耗时: {elapsed:.1f}s")

        # 读取本次结果并合并到 checkpoint
        report_path = os.path.join(output_dir, "report.json")
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for r in data.get("results", []):
                    processed.add(r["path"])
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(list(processed), f)
                print(f"累计处理: {len(processed)}/{total}")
            except Exception as e:
                print(f"合并报告失败: {e}")
        else:
            print("警告: 未找到报告文件")

        # 清理批次列表
        if os.path.exists(batch_list):
            os.remove(batch_list)

        # 更新剩余列表
        remaining = [p for p in remaining if p not in processed]

        if proc.returncode != 0:
            print(f"子进程异常退出 (code {proc.returncode})，已保存进度，继续下一批...")

    print("\n===== 全部处理完成 =====")

    # 最终移动问题图片
    detector = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watermark_detector.py")
    subprocess.run([sys.executable, detector, "-i", input_dir, "--no-recursive"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run_batches.py <图片文件夹路径> [每批数量]")
        sys.exit(1)
    input_dir = sys.argv[1]
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    run_batches(input_dir, batch_size)
