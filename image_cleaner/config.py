# -*- coding: utf-8 -*-
"""集中配置：阈值、关键词、路径规则。

所有可调参数都在这里，方便根据参考 ERR 结果和人工纠正迭代调优。
"""

import os

# 支持的图片扩展名（主目标为 WebP，保留常见格式以兼容历史批次）
IMAGE_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".avif")

# 扫描时需要跳过的目录名（不区分大小写）
SKIP_DIR_NAMES = {
    ".cache_thumbs",
    "err",
    "err(1)",
    "watermark_output",
    "clean_report",
    "output",
    "visualized",
    "review",
}

# ---------------------------------------------------------------------------
# 规则 4：无效图片（文件级/图像级快检）
# ---------------------------------------------------------------------------
TINY_MIN_SIDE_MOVE = 80        # 短边 < 该值 → 过小缩略图，直接移动
TINY_MIN_SIDE_REVIEW = 150     # 短边 < 该值 → 偏小，进待审核
TINY_MIN_AREA = 8_000          # 宽*高 < 该值 → 直接移动

BLANK_LUM_STD_MOVE = 5.0       # 亮度标准差 < 该值 且 均匀度达标 → 纯色/空白，直接移动
BLANK_LUM_STD_REVIEW = 7.0     # 亮度标准差 < 该值 且 均匀 → 疑似纯色，进待审核
BLANK_UNIFORM_PCT = 0.97       # 与亮度均值差异 < 6 的像素占比 >= 该值视为均匀
BLANK_REVIEW_UNIFORM_PCT = 0.90

# 模糊规则：实测该指标在保留图/坏图间没有区分度，里程碑 1 默认关闭，
# 仅保留 blur_var 作为报告特征。后续换用更好的对焦指标再开启。
ENABLE_BLUR_RULE = False
BLUR_LAP_VAR_MOVE = 8.0        # 拉普拉斯方差 < 该值 → 严重模糊
BLUR_LAP_VAR_REVIEW = 15.0     # 拉普拉斯方差 < 该值 → 疑似模糊
MOVE_ON_SEVERE_BLUR = False    # 默认严重模糊只进审核，不直接移动（可调）

# ---------------------------------------------------------------------------
# OCR 文本规则（里程碑 2）
# ---------------------------------------------------------------------------
OCR_LANG = "ch"                # PaddleOCR 语言，ch 同时覆盖中英文
OCR_CONF_MIN = 0.55            # OCR 文本参与判定的最低置信度
OCR_MAX_LINES = 60             # 单图最多参与判定的文本行数（防性能抖动）

# OCR 运行目录重定向到 D 盘（避开 C 盘空间；注意：路径不能含中文，
# Paddle 原生库不支持非 ASCII 路径，所以不用项目目录 D:\图片清理\...）
OCR_TEMP_DIR = r"D:\ocr_tmp"        # 进程临时目录
OCR_MODEL_DIR = r"D:\ocr_models"    # PaddleOCR 模型目录

# 规则 2：网址 / 域名 / URL
URL_PATTERNS = (
    r"https?://[^\s，。；、\"'<>()]+",
    r"(?:^|\s)www\.[\w\-]+(?:\.[\w\-]+)+",
    r"(?:^|[^a-z0-9@])[\w\-]+\.(?:com\.cn|com|cn|net|org|io|co|cc|biz|info|shop|store|online|xyz|top|vip|club|site|me|us)(?:\b|[/\s])",
)

# 规则 3：联系方式（关键词 + 正则）
CONTACT_KEYWORDS = (
    "微信", "微信号", "wechat", "weixin",
    "qq号",
    "电话", "手机", "联系电话",
    "邮箱",
    "toll free",
)
# 弱联系方式信号：单独出现时进审核（如退货政策里的 contact us）
CONTACT_WEAK_KEYWORDS = (
    "contact us", "联系我们", "qq",
    "whatsapp", "whats app", "telegram", "facebook", "instagram", "twitter", "youtube",
)
PHONE_PATTERNS = (
    r"\+\d{1,3}[- ]?\d{5,14}\b",                         # 国际号码
    r"(?:tel|phone|mobile|电话|手机|contact)[:：\s]*[\d\- .]{7,18}",
)
# 弱电话信号：零件号/年份区间/裸数字容易误判，只进审核
PHONE_WEAK_PATTERNS = (
    r"\b1[3-9]\d{9}\b",                                  # 中国大陆手机号（裸数字）
    r"\b1[-.]\d{3}[-.]\d{3}[-.]\d{4}\b",                 # 美式 1-xxx-xxx-xxxx（需带分隔符）
    r"\b\d{3}[-.]\d{3}[-.]\d{4}\b",                      # xxx-xxx-xxxx
)
# 确认是美式电话的弱信号 → 直接移动（用户口径）
US_PHONE_MOVE_PATTERNS = (
    r"\b1[-.]\d{3}[-.]\d{3}[-.]\d{4}\b",
    r"\b\d{3}[-.]\d{3}[-.]\d{4}\b",
)
EMAIL_PATTERNS = (r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",)
QQ_PATTERNS = (r"(?:qq|扣扣)[:：\s]*[1-9]\d{4,11}\b",)

# 规则 5：促销 / 免费配送 / 营销
PROMO_KEYWORDS = (
    "free shipping", "free design", "free sample", "free delivery",
    "special price", "hot sale", "best price",
    "促销", "优惠", "特价", "包邮", "免运费", "免费", "打折",
)
PROMO_PATTERNS = (
    r"(?<![a-z0-9])free\s*shipping(?![a-z0-9])",
    r"(?<![a-z0-9])free\s*delivery(?![a-z0-9])",
    r"(?<![a-z0-9])free\s*sample(?![a-z0-9])",
    r"(?<![a-z0-9])free\s*design(?![a-z0-9])",
    r"(?<![a-z0-9])free\s*gift(?![a-z0-9])",
    r"(?<![a-z0-9])special\s*price(?![a-z0-9])",
    r"(?<![a-z0-9])hot\s*sale(?![a-z0-9])",
    r"(?<![a-z0-9])best\s*price(?![a-z0-9])",
)
# 弱促销信号：单独出现时只进审核（如“SHIPPING”“seller”横幅，避免误伤规格文字）
PROMO_WEAK_KEYWORDS = (
    "shipping", "seller", "worldwide", "ships from", "we ship", "ships to",
    "us seller", "save big", "buy now", "order now", "click here",
    "limited offer", "act now", "don't miss", "ukseller", "uk seller",
    "shipment", "ships worldwide", "ship from", "selling", "welcome to",
    "visit our", "our store", "clearance", "limited time",
)
# 出现这些短语时，弱促销信号不再触发（用户口径：只有 free shipping 才移动）
PROMO_IGNORE_PHRASES = (
    "fast shipping", "fast delivery", "same day shipping", "quick shipping",
    "expedited shipping", "fast stock shipping",
)

# 营销水印/卖家横幅（用户抽查后手动移动的高频特征；误报率实测 ~0.3%，命中即移动）
MARKETING_OVERLAY_PATTERNS = (
    r"faster\s*shipping",
    r"fastershipping",
    r"faster\s*delivery",
    r"fastdelivery",
    r"two\s*warehouses",
    r"u\.?\s*s\.?\s*seller",
    r"us\s*seller",
    r"authorized\s*dealer",
    r"official\s*stockist",
    r"\bstockist\b",
    r"contact\s*seller",
    r"contactseller",
    r"picture will be uploaded",
    r"uploaded shortly",
    r"uploaded soon",
    r"\bdealer\b",
    r"genuine\s*parts",
    r"questions\?",
    r"fitment\s*chart",
)
# 弱营销信号（不准直接移动，进审核清单）：实测 warehouse/catalog 真伪各半
MARKETING_OVERLAY_WEAK_PATTERNS = (
    r"\bwarehouse\b",
    r"\bcatalog\b",
)

# 规则 6：价格（only/just 必须带货币符号，避免把"only 3 件"这类数量误判为价格）
PRICE_PATTERNS = (
    r"[$￥¥]\s?\d[\d,]*(?:\.\d+)?",
    r"\bUSD\s?\d[\d,.]*",
    r"\b\d[\d,.]*\s?(?:USD|EUR|GBP|RMB|CNY)\b",
    r"\bprice\s*[:：]?\s*[$￥¥]?\s?\d",
    r"\b(?:only|just)\s*[:：]?\s*[$￥¥]\s?\d",
)

# 规则 9：水印关键词（含 PDF 示例：厂家直销/质量保证/现货供应 等）
WATERMARK_KEYWORDS = (
    "厂家直销", "质量保证", "现货供应", "样张", "样图", "水印", "版权", "原创",
    "禁止转载", "未经允许", "盗图必究", "摄影", "供图", "视觉中国", "图虫",
    "站酷", "lofter", "小红书", "微博", "抖音", "快手", "bilibili", "知乎",
    "网易", "腾讯", "新浪", "搜狐", "图虫创意", "东方ic", "全景", "摄图网",
    "千图网", "昵图网", "包图网",
    "watermark", "gettyimages", "shutterstock",
    "adobe stock", "istock", "dreamstime", "alamy", "depositphotos",
    "draft", "preview", "bigstock", "canstock", "fotolia",
    "pond5", "123rf", "pixabay", "unsplash", "pexels", "freepik",
)
# 弱水印信号：copyright/sample 等常见于产品图版权小字/样品字样，只进审核
WATERMARK_WEAK_KEYWORDS = ("copyright", "sample")

# 规则 10：国内外电商平台
E_COMMERCE_KEYWORDS = (
    "ebay", "amazon", "alibaba", "aliexpress", "dhgate", "1688",
    "taobao", "淘宝", "天猫", "tmall", "京东", "jd.com", "拼多多", "pinduoduo",
    "shopify", "wish", "etsy",
    "positive feedback", "top-rated seller", "member since", "add to cart",
    "buy it now", "customer reviews",
)

# 保留词表（常见误判：参数/规格/尺寸/图纸/型号对照 等，命中则不因“英文文字”移动）
KEEP_LEXICON = (
    "product parameters", "technical specification", "specification sheet",
    "specifications", "parameters", "parameter",
    "length", "width", "height", "dimension", "dimensions", "size",
    "part no", "part number", "model no", "model number", "reference number",
    "material", "color", "colour", "weight", "capacity", "voltage", "power",
    "installation", "assembly", "exploded view", "drawing", "cad", "blueprint",
    "fitment", "compatible", "oem", "partsnumber", "parts number", "parts list",
    "qty", "bill of materials", "diameter", "shaft length", "available in",
    "availablein",
    "参数", "规格", "尺寸", "型号", "图纸", "结构图", "爆炸图", "零件图",
    "装配图", "工程图", "技术图",
)

# ---------------------------------------------------------------------------
# 规则 3：二维码（本地 OpenCV 检测）
# ---------------------------------------------------------------------------
ENABLE_QR_DETECT = True

# 水印识别模型（视觉水印/商标/营销图）
WATERMARK_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "watermark_model.pth"
)
# 水印模型（v10 最终档，2026-08-29 用户定案：综合均衡 + 中分段全部移动）：
# MOVE ≥0.3（中分段 0.3~0.5 不再留审核，全部移动）→ 全量精确率 0.815 / 召回率 0.911
# 0.15~0.3 低分段 → 待审核清单（人工确认后回流训练）
WATERMARK_MODEL_MOVE_THRESHOLD = 0.3
WATERMARK_MODEL_REVIEW_THRESHOLD = 0.15

# 用户口径（2026-08-21）：恢复“待审核”档——不确定的图列清单不移动；
# 明确规则命中的才移动。模型：≥0.9 移动，0.5~0.9 待审核。
REVIEW_AS_MOVE = False

# 参照库：与库中图片相似度 >98% 才移动（用户口径 2026-08-27，原为 95%）
ENABLE_REF_LIB = True
REF_SIM_THRESHOLD = 0.98
REF_LIB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "ref_lib.json"
)

# ---------------------------------------------------------------------------
# 软信号评分（预留：纯 LOGO / 无产品实图等评分类规则）
# ---------------------------------------------------------------------------
SOFT_MOVE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# 输出目录
# ---------------------------------------------------------------------------
ERR_DIR_NAME = "ERR"
REPORT_DIR_NAME = "clean_report"
USER_DECISIONS_FILE = "审核结果.csv"   # 用户审核记录，运行时自动套用（保留/移动）
