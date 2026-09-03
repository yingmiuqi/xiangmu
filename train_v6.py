# -*- coding: utf-8 -*-
"""v6 训练启动器：用 group_653 人工 ERR（12531 张）作为正样本重训水印模型。"""

import os
import sys

from batch_paths import HUMAN_ERR_653

os.environ["CODEX_EXTRA_POS"] = HUMAN_ERR_653

sys.argv = ["train_v6", "--epochs", "5", "--max-neg", "8000"]
from build_watermark_model_v3 import main  # noqa: E402

main()
