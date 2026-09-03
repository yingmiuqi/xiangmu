# -*- coding: utf-8 -*-
"""文本规则快速自测：python tests/test_text_rules.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from image_cleaner.text_rules import analyze


CASES = [
    # (行文本, 置信度, 期望命中的键)
    ("Product Parameters", 0.95, ("keep_terms",)),
    ("Length: 120mm", 0.9, ("keep_terms",)),
    ("www.ebay.com FREE SHIPPING", 0.9, ("urls", "promos", "ecommerce")),
    ("联系电话：13800138000", 0.9, ("contacts",)),
    ("厂家直销 现货供应", 0.85, ("watermarks",)),
    ("$99 Only", 0.9, ("prices",)),
    ("USD 99 Special Price", 0.9, ("prices", "promos")),
    ("contact@example.com", 0.9, ("contacts",)),
    ("型号对照表 Part No. 12345", 0.85, ("keep_terms",)),
    ("Specification Sheet", 0.95, ("keep_terms",)),
    ("Dealmed Latex Exam Gloves", 0.9, ()),
    ("SAVE button on device", 0.9, ()),
    ("Phone Call feature", 0.9, ()),
    ("sharpie marker", 0.9, ()),
    ("Only $99", 0.9, ("prices",)),
    ("微信号：abc123", 0.85, ("contacts",)),
    ("free delivery", 0.9, ("promos",)),
    ("FREESHIPPING", 0.9, ("promos",)),
    ("SHIPPING USA SELLER GLOBALPARTSZONE", 0.9, ()),
    ("PartsNumber QTY Description", 0.9, ("keep_terms",)),
    ("可贝", 0.9, ()),                                    # 中文规则已删除
    ("の下插 防 滑 耐久性", 0.9, ()),
    ("$0100120-18P", 0.9, ()),
    ("contact us within 30 days", 0.9, ()),
    ("FEL-PRO MFG.CO instructions", 0.9, ()),
    ("USA STOCK FAST SHIPPING", 0.9, ()),
    ("@Copyright 2024", 0.9, ("watermark_weak",)),
    ("tel:1741-15-8699", 0.9, ("contacts",)),
    ("11910015791", 0.9, ()),                             # 零件号裸数字：完全忽略
    ("1-800-243-5135", 0.9, ("contact_weak",)),           # 美式带分隔符：按弱信号处理
    ("www.gmgoodwrench.com Genuine GM parts", 0.9, ("urls",)),
    ("TWO WAREHOUSES U.S.SELLER", 0.9, ("marketing_overlay",)),
    ("Authorized Dealer Official Stockist", 0.9, ("marketing_overlay",)),
    ("FASTER SHIPPING FASTDELIVERY", 0.9, ("marketing_overlay",)),
]


def main():
    lines = [(t, c) for t, c, _ in CASES]
    r = analyze(lines)
    print("urls:", r["urls"])
    print("contacts:", r["contacts"])
    print("contact_weak:", r["contact_weak"])
    print("prices:", r["prices"])
    print("promos:", r["promos"])
    print("ecommerce:", r["ecommerce"])
    print("watermarks:", r["watermarks"])
    print("watermark_weak:", r["watermark_weak"])
    print("marketing_overlay:", r["marketing_overlay"])
    print("keep_terms:", r["keep_terms"])

    failed = []
    for text, conf, expected in CASES:
        rr = analyze([(text, conf)])
        for key in expected:
            if not rr[key]:
                failed.append((text, key))
        for key in ("urls", "contacts", "prices", "promos", "ecommerce", "watermarks"):
            if key not in expected and rr[key]:
                failed.append((text, f"unexpected {key}={rr[key]}"))
        if "FAST SHIPPING" in text and rr.get("promo_weak"):
            failed.append((text, "fast shipping 不应触发弱促销"))
        if "MFG.CO" in text and rr.get("urls"):
            failed.append((text, f"MFG.CO 不应判为网址: {rr['urls']}"))
    if failed:
        print("\nFAIL:", failed)
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
