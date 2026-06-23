# -*- coding: utf-8 -*-
"""可移植 LocalizationText 解析器 —— 文本 id → 中文。

从 LocalizationText 式 xlsx(A列=文本id、B列=中文)建 id→中文 映射;
配置表里 NameId/DescId 等是 id,代入真值时用本脚本查中文。
同样用 zipfile+xml(openpyxl 对国产导出 xlsx 会报错)。

用法:
  python resolve_loc.py <LocalizationText.xlsx> [out.txt] [start-end ...]
    - 不给区间 → 输出全量 id→中文
    - 给区间(如 30000001-30000060)→ 只输出这些 id(可多段)
    - 给 out.txt → 写 UTF-8 文件;否则 stdout
列位置默认 A=id、B=中文,如不同改 build() 的 id_col/cn_col。
无项目硬编码:路径与 id 段全走 argv。
"""
import zipfile, re, sys
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

def col_idx(ref):
    m = re.match(r"([A-Z]+)\d+", ref); ls = m.group(1) if m else "A"; n = 0
    for ch in ls: n = n*26 + (ord(ch)-ord('A')+1)
    return n-1

def shared_strings(z):
    out = []
    try: data = z.read("xl/sharedStrings.xml")
    except KeyError: return out
    for si in ET.fromstring(data).findall(f"{NS}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    return out

def cval(c, shared):
    t = c.get("t")
    if t == "s":
        v = c.find(f"{NS}v"); return shared[int(v.text)] if v is not None and v.text else ""
    if t == "inlineStr":
        ie = c.find(f"{NS}is"); return "".join((x.text or "") for x in ie.iter(f"{NS}t")) if ie is not None else ""
    v = c.find(f"{NS}v"); return v.text if v is not None and v.text else ""

def build(path, sheet="xl/worksheets/sheet1.xml", id_col=0, cn_col=1):
    z = zipfile.ZipFile(path); shared = shared_strings(z)
    sd = ET.fromstring(z.read(sheet)).find(f"{NS}sheetData"); loc = {}
    for r in sd.findall(f"{NS}row"):
        cells = {}
        for c in r.findall(f"{NS}c"): cells[col_idx(c.get("r", "A1"))] = cval(c, shared)
        idv = str(cells.get(id_col, "")).strip()
        if re.match(r"^\d+$", idv): loc[idv] = cells.get(cn_col, "")
    z.close(); return loc

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python resolve_loc.py <LocalizationText.xlsx> [out.txt] [start-end ...]"); sys.exit(1)
    loc = build(sys.argv[1])
    out = None; want = None
    for a in sys.argv[2:]:
        if re.match(r"^\d+-\d+$", a):
            s, e = (int(x) for x in a.split("-"))
            want = want or set()
            want.update(str(i) for i in range(s, e+1))
        else:
            out = a
    lines = [f"LocalizationText entries: {len(loc)}", ""]
    for k, v in loc.items():
        if (want is None or k in want) and v != "": lines.append(f"{k}\t{v}")
    txt = "\n".join(lines)
    if out:
        with open(out, "w", encoding="utf-8") as f: f.write(txt)
        print("written:", out)
    else:
        sys.stdout.buffer.write(txt.encode("utf-8"))
