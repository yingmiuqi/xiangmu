# 图片清洗规则说明书（当前版本）

> 依据《图片数据清洗操作说明》实现。所有阈值可在 `image_cleaner/config.py` 中调整。
> 判定分三级：**MOVE**（建议移入 ERR）/ **REVIEW**（保留原位置、进入待审核清单）/ **KEEP**（保留）。

## 决策优先级

1. 快检硬信号（损坏 / 过小 / 纯色 / 二维码）→ MOVE
2. 文本硬信号，按顺序命中即 MOVE：网址 → 联系方式 → 价格 → 促销 → 电商 → 水印 → 中文
3. REVIEW 信号：中文 + 保留词、1~2 个中文字符、低置信中文、弱促销词、疑似纯 LOGO
4. 其余 → KEEP

## 规则明细

### 规则 1：包含中文内容
- MOVE：OCR 检出 **≥3 个汉字且置信度 ≥ 0.85**（明确大量中文直接移动；用户已确认）
- REVIEW：检出 **2 个汉字** 或 3 个以上但置信度不足；中文同时命中保留词表
- 忽略：**1 个汉字**（实测基本是 OCR 误识别，如“高/主/元/田/长/心”）
- 阈值：`OCR_CONF_MIN=0.55`；低于该置信度的中文只记“低置信中文”进 REVIEW
- Q1 已确认：带中文的商品介绍图移动，前提是确实识别出中文；少量/不确定时先询问

### 规则 2：包含网址信息
- MOVE：命中任一 URL 正则（`http(s)://`、`www.` 开头、域名 + TLD 列表如 .com/.cn/.net/...）
- 域名白名单严格限定 TLD，避免把型号编号当域名

### 规则 3：包含联系方式
- MOVE：
  - 邮箱正则（`xxx@yyy.zzz`）
  - 手机号（`1[3-9]` 开头 11 位）、国际号码（+ 开头）
  - 座机（必须带 tel/电话/contact 等上下文，避免把 0 开头的零件号当电话）
  - 美式号码（1-800-243-5135、1.888.369.7942、(xxx)xxx-xxxx）
  - “tel/phone/mobile/电话/手机/contact + 数字串”组合
  - 强关键词：微信 / 微信号 / wechat / weixin / qq / 扣扣 / 邮箱 / whatsapp / facebook / instagram / youtube / contact us / 联系我们
  - 二维码（OpenCV 本地检测，检出即 MOVE，无需识别内容）
- 不触发：单独出现的 phone / tel / mobile / email / company 等产品功能词
- **待确认 Q6**：产品界面上的“Phone Call / Email”按钮字样，按现状不会触发，是否认可？

### 规则 4：无效图片
- MOVE：无法解码；短边 < 80px 或面积 < 8000；纯色/空白（亮度标准差 < 5 且均匀度 ≥ 97%）
- REVIEW：短边 < 150px；疑似纯色（标准差 < 7 且均匀度 ≥ 90%）；严重模糊（当前默认只列审核，指标待定）
- **待确认 Q4**：实测“拉普拉斯方差”在坏图/保留图之间没有区分度，严重模糊改用哪种判据？（目前可先全部走审核，或你提供几张典型模糊图）

### 规则 5：促销 / 免费配送
- MOVE：`free shipping / free delivery / free sample / free design / free gift`（含无空格粘连写法，如 FREESHIPPING）；special price / hot sale / limited time / best price / clearance / discount / promotion；中文：促销 / 优惠 / 特价 / 包邮 / 免运费 / 免费 / 打折
- REVIEW（弱营销词）：shipping / seller / ukseller / worldwide / ships from / we ship / save big / buy now / order now / click here / selling / welcome to / visit our / our store 等
- **待确认 Q5**：卖家横幅（如“SHIPPING / USA / SELLER / GLOBALPARTSZONE”）目前只进审核，是否应直接移动？

### 规则 6：价格信息
- MOVE：`$ / ￥ / ¥ + 数字`；`USD/EUR/GBP/RMB/CNY + 数字`；`price / only / just + 数字`

### 规则 7：纯 LOGO / 商标图
- MOVE（用户已确认）：OCR 文本总长 ≤ 60 字符且 16 色量化色彩数 ≤ 4

### 规则 8：无产品实图 / 无意义
- 暂无可靠自动判据，与规则 7 共用启发式，先进 REVIEW
- **待确认 Q8**：是否需要训练一个小分类器（或先全部人工审核这类）

### 规则 9：水印
- MOVE：关键词命中（中文：厂家直销 / 质量保证 / 现货供应 / 样张 / 版权 / 图库平台等；英文：sample / watermark / copyright / gettyimages / shutterstock / adobe stock / istock / dreamstime 等；注意：logo 一词已移出，纯 LOGO 图由规则 7 启发式处理）
- 半透明 / 图形水印启发式得分（watermark_detector 移植）已加入报告列，但实测区分度不足
  （保留图 19% 也达到高分），因此**不用于自动判定**，仅作参考；疑似图形水印的图进待审核由人工确认
- 说明：已删除易误伤词（rf、proof 等），英文词按单词边界匹配

### 规则 10：电商网站标识
- MOVE：ebay / amazon / alibaba / aliexpress / dhgate / 1688 / taobao / 淘宝 / 天猫 / tmall / 京东 / jd.com / 拼多多 / shopify / wish / etsy
- 卖家信息：positive feedback / top-rated seller / member since / add to cart / buy it now / customer reviews

## 保留词表（防误删）

- 英文：product parameters / technical specification / specification sheet / parameters / length / width / height / dimension / size / part no / model no / reference number / material / color / weight / capacity / voltage / power / installation / assembly / exploded view / drawing / cad / blueprint / fitment / oem / partsnumber / qty / diameter / shaft length / available in 等
- 中文：参数 / 规格 / 尺寸 / 型号 / 图纸 / 结构图 / 爆炸图 / 零件图 / 装配图 / 工程图 / 技术图
- 命中保留词：纯英文时 KEEP；若同时含中文 → REVIEW
- Q2 已确认：以 PDF 为准——参数表 / 零件清单类图**允许保留**（样本见“人工审核\参数表-零件清单样本”）
  - 补充口径（用户确认）：保留的前提是**无水印**；带水印（样本 1、3）→ 必须移动

## 去重

- MD5 精确指纹（对齐参考工具的 md5_cache 机制）
- 同一指纹组内只要有 1 张判定 MOVE，其余全部联动 MOVE（规则标注“重复图片(指纹联动)”）

## 学习记录（来自人工审核反馈）

- group_339 抽查反馈（2026-08-15）：被判定移动的图里很多**同时带水印**（电商标、网址、
  FREESHIPPING 横幅等往往与水印叠加）；文本水印可由关键词自动识别，图形/半透明水印仍需人工
  审核或后续训练专门模型。
- 零件号易与电话混淆：0 开头的 9 位数字（如 0263053559）是零件号不是座机，座机判定必须带
  “tel/电话/contact”等上下文。

## 性能

- 快检约 10 张/秒；OCR 约 1~1.5 秒/张（CPU）
- 断点续传 + OCR 缓存，重跑不重复识别
