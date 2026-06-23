# -*- coding: utf-8 -*-
"""value_check.py 测试 —— 纯 stdlib,逻辑层用内存 idx/doc 夹具(表/字段名均为示意)。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import value_check as V


def _idx():
    return {
        "unit": {"file": "unit.xlsx", "fieldcol": {"id": 0, "line": 1, "rarity": 2},
                 "data": [["1101", "1101", "1"], ["1001", "1001", "2"],
                          ["1002", "1001", "2"], ["1003", "1001", "2"],
                          ["1900", "", "1"]]},
        "evolveLine": {"file": "unit.xlsx", "fieldcol": {"id": 0, "member": 1},
                       "data": [["1001", "1001", "1002", "1003"]]},
        "rarityCap": {"file": "unit.xlsx", "fieldcol": {"id": 0, "evolution": 1},
                      "data": [["1", "0"], ["2", "1"], ["3", "2"]]},
        "levelTable": {"file": "unit.xlsx", "fieldcol": {"id": 0, "Hp": 1},
                       "data": [["1", "10"], ["2", "20"], ["4", "40"]]},
        "__enums__": {"A": "3", "水": "1"},
        "__keymap__": {},
    }


def _doc_fk(ref, is_array=False):
    return {"unit": {"fields": {"line": {"ref": ref, "is_array": is_array,
                                         "type": "int", "value": "—", "range": "—"}}}}


# ---------- FK ----------
def test_fk_detects_break():
    fs = V.check_fk(_doc_fk("`evolveLine.id`"), _idx())
    b = [f for f in fs if f["kind"] == "FK_BREAK"]
    assert b and b[0]["sev"] == "major"
    assert "1101" in b[0]["msg"]                # line 1101 不在 evolveLine.id
    assert "1001" not in b[0]["msg"].split("样例")[-1]  # 合法值不报

def test_fk_skips_null_sentinel_zero():
    # 末阶引用字段=0 表示无引用,不应判为断链
    idx = _idx()
    idx["unit"]["fieldcol"]["evoTarget"] = 3
    idx["unit"]["data"] = [["1001", "1001", "2", "1002"], ["1002", "1001", "2", "0"]]
    doc = {"unit": {"fields": {"evoTarget": {"ref": "`unit.id`", "is_array": False,
                                             "type": "int", "value": "—", "range": "—"}}}}
    assert not any(f["kind"] == "FK_BREAK" for f in V.check_fk(doc, idx))   # 0 被当空哨兵

def test_fk_skips_array_source():
    fs = V.check_fk(_doc_fk("`unit.id`", is_array=True), _idx())
    assert not any(f["kind"] == "FK_BREAK" for f in fs)

def test_fk_array_member_break():
    # v3: 数组源逐成员校验 —— evolveLine.member[] 某成员不在 unit.id → 断链
    idx = {"g": {"fieldcol": {"id": 0, "member": 1}, "arraycols": {"member": [1, 2, 3]},
                 "data": [["1001", "1001", "1002", "999999"]]},
           "unit": {"fieldcol": {"id": 0}, "arraycols": {}, "data": [["1001"], ["1002"]]}}
    doc = {"g": {"fields": {"member": {"ref": "`unit.id`", "is_array": True,
                                       "type": "int", "value": "—", "range": "—"}}}}
    fs = V.check_fk(doc, idx)
    assert any(f["kind"] == "FK_BREAK" and "999999" in f["msg"] for f in fs)

def test_fk_crossfile_via_refmap():
    # v3: 中文名 道具表 经 refmap → item.id 跨文件解析
    idx = {"levelTable": {"fieldcol": {"id": 0, "key": 1}, "arraycols": {}, "data": [["1", "5001"], ["2", "999"]]},
           "item": {"fieldcol": {"id": 0}, "arraycols": {}, "data": [["5001"]]}}
    doc = {"levelTable": {"fields": {"key": {"ref": "道具表", "is_array": False,
                                            "type": "int", "value": "—", "range": "—"}}}}
    fs = V.check_fk(doc, idx, {"道具表": "item.id"})
    assert any(f["kind"] == "FK_BREAK" and "999" in f["msg"] for f in fs)   # key 999 不在 item.id
    assert not any(f["kind"] == "FK_BREAK" for f in V.check_fk(doc, idx, {}))  # 无 refmap → 中文名不解析

def test_fk_skips_non_ref():
    assert not any(f["kind"] in ("FK_BREAK", "FK_SKIP") for f in V.check_fk(_doc_fk("道具表"), _idx()))

def test_fk_target_not_in_index_is_skip_info():
    fs = V.check_fk(_doc_fk("`枚举字典.Rarity`"), _idx())
    assert any(f["kind"] == "FK_SKIP" and f["sev"] == "info" for f in fs)

def test_fk_clean_no_break():
    idx = _idx()
    idx["unit"]["data"] = [["1001", "1001", "2"]]   # line 全部命中
    assert not any(f["kind"] == "FK_BREAK" for f in V.check_fk(_doc_fk("`evolveLine.id`"), idx))


# ---------- 验收引用解析 ----------
def test_acc_flags_dangling_citation():
    acc = "那么 uid 变为 evolveLine[1101].member[1]\n"
    fs = V.check_acceptance(acc, _idx())
    assert any(f["kind"] == "ACC_DANGLING" and "1101" in f["msg"] for f in fs)

def test_acc_resolved_ok_no_finding():
    fs = V.check_acceptance("扣除 = levelTable[2].Hp\n", _idx())
    assert not any(f["kind"] == "ACC_DANGLING" for f in fs)

def test_acc_empty_field_not_dangling():
    # unit[1900] 行在、line 为空(可选字段)→ 不算悬空,避免误报
    fs = V.check_acceptance("校验 unit[1900].line 应为空\n", _idx())
    assert not any(f["kind"] == "ACC_DANGLING" for f in fs)

def test_acc_multi_skipped():
    # 火 未在 enums + 无 keymap → MULTI → 不报(需手填,不是断链)
    fs = V.check_acceptance("starTable[A,火,1].x = 1\n", _idx())
    assert not any(f["kind"] == "ACC_DANGLING" for f in fs)


# ---------- rules ----------
def _card_rule(severity=None):
    r = {"type": "cardinality", "array_table": "evolveLine", "array_field": "member",
         "member_table": "unit", "member_rarity_field": "rarity",
         "limit_table": "rarityCap", "limit_field": "evolution"}
    if severity:
        r["severity"] = severity
    return r

def test_rule_cardinality_violation():
    fs = V.run_rules([_card_rule()], _idx())
    c = [f for f in fs if f["kind"] == "RULE_CARDINALITY"]
    assert c and c[0]["sev"] == "major"          # 3 成员=2 进化 > rarityCap[2].evolution=1

def test_rule_cardinality_severity_override():
    c = [f for f in V.run_rules([_card_rule("advisory")], _idx()) if f["kind"] == "RULE_CARDINALITY"]
    assert c and c[0]["sev"] == "advisory"       # severity 可降级,不阻断门禁

def test_rule_cardinality_ok():
    idx = _idx()
    idx["evolveLine"]["data"] = [["1001", "1001", "1002"]]   # 2 成员=1 进化 ≤1
    assert not any(f["kind"] == "RULE_CARDINALITY" for f in V.run_rules([_card_rule()], idx))

def test_rule_coverage_gap():
    rule = {"type": "coverage", "table": "levelTable", "field": "id", "min": 1, "max": 4}
    fs = V.run_rules([rule], _idx())
    g = [f for f in fs if f["kind"] == "RULE_COVERAGE"]
    assert g and "3" in g[0]["msg"]              # 缺 3

def test_rule_monotonic_violation():
    idx = _idx()
    idx["levelTable"]["data"] = [["1", "10"], ["2", "5"], ["3", "20"]]   # 10→5 下降
    rule = {"type": "monotonic", "table": "levelTable", "field": "Hp", "order_field": "id"}
    assert any(f["kind"] == "RULE_MONOTONIC" for f in V.run_rules([rule], idx))

def test_rule_monotonic_ok():
    rule = {"type": "monotonic", "table": "levelTable", "field": "Hp", "order_field": "id"}
    assert not any(f["kind"] == "RULE_MONOTONIC" for f in V.run_rules([rule], _idx()))

def test_deterministic():
    d = _doc_fk("`evolveLine.id`")
    assert V.check_fk(d, _idx()) == V.check_fk(d, _idx())


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
