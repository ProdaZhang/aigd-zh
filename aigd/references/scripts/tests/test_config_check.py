# -*- coding: utf-8 -*-
"""config_check.py 测试 —— 纯 stdlib(逻辑层用内存夹具,不落 xlsx 文件;表/字段名均为示意)。
跑法: python test_config_check.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config_check as C


# ---------- parse_domain ----------

def test_parse_domain_enum():
    assert C.parse_domain("0/1") == ("enum", {0, 1})
    assert C.parse_domain("50/100/150/200") == ("enum", {50, 100, 150, 200})

def test_parse_domain_range():
    assert C.parse_domain("1~5") == ("range", 1, 5)
    assert C.parse_domain("1~200") == ("range", 1, 200)

def test_parse_domain_unparseable_returns_none():
    # 带文字/省略/口径的一律不解析,避免误报
    for s in ["万分比", "—", "累计值", "0/1，默认 0", "Grade 1A/2B/3C/4S",
              "0随机/int指定槽", "0/5/10/…/100", "0 起", ""]:
        assert C.parse_domain(s) is None, s


# ---------- parse_xlsx_sheet (内存 rows) ----------

def _rows(*rows):
    return [list(r) for r in rows]

def test_xlsx_table_name_from_row1():
    sh = C.parse_xlsx_sheet(_rows(
        ["unit", "", "", ""],
        ["int", "int", "int", "int"],
        ["id", "name", "rarity", "convert"],
        ["id", "名称", "品质", "转化"],
        ["1001", "1", "2", "5001"],
    ))
    assert sh["table"] == "unit"
    assert set(sh["fields"]) == {"id", "name", "rarity", "convert"}

def test_xlsx_array_field_collapsed():
    # skill[ ] 占 4 列 → 归一为逻辑字段 skill
    sh = C.parse_xlsx_sheet(_rows(
        ["unit", "", "", "", "", ""],
        ["int", "int", "int", "int", "int", "int"],
        ["id", "skill[", "", "", "]", "model"],
        ["id", "技能", "", "", "", "模型"],
        ["1001", "1", "2", "3", "4", "9"],
    ))
    assert set(sh["fields"]) == {"id", "skill", "model"}
    assert sh["fields"]["skill"]["is_array"] is True

def test_xlsx_object_array_collapsed():
    # 对象数组 field.sub[{id,min,max}…max}] 闭合于含 ] 的列 → 归一为单逻辑字段,后续列不被吞
    sh = C.parse_xlsx_sheet(_rows(
        ["gear", "", "", "", "", ""],
        ["int", "int", "int64", "int64", "int", "int64"],
        ["id", "stat.roll[{id", "min", "max}]", "groupId", "bonus"],
        ["id", "属性", "", "", "组", "加成"],
        ["1", "11", "5", "9", "3", "100"],
    ))
    assert set(sh["fields"]) == {"id", "stat.roll", "groupId", "bonus"}
    assert sh["fields"]["stat.roll"]["is_array"] is True   # 后续 groupId/bonus 未被吞

def test_diff_skips_type_for_array():
    doc = {"T": {"fields": {"m": {"type": "混合", "is_array": True, "value": "—", "range": "—", "ref": "—"}}}}
    xl = {"T": _xf({"m": ("int", None)})}        # xlsx 数组列,单一类型 int
    assert not any(f["kind"] == "TYPE" for f in C.diff(doc, xl))   # 数组不比类型

def test_xlsx_merge_artifact_none_skipped():
    # name 合并单元格 → 第2列字段名为空,不应产生幽灵字段
    sh = C.parse_xlsx_sheet(_rows(
        ["unit", "", ""],
        ["int", "", "int"],
        ["name", "", "rarity"],
        ["名称", "名字", "品质"],
        ["1", "", "2"],
    ))
    assert set(sh["fields"]) == {"name", "rarity"}

def test_xlsx_scalar_domain_collected():
    sh = C.parse_xlsx_sheet(_rows(
        ["starTable", ""],
        ["int", "int"],
        ["id", "skillPoint"],
        ["行id", "技能点"],
        ["1", "2"], ["2", "3"], ["3", "40"], ["4", ""],  # 空格跳过
    ))
    assert sh["fields"]["skillPoint"]["vals"] == [2, 3, 40]


# ---------- parse_config_md ----------

_MD = """# 示例配置说明

## 配置表总览

| Sheet | 表名 | 主键 | 用途 | 状态 |
|---|---|---|---|---|
| 单位 | `unit` | id | x | [已定] |

## 1. `unit` 单位列表（主键 id）

| 字段 | 类型 | 取值/枚举 | 范围/默认 | 引用 | 说明 |
|------|------|----------|----------|------|------|
| id | int | — | 1xxxxx | — | id |
| rarity | int | Rarity | 1~5 | `枚举字典.Rarity` | 品质 |
| skill[1..4] | int[] | — | 4 列 | 技能表 | 技能 |

## 2. `starTable` 升星（主键 star）  [已定]

| 字段 | 类型 | 取值 | 范围 | 引用 | 说明 |
|------|------|------|------|------|------|
| id | int | — | — | — | id |
| skillPoint | int | 0/1 | — | — | 是否发点 |
"""

def test_config_md_tables_and_fields():
    doc = C.parse_config_md(_MD)
    assert set(doc) == {"unit", "starTable"}          # 总览不算表;只取带 backtick 标题的段
    assert set(doc["unit"]["fields"]) == {"id", "rarity", "skill"}  # 数组归一
    assert doc["unit"]["fields"]["rarity"]["range"] == "1~5"
    assert doc["starTable"]["fields"]["skillPoint"]["value"] == "0/1"


# ---------- diff ----------

def _docf(**types):
    return {"fields": {n: {"type": t, "value": "—", "range": "—", "ref": "—", "is_array": False}
                       for n, t in types.items()}}

def _xf(fields):
    # fields: {name: (type, vals_or_None)}
    out = {}
    for n, (t, vals) in fields.items():
        out[n] = {"type": t, "is_array": vals is None, "vals": (vals or [])}
    return {"table": "T", "fields": out}

def test_diff_undocumented_column():
    doc = {"T": _docf(id="int", name="int")}
    xl = {"T": _xf({"id": ("int", []), "name": ("int", []), "evolveTarget": ("int", [])})}
    fs = C.diff(doc, xl)
    assert any(f["kind"] == "UNDOC_COL" and f["field"] == "evolveTarget" for f in fs)
    assert all(f["sev"] == "major" for f in fs if f["kind"] == "UNDOC_COL")

def test_diff_missing_column():
    doc = {"T": _docf(id="int", convert="int")}
    xl = {"T": _xf({"id": ("int", [])})}
    fs = C.diff(doc, xl)
    assert any(f["kind"] == "MISSING_COL" and f["field"] == "convert" for f in fs)

def test_diff_type_mismatch():
    doc = {"T": _docf(id="int")}
    xl = {"T": _xf({"id": ("string", [])})}
    fs = C.diff(doc, xl)
    assert any(f["kind"] == "TYPE" and f["field"] == "id" for f in fs)

def test_diff_table_rename_then_field_diff():
    # 文档表名 slot,xlsx 表名 unitSlot(含 slot) → RENAME;且多列 max → UNDOC_COL
    doc = {"slot": _docf(id="int", condition="int", para="int")}
    xl = {"unitSlot": _xf({"id": ("int", []), "condition": ("int", []),
                           "para": ("int", []), "max": ("int", [])})}
    fs = C.diff(doc, xl)
    assert any(f["kind"] == "RENAME" for f in fs)
    assert any(f["kind"] == "UNDOC_COL" and f["field"] == "max" for f in fs)

def test_diff_domain_enum_violation():
    doc = {"T": {"fields": {"skillPoint": {"type": "int", "value": "0/1", "range": "—",
                                           "ref": "—", "is_array": False}}}}
    xl = {"T": _xf({"skillPoint": ("int", [0, 1, 2, 40])})}
    fs = C.diff(doc, xl)
    d = [f for f in fs if f["kind"] == "DOMAIN" and f["field"] == "skillPoint"]
    assert d and d[0]["sev"] == "advisory"
    assert "2" in d[0]["msg"] or "40" in d[0]["msg"]   # 给出越界样例

def test_diff_domain_range_ok_no_finding():
    doc = {"T": {"fields": {"rarity": {"type": "int", "value": "Rarity", "range": "1~5",
                                       "ref": "—", "is_array": False}}}}
    xl = {"T": _xf({"rarity": ("int", [1, 2, 3, 4, 5])})}
    fs = C.diff(doc, xl)
    assert not any(f["kind"] == "DOMAIN" for f in fs)

def test_diff_domain_unparseable_skipped():
    doc = {"T": {"fields": {"hp": {"type": "int", "value": "万分比", "range": "累计值",
                                   "ref": "—", "is_array": False}}}}
    xl = {"T": _xf({"hp": ("int", [120, 880, 9999])})}
    fs = C.diff(doc, xl)
    assert not any(f["kind"] == "DOMAIN" for f in fs)

def test_diff_array_field_no_false_positive():
    doc = {"T": {"fields": {"skill": {"type": "int", "value": "—", "range": "—",
                                      "ref": "—", "is_array": True}}}}
    xl = {"T": _xf({"skill": ("int", None)})}   # None vals → array
    fs = C.diff(doc, xl)
    assert not any(f["kind"] in ("UNDOC_COL", "MISSING_COL") for f in fs)

def test_diff_deterministic():
    doc = {"T": _docf(id="int", name="int")}
    xl = {"T": _xf({"id": ("int", []), "x": ("int", [])})}
    assert C.diff(doc, xl) == C.diff(doc, xl)


if __name__ == "__main__":
    import traceback, inspect, tempfile, pathlib
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fails = 0
    for n, f in fns:
        try:
            if "tmp_path" in inspect.signature(f).parameters:
                f(pathlib.Path(tempfile.mkdtemp()))
            else:
                f()
            print("PASS", n)
        except Exception:
            fails += 1
            print("FAIL", n)
            traceback.print_exc()
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    raise SystemExit(1 if fails else 0)
