# -*- coding: utf-8 -*-
"""规则引擎：文件级/图像级快检 + OCR 文本规则。

输入特征 → 决策：
  MOVE   —— 高置信命中删除规则，可移动
  KEEP   —— 未命中任何删除规则
  REVIEW —— 疑似但拿不准，保留并列入审核清单
"""

from . import config
from . import text_rules


RULE_IDS = {
    "invalid_corrupt": "4-无效图片(损坏/无法解码)",
    "invalid_tiny": "4-无效图片(过小缩略图)",
    "invalid_blank": "4-无效图片(空白/纯色)",
    "invalid_blur": "4-无效图片(严重模糊)",
    "qr": "3-联系方式(二维码)",
    "pure_logo": "7-纯LOGO/商标图片",
    "url": "2-包含网址信息",
    "contact": "3-包含联系方式",
    "price": "6-包含价格信息",
    "promo": "5-促销/免费配送信息",
    "watermark": "9-水印图片",
    "ecommerce": "10-电商网站标识",
    "marketing_overlay": "11-营销水印/卖家横幅",
}


def decide(feats, ocr_lines=None):
    """feats 来自 features.collect_features；ocr_lines 为 [(text, conf), ...]。
    返回 (决策字典, 文本分析结果)。"""
    if not feats.get("ok"):
        return _move(RULE_IDS["invalid_corrupt"], [f"无法解码: {feats.get('error')}"]), {}

    w, h = feats["w"], feats["h"]
    side = min(w, h)
    area = w * h

    if side < config.TINY_MIN_SIDE_MOVE or area < config.TINY_MIN_AREA:
        return _move(RULE_IDS["invalid_tiny"], [f"尺寸过小 {w}x{h}"]), {}

    review_evidence = []
    qr_texts = feats.get("qr_texts") or []
    if qr_texts:
        review_evidence.append(f"检测到二维码(按用户口径待确认): {qr_texts[0][:40]}")

    if side < config.TINY_MIN_SIDE_REVIEW:
        review_evidence.append(f"尺寸偏小 {w}x{h}")

    stats = feats.get("stats") or {}
    std = stats.get("lum_std")
    uniform = stats.get("uniform_pct")
    if (
        std is not None
        and std < config.BLANK_LUM_STD_MOVE
        and uniform is not None
        and uniform >= config.BLANK_UNIFORM_PCT
    ):
        return _move(
            RULE_IDS["invalid_blank"],
            [f"纯色/空白图 std={std:.2f} uniform={uniform:.2%}"],
        ), {}
    if (
        std is not None
        and std < config.BLANK_LUM_STD_REVIEW
        and uniform is not None
        and uniform >= config.BLANK_REVIEW_UNIFORM_PCT
    ):
        review_evidence.append(f"疑似纯色/空白 std={std:.2f}")

    if config.ENABLE_BLUR_RULE:
        lap = feats.get("blur_var")
        if lap is not None:
            if lap < config.BLUR_LAP_VAR_MOVE:
                review_evidence.append(f"严重模糊 lap_var={lap:.1f}")
                if config.MOVE_ON_SEVERE_BLUR:
                    return _move(RULE_IDS["invalid_blur"], review_evidence), {}
            elif lap < config.BLUR_LAP_VAR_REVIEW:
                review_evidence.append(f"疑似模糊 lap_var={lap:.1f}")

    text_analysis = {}
    if ocr_lines:
        text_analysis = text_rules.analyze(ocr_lines)
        review_evidence += _text_evidence(text_analysis)

    hard = _text_hard_move(text_analysis)
    if hard:
        return hard, text_analysis

    logo_reason = _visual_logo(feats, text_analysis)
    if logo_reason:
        return _move(RULE_IDS["pure_logo"], [logo_reason]), text_analysis

    if review_evidence:
        if config.REVIEW_AS_MOVE:
            return _move("待确认(不确定即移动)", _dedup(review_evidence)), text_analysis
        return {
            "decision": "REVIEW",
            "rule": "待审核",
            "evidence": _dedup(review_evidence),
            "score": 0.5,
        }, text_analysis
    return {"decision": "KEEP", "rule": "-", "evidence": [], "score": 0.0}, text_analysis


def _visual_logo(feats, ta):
    """纯 LOGO / 品牌图 启发式（规则 7）：文字简短 + 色彩很少 → 直接移动（用户已确认）。"""
    stats = feats.get("stats") or {}
    ncolors = stats.get("ncolors16")
    texts = (ta or {}).get("texts") or []
    total_len = sum(len(t) for t in texts)
    if ncolors is not None and ncolors <= 4 and texts and total_len <= 60:
        return f"纯LOGO/品牌图（文字简短、色彩少 ncolors={ncolors}）"
    return None


def _text_evidence(ta):
    """文本规则产生的“待审核”证据（拿不准的情况）。"""
    ev = []
    if ta.get("watermark_weak"):
        ev.append(f"疑似水印(弱信号): {ta['watermark_weak'][:3]}")
    if ta.get("marketing_weak"):
        ev.append(f"疑似营销横幅(弱信号): {ta['marketing_weak'][:3]}")
    return ev


def _text_hard_move(ta):
    """文本规则硬信号 → MOVE。"""
    if not ta:
        return None
    if ta.get("urls"):
        if _url_with_marketing(ta):
            return _move(RULE_IDS["url"], [f"营销类网址/域名: {ta['urls'][:3]}"])
        return None
    if ta.get("contacts"):
        return _move(RULE_IDS["contact"], [f"联系方式: {ta['contacts'][:3]}"])
    if ta.get("prices"):
        return _move(RULE_IDS["price"], [f"价格信息: {ta['prices'][:3]}"])
    if ta.get("promos"):
        return _move(RULE_IDS["promo"], [f"促销宣传: {ta['promos'][:3]}"])
    if ta.get("ecommerce"):
        return _move(RULE_IDS["ecommerce"], [f"电商平台: {ta['ecommerce'][:3]}"])
    if ta.get("watermarks"):
        return _move(RULE_IDS["watermark"], [f"水印关键词: {ta['watermarks'][:3]}"])
    if ta.get("marketing_overlay"):
        return _move(RULE_IDS["marketing_overlay"], [f"营销水印/卖家横幅: {ta['marketing_overlay'][:3]}"])
    return None


def _url_with_marketing(ta):
    """网址是否伴随营销/硬信号（促销/电商/价格/联系方式/水印）——是则判移动，否则视为厂家网址待确认。"""
    return any(ta.get(k) for k in ("promos", "promo_weak", "ecommerce", "prices", "contacts", "watermarks"))


def _dedup(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _move(rule, evidence):
    return {"decision": "MOVE", "rule": rule, "evidence": evidence, "score": 1.0}
