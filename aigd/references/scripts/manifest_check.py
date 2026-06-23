# -*- coding: utf-8 -*-
"""工具6 · manifest_check —— 脊柱 manifest.md 内部一致性校验器(纯 stdlib)。

为什么存在:manifest 是脊柱(A 系统清单+依赖图 / B 号段登记 / C 跨层索引 /
D 冻结账本+待重验 / E 回退记录 / F 共享真源),6 张强类型表全手写 markdown,
跨表引用(A 表 R-模块码 ↔ B 表号段、A 表依赖 ↔ A 表系统、A 表系统 ↔ C 表分块、
A↔A 依赖成环)没人机检。config_check/value_check 管"配置 ↔ 文档",本脚本管"脊柱自洽"。

抓什么(major,会 gate):
  SEG_MISSING   A 表某系统的 R-模块码,B 表号段登记里查不到 —— 领了码没登记/登记表漏行
  DANGLING_DEP  A 表「依赖(上游)」里的显式系统ID(S\\d+)在 A 表不存在 —— 指向了不存在的系统
  BAD_STATUS    A/D/E 表里的状态值不在状态枚举内(定稿* 归一为 定稿)
  NO_CBLOCK     A 表某系统在 C 表没有 `### <ID>` 跨层索引分块 —— 产物散落没登记
抓什么(advisory,需人判):
  CYCLE         依赖图(按系统名/ID 连边,排自环)成环 —— 提示公共类型须先在全局规范登记破环
  DEFINED_NO_CONTRACT  C 表里 定稿/定稿* 系统的分块缺 proto 或 验收行(定稿应有交接产物)
  SEG_UNUSED    B 表登记了模块码、A 表无系统用它 —— 号段空挂/系统已删
  CBLOCK_ORPHAN C 表有分块、A 表无此系统 —— 删了系统没删索引
info:
  DEP_BY_NAME   依赖边按系统名解析(真 manifest 依赖列是散文) —— 透明声明本次按名连边

不抓(留给人工 / 太自由文本会误报):D 表「待重验触发」↔ F 表登记对账(触发项含点对点
口径,非全是广播真源,机检会大量误报);号段数值区间两两不撞(B 表已自带 `示例` 占位)。

设计与 config_check/value_check 一致:argv 驱动、零项目硬编码、确定性、宁可漏报不误报。

用法:
  python manifest_check.py <manifest.md>
  退出码: 有 major → 1,否则 0(advisory/info 不致失败)。
"""
import sys, os, re

STATUS_ENUM = {"草稿", "试玩中", "定稿", "待重验"}
_SYS_ID_RE = re.compile(r"\bS\d{1,3}\b")
_RCODE_RE = re.compile(r"R-[A-Z][A-Z0-9]*")   # 模块码 token(全大写 ASCII);一系统可多段(如 R-FOO / R-BAR)
_SPLIT_RE = re.compile(r"(?<!\\)\|")


# ---------------------------------------------------------------- markdown 表解析
def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in _SPLIT_RE.split(s)]


def _is_sep(line):
    body = line.strip().strip("|")
    return bool(body) and set(body) <= set("-:| ") and "-" in body


def parse_md_tables(text):
    """连续 | 行成一张表:首行表头,次行若是 ---|--- 分隔则跳过,其余数据行。"""
    tables = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if lines[i].lstrip().startswith("|"):
            block = []
            while i < n and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            header = _split_row(block[0])
            start = 2 if len(block) > 1 and _is_sep(block[1]) else 1
            rows = [_split_row(b) for b in block[start:]]
            tables.append({"header": header, "rows": rows})
        else:
            i += 1
    return tables


def _col(header, *keys):
    for k in keys:
        for j, h in enumerate(header):
            if k in h:
                return j
    return None


def _pick(tables, *keys):
    """取首张表头含全部 keys 的表。"""
    for t in tables:
        if all(_col(t["header"], k) is not None for k in keys):
            return t
    return None


def _cell(row, i):
    return row[i] if (i is not None and i < len(row)) else ""


def _norm_status(s):
    """去 markdown 强调/反引号/挂账星号 → 纯状态词。"""
    return (s or "").replace("**", "").replace("`", "").replace("*", "").strip()


def _names_in_text(text, names):
    """文本里出现了哪些系统名(集合)。长名优先掩码,避免短名被长名误命中
    (如系统名「主线」是「主线任务」的子串 → 提到主线任务不该误连主线边)。"""
    found, tmp = set(), text
    for nm in sorted(names, key=len, reverse=True):
        if nm and nm in tmp:
            found.add(nm)
            tmp = tmp.replace(nm, "\x00" * len(nm))   # 掩掉已命中的长名,短子串不再重复命中
    return found


def _is_placeholder(s):
    s = (s or "").strip()
    return (not s) or s in {"—", "-"} or (s.startswith("<") and s.endswith(">"))


# ---------------------------------------------------------------- C 表分块解析
def parse_c_blocks(text):
    """`### <ID> <名>` 起一块,正文到下一个 ###/##/# 止。返回 {id:{name,body}}。"""
    blocks = {}
    lines = text.splitlines()
    cur_id = cur_name = None
    buf = []

    def flush():
        if cur_id:
            blocks[cur_id] = {"name": cur_name, "body": "\n".join(buf)}

    for ln in lines:
        st = ln.strip()
        if st.startswith("### "):
            flush()
            buf = []
            head = st[4:].strip()
            m = _SYS_ID_RE.search(head)
            cur_id = m.group(0) if m else None
            cur_name = head
        elif re.match(r"^#{1,3} ", st):   # 退到 ###/##/# 同级或更高 → 结束当前块
            flush()
            cur_id = cur_name = None
            buf = []
        else:
            if cur_id:
                buf.append(ln)
    flush()
    return blocks


# ---------------------------------------------------------------- 主检查
def check_text(text):
    findings = []
    tables = parse_md_tables(text)

    A = _pick(tables, "系统ID")
    B = _pick(tables, "模块码", "号段")
    D = _pick(tables, "待重验")
    E = _pick(tables, "从状态")

    if not A:
        return [{"sev": "major", "kind": "NO_A_TABLE", "where": "manifest",
                 "msg": "未找到 A 表(系统清单,表头需含「系统ID」) —— 这不是合法 manifest 或表头被改坏"}]

    # ---- A 表抽取 ----
    aid = _col(A["header"], "系统ID")
    aname = _col(A["header"], "系统名")
    astat = _col(A["header"], "状态")
    acode = _col(A["header"], "模块码")
    adep = _col(A["header"], "依赖")

    sys_ids, sys_names, sys_status, sys_code, sys_dep = [], {}, {}, {}, {}
    for r in A["rows"]:
        sid = _cell(r, aid).replace("`", "").strip()
        if _is_placeholder(sid) or not _SYS_ID_RE.match(sid):
            continue
        sys_ids.append(sid)
        nm = _cell(r, aname).replace("`", "").replace("*", "").strip()
        sys_names[sid] = nm
        sys_status[sid] = _norm_status(_cell(r, astat))
        sys_code[sid] = _RCODE_RE.findall(_cell(r, acode))   # 一系统可多段码(如 R-FOO / R-BAR)
        sys_dep[sid] = _cell(r, adep)
    id_set = set(sys_ids)
    name_to_id = {n: i for i, n in sys_names.items() if n}

    # ---- B 表号段登记 ----
    b_codes = set()
    if B:
        bcode = _col(B["header"], "模块码")
        for r in B["rows"]:
            c = _cell(r, bcode).replace("`", "").strip()
            if not _is_placeholder(c):
                b_codes.add(c)

    # ① SEG_MISSING / SEG_UNUSED:A 表模块码 ↔ B 表登记(一系统可多段码)
    used_codes = set()
    for sid in sys_ids:
        for code in sys_code.get(sid, []):
            used_codes.add(code)
            if B and code not in b_codes:
                findings.append({"sev": "major", "kind": "SEG_MISSING", "where": "A→B 表",
                                 "msg": "系统 %s(%s)的模块码 '%s' 在 B 表号段登记里查不到" % (sid, sys_names.get(sid, ""), code)})
    for c in sorted(b_codes - used_codes):
        findings.append({"sev": "advisory", "kind": "SEG_UNUSED", "where": "B 表",
                         "msg": "B 表登记模块码 '%s',A 表无系统使用(号段空挂或系统已删)" % c})

    # ② 状态枚举:A / D / E 表
    for sid in sys_ids:
        s = sys_status.get(sid, "")
        if s and s not in STATUS_ENUM:
            findings.append({"sev": "major", "kind": "BAD_STATUS", "where": "A 表",
                             "msg": "系统 %s 状态 '%s' 不在状态枚举 %s 内" % (sid, s, "/".join(sorted(STATUS_ENUM)))})
    if D:
        dstat = _col(D["header"], "状态")
        dsysc = _col(D["header"], "系统")
        for r in D["rows"]:
            s = _norm_status(_cell(r, dstat))
            who = _cell(r, dsysc).replace("`", "").strip()
            if _is_placeholder(s):
                continue                              # 占位行(— / 空)不校验
            if s and s not in STATUS_ENUM:
                findings.append({"sev": "major", "kind": "BAD_STATUS", "where": "D 表",
                                 "msg": "D 表 '%s' 状态 '%s' 不在状态枚举内" % (who, s)})
    if E:
        etrans = _col(E["header"], "从状态")
        for r in E["rows"]:
            cell = _cell(r, etrans)
            if _is_placeholder(cell):
                continue                              # 占位行(— / 空,"暂无回退")不校验
            for part in re.split(r"→|->", cell):
                s = _norm_status(part)
                if _is_placeholder(s):
                    continue
                if s and s not in STATUS_ENUM:
                    findings.append({"sev": "major", "kind": "BAD_STATUS", "where": "E 表",
                                     "msg": "E 表状态迁移 '%s' 中 '%s' 不在状态枚举内" % (cell.strip(), s)})

    # ③ 依赖解析:DANGLING_DEP(显式 ID)+ 按名连边(供环检测)
    edges = {}   # sid -> set(上游 sid)
    dep_by_name = False
    for sid in sys_ids:
        cell = sys_dep.get(sid, "")
        ups = set()
        for tok in _SYS_ID_RE.findall(cell):       # 显式 ID 引用
            if tok == sid:
                continue
            if tok in id_set:
                ups.add(tok)
            else:
                findings.append({"sev": "major", "kind": "DANGLING_DEP", "where": "A 表",
                                 "msg": "系统 %s 依赖 '%s',但 A 表无此系统" % (sid, tok)})
        for nm in _names_in_text(cell, name_to_id):   # 按系统名连边(真 manifest 依赖列是散文;长名优先掩码)
            nid = name_to_id[nm]
            if nid == sid:
                continue
            ups.add(nid)
            dep_by_name = True
        edges[sid] = ups
    if dep_by_name:
        findings.append({"sev": "info", "kind": "DEP_BY_NAME", "where": "A 表",
                         "msg": "部分依赖边按系统名从依赖列散文解析(非显式 ID);环检测据此连边"})

    # ④ CYCLE:依赖图互依集群(SCC,advisory —— 公共类型须先在全局规范登记破环)
    #    用强连通分量而非枚举环:每个互依集群报一次(完整、不冗余、无组合爆炸)
    for comp in _find_cyclic_clusters(edges):
        nodes = sorted(comp)
        label = " · ".join("%s(%s)" % (i, sys_names.get(i, "")) for i in nodes)
        cyc = _sample_cycle(edges, set(comp))
        sample = (" → ".join(cyc)) if cyc else "(自环/多环)"
        findings.append({"sev": "advisory", "kind": "CYCLE", "where": "A 表依赖图",
                         "msg": "互依集群 {%s} 成环(示例 %s)—— 公共类型须先在全局规范(项目层)登记破环,handoff 时沉 proto/common" % (label, sample)})

    # ⑤ C 表分块:NO_CBLOCK / CBLOCK_ORPHAN / DEFINED_NO_CONTRACT
    cblocks = parse_c_blocks(text)
    for sid in sys_ids:
        if sid not in cblocks:
            findings.append({"sev": "major", "kind": "NO_CBLOCK", "where": "A→C 表",
                             "msg": "系统 %s(%s)在 C 表无 `### %s` 跨层索引分块" % (sid, sys_names.get(sid, ""), sid)})
            continue
        if sys_status.get(sid) == "定稿":          # 含 定稿*(已归一)
            body = cblocks[sid]["body"]
            miss = []
            if "proto" not in body and "契约" not in body:
                miss.append("proto/契约")
            if "验收" not in body:
                miss.append("验收")
            if miss:
                findings.append({"sev": "advisory", "kind": "DEFINED_NO_CONTRACT", "where": "C 表 %s" % sid,
                                 "msg": "定稿系统 %s(%s)的 C 分块缺 %s 行(定稿应有交接产物)" % (
                                     sid, sys_names.get(sid, ""), "、".join(miss))})
    for cid in sorted(cblocks):
        if cid not in id_set:
            findings.append({"sev": "advisory", "kind": "CBLOCK_ORPHAN", "where": "C 表 %s" % cid,
                             "msg": "C 表有分块 '%s'(%s),A 表无此系统(删系统未删索引?)" % (cid, cblocks[cid]["name"])})
    return findings


def _find_cyclic_clusters(edges):
    """Tarjan 强连通分量,返回每个 size>1 的 SCC(节点列表)。
    比"枚举环"更适合本场景:每个互依集群恰好报一次,既不漏(着色 DFS 会漏跨边构成的环)
    也不冗余(枚举会为同一集群报多条重叠环),且无组合爆炸。"""
    index, low, onstack, stk, sccs = {}, {}, {}, [], []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stk.append(v)
        onstack[v] = True
        for w in edges.get(v, ()):
            if w not in edges:
                continue
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif onstack.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stk.pop()
                onstack[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))
    for v in edges:
        if v not in index:
            strong(v)
    return sccs


def _sample_cycle(edges, comp):
    """在 SCC 内找一条代表环路(从最小节点出发回到自身),供报告可读。best-effort。"""
    start = sorted(comp)[0]
    stack = [(start, [start])]
    seen = set()
    while stack:
        node, path = stack.pop()
        for w in sorted(edges.get(node, ())):
            if w not in comp:
                continue
            if w == start and len(path) >= 2:
                return path + [start]
            if w not in seen:
                seen.add(w)
                stack.append((w, path + [w]))
    return None


def check(path):
    with open(path, encoding="utf-8") as f:
        return check_text(f.read())


# ---------------------------------------------------------------- report / main
_SEV_ORDER = {"major": 0, "advisory": 1, "info": 2}


def format_report(findings, path):
    out = ["脊柱 manifest 内部一致性校验", "  manifest: %s" % path, ""]
    if not findings:
        out.append("✓ 自洽:模块码登记齐 / 依赖无悬空 / 状态合法 / 系统皆有 C 分块 / 无依赖环。")
        return "\n".join(out)
    n_major = sum(1 for f in findings if f["sev"] == "major")
    n_adv = sum(1 for f in findings if f["sev"] == "advisory")
    n_info = sum(1 for f in findings if f["sev"] == "info")
    out.append("发现 %d 条(major=%d advisory=%d info=%d):" % (len(findings), n_major, n_adv, n_info))
    out.append("")
    by_where = {}
    for f in findings:
        by_where.setdefault(f["where"], []).append(f)
    tag = {"major": "[major]", "advisory": "[advisory]", "info": "[info]"}
    for w in sorted(by_where):
        out.append("● %s" % w)
        for f in sorted(by_where[w], key=lambda x: (_SEV_ORDER[x["sev"]], x["kind"])):
            out.append("    %-10s %-18s %s" % (tag[f["sev"]], f["kind"], f["msg"]))
        out.append("")
    out.append("major 须修脊柱后重跑;advisory/info 请人工判定(环=是否已全局登记破环;DEP_BY_NAME=透明声明)。")
    return "\n".join(out)


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: python manifest_check.py <manifest.md>\n")
        return 2
    path = argv[1]
    findings = check(path)
    sys.stdout.buffer.write((format_report(findings, path) + "\n").encode("utf-8"))
    return 1 if any(f["sev"] == "major" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
