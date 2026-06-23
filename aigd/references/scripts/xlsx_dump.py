# -*- coding: utf-8 -*-
"""可移植 xlsx dumper —— zipfile + ElementTree。

为什么不用 openpyxl:很多国产导表工具导出的 xlsx 会让 openpyxl 报
`Colors must be aRGB hex values`。本脚本绕开样式表,直解 XML。

用法:
  python xlsx_dump.py <file.xlsx> [out.txt] [max_rows]
    - 给 out.txt → 写 UTF-8 文件(中文务必写文件再看,控制台直接 print 可能乱码)
    - 不给 out  → 输出到 stdout(UTF-8 bytes)
    - max_rows  → 每 sheet 取前 N 行(默认 60),够看自描述表头 + 样例

自描述表头约定(行1=表英文名 / 行2=类型 / 行3=字段key(数组 field[…]) / 行4=中文名 / 行5+=数据)。
无项目硬编码:路径全走 argv。
"""
import zipfile, re, os, sys
import xml.etree.ElementTree as ET

NS  = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

def col_letters(ref):
    m = re.match(r"([A-Z]+)\d+", ref); return m.group(1) if m else "A"

def col_to_idx(letters):
    n = 0
    for ch in letters: n = n*26 + (ord(ch)-ord('A')+1)
    return n-1  # 0-based

def load_shared_strings(z):
    out = []
    try: data = z.read("xl/sharedStrings.xml")
    except KeyError: return out
    for si in ET.fromstring(data).findall(f"{NS}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    return out

def sheet_map(z):
    """[(显示名, sheet xml 路径)]，按 workbook 顺序。"""
    wb   = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid  = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for sh in wb.find(f"{NS}sheets").findall(f"{NS}sheet"):
        tgt = rid.get(sh.get(f"{RNS}id"), "")
        tgt = tgt.lstrip("/") if tgt.startswith("/") else "xl/" + tgt
        out.append((sh.get("name"), tgt))
    return out

def read_rows(z, path, shared, max_rows=None):
    sd = ET.fromstring(z.read(path)).find(f"{NS}sheetData"); rows = []
    if sd is None: return rows
    for r in sd.findall(f"{NS}row"):
        if max_rows is not None and len(rows) >= max_rows: break
        cells = {}; mx = -1
        for c in r.findall(f"{NS}c"):
            ci = col_to_idx(col_letters(c.get("r", "A1"))); t = c.get("t"); val = ""
            if t == "s":
                v = c.find(f"{NS}v"); val = shared[int(v.text)] if v is not None and v.text else ""
            elif t == "inlineStr":
                ie = c.find(f"{NS}is"); val = "".join((x.text or "") for x in ie.iter(f"{NS}t")) if ie is not None else ""
            else:
                v = c.find(f"{NS}v"); val = v.text if v is not None and v.text else ""
            cells[ci] = val; mx = max(mx, ci)
        rows.append([cells.get(i, "") for i in range(mx+1)])
    return rows

def dump(path, max_rows=60):
    z = zipfile.ZipFile(path); shared = load_shared_strings(z)
    lines = [f"===== FILE: {os.path.basename(path)} ====="]
    sheets = sheet_map(z)
    lines.append(f"sheets ({len(sheets)}): " + ", ".join(n for n, _ in sheets)); lines.append("")
    for name, sp in sheets:
        rows = read_rows(z, sp, shared, max_rows)
        lines.append(f"----- SHEET: {name} ({sp}) rows={len(rows)} -----")
        for i, row in enumerate(rows): lines.append(f"[r{i+1}] " + "\t".join(row))
        lines.append("")
    z.close(); return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python xlsx_dump.py <file.xlsx> [out.txt] [max_rows]"); sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    mr  = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    txt = dump(src, mr)
    if out:
        with open(out, "w", encoding="utf-8") as f: f.write(txt)
        print("written:", out)
    else:
        sys.stdout.buffer.write(txt.encode("utf-8"))
