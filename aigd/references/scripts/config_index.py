# -*- coding: utf-8 -*-
"""配置表索引 + `表[主键].字段` 解析(纯 stdlib,复用 xlsx_dump)。

从 gherkin_to_checklist.py 抽出的共享层,供 gherkin_to_checklist(策划版清单代值)
与 config_check / value_check(校验)共用,避免重复且不拖 openpyxl 进校验器。

- build_index(dir): 扫目录所有 xlsx 所有 sheet → {表英文名: {file, fieldcol, data}}。
- load_enums(枚举字典.md): {枚举名/中文: id},冲突名丢弃(防误代)。
- load_keymap(复合键映射.json): {复合键表: [分量列名…]}。
- lookup(idx, table, keystr, field): 真值 / 'MULTI'(多键枚举需手填) / None(查不到=断链)。
  护栏:单主键数字直查 id/col0;复合键按 keymap 分量列匹配、枚举名经 enums 解;绝不臆造。
"""
import os, re, json, zipfile

import xlsx_dump

REF_RE = re.compile(r"([A-Za-z]\w*)\[([^\]\[]+)\]\.([A-Za-z]\w*)")   # 表[主键].字段


def _array_spans(field_row):
    """简单列表数组(`field[ … ]`)→ {base: [数据列下标]}。对象数组(`[{…}]`)跳过。"""
    spans = {}
    base, cols = None, []
    for ci in range(len(field_row)):
        k = (field_row[ci] or "").strip() if field_row[ci] is not None else ""
        if base is not None:
            if "]" in k and "{" not in k:          # 闭合标记列(无数据)
                spans[base] = cols; base, cols = None, []
                continue
            if k == "":
                cols.append(ci); continue
            spans[base] = cols; base, cols = None, []   # 提前遇新字段 → 收尾(尾随数组)
        if "[" in k and "{" not in k:
            b = re.split(r"[\[.]", k)[0].strip()
            if b:
                base, cols = b, [ci]
                if "]" in k:                        # 自闭合
                    spans[b] = cols; base, cols = None, []
    if base is not None:
        spans[base] = cols
    return spans


def build_index(config_dir):
    """扫配置目录所有 xlsx 的所有 sheet,建 表英文名 → {file, fieldcol, arraycols, data}。
    自描述表头:行1=表名,行3=字段key(数组 field[ 也按裸名注册),行5+=数据。"""
    idx = {}
    for fn in sorted(os.listdir(config_dir)):
        if not fn.lower().endswith(".xlsx") or fn.startswith("~$"):
            continue
        path = os.path.join(config_dir, fn)
        try:
            z = zipfile.ZipFile(path)
            shared = xlsx_dump.load_shared_strings(z)
            for name, sp in xlsx_dump.sheet_map(z):
                rows = xlsx_dump.read_rows(z, sp, shared, None)
                if len(rows) < 5:
                    continue
                table = (rows[0][0] or "").strip()
                if not table or not re.match(r"^[A-Za-z]\w*$", table):
                    continue
                fieldcol = {}
                for ci, k in enumerate(rows[2]):
                    k = (k or "").strip()
                    if not k:
                        continue
                    if k not in fieldcol:
                        fieldcol[k] = ci
                    base = re.split(r"[\[.]", k)[0]    # 数组/对象字段 member[ / jump.x → 裸名也注册
                    if base and base not in fieldcol:
                        fieldcol[base] = ci
                idx[table] = {"file": fn, "fieldcol": fieldcol,
                              "arraycols": _array_spans(rows[2]), "data": rows[4:]}
            z.close()
        except Exception:
            continue
    return idx


def load_enums(path):
    """解 枚举字典.md 的 markdown 表 → {枚举名/中文: id}。冲突名丢弃(防误代)。"""
    enums, ambig = {}, set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2 or not re.fullmatch(r"\d+", cells[0]):
                continue
            idv = cells[0]
            for nm in cells[1:3]:
                if nm and not re.fullmatch(r"[-:\s]+", nm) and not re.fullmatch(r"\d+", nm):
                    if nm in enums and enums[nm] != idv:
                        ambig.add(nm)
                    else:
                        enums.setdefault(nm, idv)
    for a in ambig:
        enums.pop(a, None)
    return enums


def load_keymap(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_")}   # 丢注释键


def _cell(row, fc):
    if fc < len(row):
        v = str(row[fc]).strip()
        return v if v != "" else None
    return None


def _resolve_key(k, enums):
    """key → 用于匹配列的 id 串(数字原样;枚举名→id;解不出 None)。"""
    if re.fullmatch(r"-?\d+", k):
        return k
    return enums.get(k)


def _find_row(idx, table, keystr):
    """按主键命中一行 → row / 'MULTI'(多键枚举需手填) / None(无此行)。复合键按分量列匹配。"""
    t = idx.get(table)
    if not t:
        return None
    enums = idx.get("__enums__", {}) or {}
    keymap = idx.get("__keymap__", {}) or {}
    keys = [k.strip() for k in keystr.split(",")]
    if len(keys) == 1 and re.fullmatch(r"-?\d+", keys[0]):
        k = keys[0]
        keycols = ([t["fieldcol"]["id"]] if "id" in t["fieldcol"] else []) + [0]
        for row in t["data"]:
            if any(kc < len(row) and str(row[kc]).strip() == k for kc in keycols):
                return row
        return None
    cols = keymap.get(table)
    if not cols or len(cols) != len(keys):
        return "MULTI"
    colidx = []
    for ck in cols:
        ci = t["fieldcol"].get(ck)
        if ci is None:
            return None
        colidx.append(ci)
    resolved = []
    for k in keys:
        rk = _resolve_key(k, enums)
        if rk is None:
            return "MULTI"
        resolved.append(rk)
    for row in t["data"]:
        if all(ci < len(row) and str(row[ci]).strip() == resolved[j] for j, ci in enumerate(colidx)):
            return row
    return None


def lookup(idx, table, keystr, field):
    """真值字符串 / 'MULTI'(需手填) / None(查不到=断链 或 字段空)。复合键按分量列多列匹配。"""
    row = _find_row(idx, table, keystr)
    if row == "MULTI":
        return "MULTI"
    if row is None:
        return None
    fc = idx[table]["fieldcol"].get(field)
    return _cell(row, fc) if fc is not None else None


def row_exists(idx, table, keystr):
    """主键是否命中一行(不看字段值)。True / False / None(MULTI 无法判定 或 表不在)。
    用于区分『引用悬空(行不存在)』与『字段值为空(可选字段)』,避免把空值误报成断链。"""
    row = _find_row(idx, table, keystr)
    if row == "MULTI" or (row is None and table not in idx):
        return None
    return row is not None


def column_values(idx, table, field):
    """表某列全部非空值(字符串集合)。用于外键校验(目标列取值域)。"""
    t = idx.get(table)
    if not t:
        return None
    fc = t["fieldcol"].get(field)
    if fc is None:
        return None
    out = set()
    for row in t["data"]:
        v = _cell(row, fc)
        if v is not None:
            out.add(v)
    return out


def array_column_values(idx, table, base):
    """数组字段(`base[ … ]`)跨所有行的全部成员值(非空)。None=表/数组列不存在。
    用于逐成员外键校验(如 evolveLine.member[] 每个 id ∈ unit.id)。"""
    t = idx.get(table)
    if not t:
        return None
    cols = t.get("arraycols", {}).get(base)
    if not cols:
        return None
    out = set()
    for row in t["data"]:
        for c in cols:
            v = _cell(row, c)
            if v is not None:
                out.add(v)
    return out
