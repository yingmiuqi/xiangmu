# -*- coding: utf-8 -*-
import os
import sys
import subprocess

from batch_paths import BATCH_653

os.environ["CODEX_BATCH_PATH"] = BATCH_653
child = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_env_child.py")
r = subprocess.run([sys.executable, "-X", "utf8", child], capture_output=True, text=True, encoding="utf-8")
print("child rc:", r.returncode)
print(r.stdout)
print(r.stderr)
