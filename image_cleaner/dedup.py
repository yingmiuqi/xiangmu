# -*- coding: utf-8 -*-
"""指纹去重：MD5 精确指纹（对齐参考工具的 md5_cache 机制）。
同指纹图片中只要有一张判定不合格，其余全部联动移动。"""

import hashlib


def md5_of(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class Deduper:
    def __init__(self):
        self._cache = {}

    def fingerprint(self, path):
        if path not in self._cache:
            try:
                self._cache[path] = md5_of(path)
            except OSError:
                self._cache[path] = None
        return self._cache[path]

    @staticmethod
    def propagate(rows):
        """rows: 每行含 _path、_md5、决策。同 _md5 组内若存在 MOVE，
        其余行（KEEP/REVIEW）改为 MOVE（指纹联动）。返回被联动改判的数量。"""
        groups = {}
        for r in rows:
            fp = r.get("_md5")
            if fp:
                groups.setdefault(fp, []).append(r)
        changed = 0
        for fp, members in groups.items():
            if len(members) < 2:
                continue
            if any(m.get("决策") == "MOVE" for m in members):
                for m in members:
                    if m.get("决策") != "MOVE":
                        m["决策"] = "MOVE"
                        m["规则"] = "重复图片(指纹联动)"
                        m["证据"] = [f"与同指纹图片联动（MD5 {fp[:12]}…）"]
                        m["得分"] = 1.0
                        changed += 1
        return changed
