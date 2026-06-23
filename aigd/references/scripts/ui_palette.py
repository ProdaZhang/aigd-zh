"""工具3 家族 · 确定性采色器:原图 + 界面 DSL → 每元素主色(fill)+ 文字色(ink) skin 模块。

按 DSL 的 bbox 从原图采样真实颜色(主色=区域主导色,文字色=区域内与主色对比最大的色),
背景槽/立绘槽(美术,要换素材)与无 id 元素不采。需 Pillow;同输入 + 同 Pillow 版本 → 输出一致。

用法: python ui_palette.py <dsl.md> <image> [out.skin.json]
产物: {元素id: {"fill":"#rrggbb", "ink":"#rrggbb"}} —— 喂 ui_render.py --skin 逐元素上色。
      或 --merge 把色写成 md 的 `## 皮肤` 段(渲染该 md 即用真色,无需 --skin)。
"""
import sys, json, os

try:
    import ui_render as R
except ImportError:
    R = None

ART = ("背景槽", "立绘槽")


def _hex(c):
    return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _dominant(region, k=6):
    rgb = region.convert("RGB")
    q = rgb.quantize(colors=k).convert("RGB")
    cols = q.getcolors(q.width * q.height) or []
    cols.sort(key=lambda c: c[0], reverse=True)   # 频次降序
    return [c[1] for c in cols]


def sample(image_path, parsed):
    from PIL import Image
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    skin = {}
    for e in parsed["elements"]:
        if not e["id"] or e["type"] in ART:
            continue
        x1, y1 = e["x"] / 100 * W, e["y"] / 100 * H
        x2, y2 = (e["x"] + e["w"]) / 100 * W, (e["y"] + e["h"]) / 100 * H
        box = (max(0, int(x1)), max(0, int(y1)), min(W, int(round(x2))), min(H, int(round(y2))))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        # 圆形元素:取中心内圈采样(否则方框里圆外的背景会主导,采错色)
        if (e.get("shape") or "") in ("圆", "圆形", "circle"):
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            hw, hh = (box[2] - box[0]) * 0.28, (box[3] - box[1]) * 0.28
            inner = (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))
            if inner[2] > inner[0] and inner[3] > inner[1]:
                box = inner
        doms = _dominant(img.crop(box))
        if not doms:
            continue
        fill = doms[0]
        ink = max(doms, key=lambda c: abs(_lum(c) - _lum(fill))) if len(doms) > 1 else (240, 240, 240)
        skin[e["id"]] = {"fill": _hex(fill), "ink": _hex(ink)}
    return skin


def merge(md_text, skin):
    """把采样色写成 md 的 `## 皮肤` 段(id → 色):替换已有皮肤段,或追加到文末。

    皮肤与结构(Layout)分离 —— 整段可换肤/可删(删=回退 L1),不污染元素行。
    skin 为有序 dict(sample 按元素顺序产出)→ 输出确定。
    """
    lines = md_text.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.strip().startswith("## ") and ln.strip()[3:].strip().startswith("皮肤"):
            i += 1                                   # 跳过旧皮肤段(到下一个 ## 或文末)
            while i < n and not lines[i].strip().startswith("## "):
                i += 1
            continue
        out.append(ln); i += 1
    while out and not out[-1].strip():               # 去尾部空行再追加
        out.pop()
    block = ["", "## 皮肤", ""]
    for key in skin:
        c = skin[key]
        row = "%s  %s" % (key, c["fill"])
        if c.get("ink"):
            row += " / %s" % c["ink"]
        block.append(row)
    return "\n".join(out + block) + "\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    merge_mode, merge_out = False, None
    if "--merge" in argv:
        merge_mode = True
        i = argv.index("--merge")
        if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            merge_out = argv[i + 1]; del argv[i:i + 2]
        else:
            del argv[i]
    if len(argv) < 2:
        print("用法: python ui_palette.py <dsl.md> <image> [out.skin.json]")
        print("      python ui_palette.py <dsl.md> <image> --merge [out.md]   # 把色写成 md 的 ## 皮肤 段")
        return 2
    if R is None:
        print("✗ 需要同目录 ui_render.py(复用 parse_dsl)")
        return 2
    dsl, image = argv[0], argv[1]
    with open(dsl, encoding="utf-8") as f:
        md = f.read()
    parsed = R.parse_dsl(md)
    # 不 resolve:采色/--merge 按 authored md 的 id 写回,展开后命名空间 id 会写错。
    # 竞品捕获(本工具唯一场景)本就不含实例,resolve 是恒等;故略过。
    from PIL import Image as _I
    iw, ih = _I.open(image).size
    print("建议 > 尺寸:", "%dx%d" % R.recommend_size(iw, ih))
    skin = sample(image, parsed)
    if merge_mode:
        out = merge_out or (dsl.rsplit(".", 1)[0] + ".colored.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(merge(md, skin))
        print("merged md ->", out, "(%d 元素上色)" % len(skin))
    else:
        out = argv[2] if len(argv) > 2 else (dsl.rsplit(".", 1)[0] + ".skin.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(skin, f, ensure_ascii=False, indent=1)
        print("skin ->", out, "(%d 元素)" % len(skin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
