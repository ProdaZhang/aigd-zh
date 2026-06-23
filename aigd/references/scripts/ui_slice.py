"""工具3 家族 · 确定性切片器:原图 + 界面 DSL → 每元素一张 png 切片 + index.md 接触表。

按 DSL 的 bbox 从原图切出每个元素的区域(`形=圆` 加圆形 alpha 蒙版),把竞品界面拆成
可参考/可替换的部件素材。与 ui_palette 同族:复用 parse_dsl、需 Pillow、声明驱动
(只按 `形=` 决定圆/方,不靠纵横比猜)。同输入 + 同 Pillow/zlib 版本 → 输出字节一致。

用法: python ui_slice.py <dsl.md> <image> [outdir]
      python ui_slice.py <dsl.md> <image> [outdir] --only 背景槽,立绘槽,图标槽   # 只切这些类型
产物: outdir/NN_<id或名>.png(逐元素切片,NN=文档序) + outdir/index.md(缩略图接触表 + bbox 表)。
"""
import sys, os, re

try:
    import ui_render as R
except ImportError:
    R = None

_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')
_CIRCLE = ("圆", "圆形", "circle")


def _slug(e):
    s = _UNSAFE.sub("-", (e["id"] or e["name"] or e["type"] or "el")).strip("-")
    return s or "el"


def _box(e, W, H):
    x1, y1 = e["x"] / 100 * W, e["y"] / 100 * H
    x2, y2 = (e["x"] + e["w"]) / 100 * W, (e["y"] + e["h"]) / 100 * H
    return (max(0, int(x1)), max(0, int(y1)), min(W, int(round(x2))), min(H, int(round(y2))))


def cut(image_path, parsed, outdir, only=None):
    """切出每个(可选按类型过滤的)元素 → outdir/NN_slug.png;返回 manifest 列表(保序)。

    编号 NN 取自**完整元素列表的文档序**——即便用 only 过滤,留下来的切片编号仍稳定。
    """
    from PIL import Image, ImageDraw
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    all_els = parsed["elements"]
    keep = set(only) if only else None
    width = max(2, len(str(len(all_els))))
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for i, e in enumerate(all_els):
        if keep is not None and e["type"] not in keep and e["type"].split("·")[0] not in keep:
            continue
        box = _box(e, W, H)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        crop = img.crop(box)
        if (e.get("shape") or "") in _CIRCLE:
            crop = crop.convert("RGBA")
            mask = Image.new("L", crop.size, 0)
            ImageDraw.Draw(mask).ellipse([0, 0, crop.width - 1, crop.height - 1], fill=255)
            crop.putalpha(mask)
        fn = "%0*d_%s.png" % (width, i, _slug(e))
        crop.save(os.path.join(outdir, fn))
        manifest.append({"file": fn, "id": e["id"], "name": e["name"], "type": e["type"],
                         "z": e["z"], "shape": e.get("shape") or "",
                         "bbox": [e["x"], e["y"], e["w"], e["h"]]})
    with open(os.path.join(outdir, "index.md"), "w", encoding="utf-8") as f:
        f.write(index_md(parsed, manifest))
    return manifest


def _cell(s):
    return str(s).replace("|", "/")          # 表格单元勿含裸竖线


def index_md(parsed, manifest):
    """缩略图接触表 + bbox 表(markdown,KB 直接可读)。"""
    lines = ["# 切片接触表 · %s" % (parsed["screen"] or ""), "",
             "> 工具3 ui_slice 产物:逐元素切原图(`形=圆` 已加圆形蒙版)。",
             "> 换素材时按 bbox/类型对位;原图可弃,本表 + 切片即归档。", ""]
    for m in manifest:
        cap = m["name"] or m["id"] or m["type"]
        lines.append("![%s](%s)" % (_cell(cap), m["file"]))
    lines += ["", "| 切片 | id | 名称 | 类型 | 形 | z | bbox(x y w h %) |",
              "|---|---|---|---|---|---|---|"]
    for m in manifest:
        z = "" if m["z"] is None else m["z"]
        bb = " ".join("%g" % v for v in m["bbox"])
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            _cell(m["file"]), _cell(m["id"] or ""), _cell(m["name"] or ""),
            _cell(m["type"]), _cell(m["shape"]), z, bb))
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = [t for t in argv[i + 1].split(",") if t] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if len(argv) < 2:
        print("用法: python ui_slice.py <dsl.md> <image> [outdir] [--only 类型,类型]")
        return 2
    if R is None:
        print("✗ 需要同目录 ui_render.py(复用 parse_dsl)")
        return 2
    dsl, image = argv[0], argv[1]
    outdir = argv[2] if len(argv) > 2 and not argv[2].startswith("-") else (dsl.rsplit(".", 1)[0] + ".slices")
    with open(dsl, encoding="utf-8") as f:
        parsed = R.parse_dsl(f.read())
    from PIL import Image as _I
    iw, ih = _I.open(image).size
    print("建议 > 尺寸:", "%dx%d" % R.recommend_size(iw, ih))
    parsed = R.resolve(parsed, os.path.dirname(os.path.abspath(dsl)))   # 展开实例(无实例则恒等)
    manifest = cut(image, parsed, outdir, only)
    print("slices ->", outdir, "(%d 片 + index.md)" % len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
