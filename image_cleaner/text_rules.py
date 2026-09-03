# -*- coding: utf-8 -*-
"""OCR 文本规则：网址 / 联系方式 / 价格 / 促销 / 水印 / 电商 + 保留词。

英文关键词一律按单词边界匹配，避免“deal→dealmed、rf→performance”这类误命中；
中文关键词按子串匹配。
"""

import re

from . import config


def _norm(t):
    return t.lower().strip()


def _kw_regex(keywords):
    """把关键词列表编译成 (is_chinese, 关键词, 正则) 列表。"""
    out = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if re.search(r"[\u4e00-\u9fff]", kw):
            out.append((True, kw, None))
        else:
            pat = re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")
            out.append((False, kw, pat))
    return out


_CONTACT = _kw_regex(config.CONTACT_KEYWORDS)
_CONTACT_WEAK = _kw_regex(config.CONTACT_WEAK_KEYWORDS)
_PROMO = _kw_regex(config.PROMO_KEYWORDS)
_PROMO_WEAK = _kw_regex(config.PROMO_WEAK_KEYWORDS)
_ECOMM = _kw_regex(config.E_COMMERCE_KEYWORDS)
_WATER = _kw_regex(config.WATERMARK_KEYWORDS)
_WATER_WEAK = _kw_regex(config.WATERMARK_WEAK_KEYWORDS)
_KEEP = _kw_regex(config.KEEP_LEXICON)


def _match_keywords(norm, items):
    hits = []
    for is_cn, kw, pat in items:
        if is_cn:
            if kw in norm:
                hits.append(kw)
        else:
            if pat.search(norm):
                hits.append(kw)
    return hits


def analyze(lines):
    """lines: [(text, conf), ...]
    返回 {urls, contacts, contact_weak, prices, promos, promo_weak,
          ecommerce, watermarks, watermark_weak, keep_terms, texts}。
    """
    res = {
        "urls": [],
        "contacts": [],
        "contact_weak": [],
        "prices": [],
        "promos": [],
        "promo_weak": [],
        "ecommerce": [],
        "watermarks": [],
        "watermark_weak": [],
        "marketing_overlay": [],
        "marketing_weak": [],
        "keep_terms": [],
        "texts": [],
    }
    high = []
    for text, conf in lines[: config.OCR_MAX_LINES]:
        if conf >= config.OCR_CONF_MIN:
            high.append((text, conf))

    for t, conf in high:
        norm = _norm(t)
        res["texts"].append(t[:120])

        for pat in config.URL_PATTERNS:
            for m in re.findall(pat, norm):
                m = m.strip()
                if not _company_abbrev(m):
                    res["urls"].append(m[:80])
        for pat in config.EMAIL_PATTERNS:
            for m in re.findall(pat, norm):
                res["contacts"].append(m[:80])
        for pat in config.PHONE_PATTERNS:
            for m in re.findall(pat, norm):
                if not _looks_placeholder(m):
                    res["contacts"].append(m.strip()[:80])
        for pat in config.PHONE_WEAK_PATTERNS:
            for m in re.findall(pat, norm):
                if not _looks_placeholder(m):
                    res["contact_weak"].append(m.strip()[:80])
        for pat in config.US_PHONE_MOVE_PATTERNS:
            for m in re.findall(pat, norm):
                if not _looks_placeholder(m):
                    res["contacts"].append(m.strip()[:80])
        for pat in config.QQ_PATTERNS:
            for m in re.findall(pat, norm):
                res["contacts"].append(m.strip()[:80])
        for pat in config.PRICE_PATTERNS:
            for m in re.findall(pat, norm, flags=re.IGNORECASE):
                if not _part_number_like(m):
                    res["prices"].append(m.strip()[:80])
        for pat in config.PROMO_PATTERNS:
            for m in re.findall(pat, norm, flags=re.IGNORECASE):
                res["promos"].append(m.strip()[:80])
        for pat in config.MARKETING_OVERLAY_PATTERNS:
            for m in re.findall(pat, norm):
                res["marketing_overlay"].append(m.strip()[:80])
        for pat in getattr(config, "MARKETING_OVERLAY_WEAK_PATTERNS", ()):
            for m in re.findall(pat, norm):
                res["marketing_weak"].append(m.strip()[:80])

        res["contacts"] += _match_keywords(norm, _CONTACT)
        res["contact_weak"] += _match_keywords(norm, _CONTACT_WEAK)
        res["promos"] += _match_keywords(norm, _PROMO)
        if not any(p in norm for p in config.PROMO_IGNORE_PHRASES):
            res["promo_weak"] += _match_keywords(norm, _PROMO_WEAK)
        res["ecommerce"] += _match_keywords(norm, _ECOMM)
        res["watermarks"] += _match_keywords(norm, _WATER)
        res["watermark_weak"] += _match_keywords(norm, _WATER_WEAK)
        res["keep_terms"] += _match_keywords(norm, _KEEP)

    for key in ("urls", "contacts", "contact_weak", "prices", "promos", "promo_weak",
                "ecommerce", "watermarks", "watermark_weak", "marketing_overlay",
                "marketing_weak", "keep_terms"):
        seen = set()
        res[key] = [x for x in res[key] if not (x in seen or seen.add(x))]
    return res


def _looks_placeholder(s):
    """识别模板占位电话（如 1234567890、0000000000），不算真实联系方式。"""
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 7:
        return True
    if digits in ("1234567890", "0123456789", "9876543210", "0987654321"):
        return True
    uniq = set(digits)
    if len(uniq) <= 2:
        return True
    seq = all(int(b) == int(a) + 1 for a, b in zip(digits, digits[1:]))
    seq_r = all(int(a) == int(b) + 1 for a, b in zip(digits, digits[1:]))
    return seq or seq_r


def _part_number_like(s):
    """价格规则排除零件号：$ 开头 + 7 位以上数字且无小数点（如马自达零件号 $0100120）。"""
    digits = "".join(ch for ch in s if ch.isdigit())
    return len(digits) > 6 and "." not in s


def _company_abbrev(s):
    """厂商缩写误判为域名：MFG.CO / INC.CO 等。"""
    low = s.lower().rstrip("/.")
    label = low.rsplit(".", 1)[0] if "." in low else ""
    return label in {"mfg", "inc", "ltd", "llc", "corp", "co", "intl", "etc", "org"}
