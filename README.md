# 图片数据清洗自动化脚本

依据《图片数据清洗操作说明》开发的批量 WebP 图片分类清洗脚本。

## 当前阶段

- 里程碑 1（已实现）：盘点扫描、文件级/图像级快检（损坏、过小、纯色/空白、二维码）、
  dry-run 报告、ERR 移动（含防重名）、断点续传。
- 里程碑 2（已实现）：PaddleOCR 文本规则（中文 / 网址 / 联系方式 / 价格 / 促销 / 电商网站 / 水印）
  与保留词表；英文关键词按单词边界匹配；弱促销信号进审核。
- 里程碑 3（部分实现）：MD5 指纹去重联动（同指纹一张不合格全部联动移动）、
  基于 move_log 的回退工具、纯 LOGO/品牌图启发式（进审核）。
- 里程碑 4（进行中）：用参考 ERR 与保留图做召回/误报评估与阈值调优。

## 当前评估（group_636_58978，各 200 张抽样）

- 坏图召回：33%（网址 29、价格 11、电商 13、促销 7、中文 4、联系方式 1、二维码 1）
- 保留图误报：2.5%（5/200，均为可辩护命中：价格 2、中文 1、网址 1、邮箱 1）
- 待审核：坏图样本 8%，保留图样本 5%

## 用法

```bash
# dry-run：只出报告，不移动
python -m image_cleaner.runner --input "D:\图片清理\group_636_58978\images"

# 指定批次根目录（自动识别 images 子目录）
python -m image_cleaner.runner --input "D:\图片清理\group_636_58978"

# 小样本调试
python -m image_cleaner.runner --input "D:\图片清理\group_636_58978" --limit 500

# 确认无误后执行移动
python -m image_cleaner.runner --input "D:\图片清理\group_636_58978" --move

# 回退（按移动日志把文件移回原位）
python -m image_cleaner.undo --log "D:\图片清理\group_636_58978\clean_report\move_log.jsonl"

# 只跑快检 / 关闭去重 / 忽略断点
python -m image_cleaner.runner --input "..." --no-ocr --no-dedup --force

# 与参考 ERR 对比评估
python -m image_cleaner.evaluate --report "D:\图片清理\group_636_58978\clean_report\report.csv" --reference "D:\图片清理\group_636_58978\ERR"

# 坏图召回抽样（只读）
python tests\probe_err_sample.py "D:\图片清理\group_636_58978\ERR" 200 tests\ocr_cache_probe.jsonl
```

## 输出

- `ERR/`：不合格图片（目标图片文件夹的同级目录）
- `clean_report/report.csv|json`：每张图的决策、规则、证据、特征
- `clean_report/review.csv`：待人工确认清单（拿不准的图不移动）
- `clean_report/move_plan.txt`：dry-run 时的待移动清单
- `clean_report/move_log.jsonl`：移动日志（可回退）
- `clean_report/checkpoint.json`：断点续传
- `clean_report/ocr_cache.jsonl`：OCR 结果缓存（重跑不重复识别）

所有阈值集中在 `image_cleaner/config.py`，可根据参考 ERR 与人工纠正迭代调整。
