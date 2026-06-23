import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ui_render as R
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
import ui_slice as S


def _img(tmp_path):
    img = Image.new("RGB", (100, 100), (12, 12, 12))
    img.paste((220, 30, 30), (0, 0, 50, 50))      # 左上红块
    img.paste((30, 30, 220), (50, 50, 100, 100))  # 右下蓝块
    p = tmp_path / "src.png"; img.save(str(p))
    return str(p)


def test_cut_writes_files_and_index(tmp_path):
    if not HAS_PIL:
        print("  (skip test_cut_writes_files_and_index: 无 Pillow)"); return
    p = _img(tmp_path)
    dsl = "## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1\n蓝 :b [面板] @{50 50 50 50} z=2\n```\n"
    out = str(tmp_path / "sl")
    man = S.cut(p, R.parse_dsl(dsl), out)
    assert len(man) == 2
    assert os.path.exists(os.path.join(out, man[0]["file"]))
    idx = open(os.path.join(out, "index.md"), encoding="utf-8").read()
    assert "![" in idx and man[0]["file"] in idx       # 接触表含缩略图引用
    assert man[0]["file"] == "00_a.png" and man[1]["file"] == "01_b.png"


def test_cut_crops_correct_region(tmp_path):
    if not HAS_PIL:
        print("  (skip test_cut_crops_correct_region: 无 Pillow)"); return
    p = _img(tmp_path)
    dsl = "## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1\n蓝 :b [面板] @{50 50 50 50} z=2\n```\n"
    out = str(tmp_path / "sl")
    man = S.cut(p, R.parse_dsl(dsl), out)
    a = Image.open(os.path.join(out, man[0]["file"])).convert("RGB")
    b = Image.open(os.path.join(out, man[1]["file"])).convert("RGB")
    pa = a.getpixel((a.width // 2, a.height // 2)); pb = b.getpixel((b.width // 2, b.height // 2))
    assert pa[0] > 180 and pa[2] < 90, pa             # a 切的是红块
    assert pb[2] > 180 and pb[0] < 90, pb             # b 切的是蓝块


def test_cut_circle_has_alpha(tmp_path):
    if not HAS_PIL:
        print("  (skip test_cut_circle_has_alpha: 无 Pillow)"); return
    p = _img(tmp_path)
    dsl = "## Layout\n\n```\n圆 :c [图标槽] @{0 0 50 50} z=1 形=圆\n```\n"
    out = str(tmp_path / "sl")
    man = S.cut(p, R.parse_dsl(dsl), out)
    im = Image.open(os.path.join(out, man[0]["file"]))
    assert im.mode == "RGBA"
    assert im.getpixel((0, 0))[3] == 0                                # 角落透明(圆外)
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 255      # 中心不透明
    # 未声明 形=圆 → 方角、无 alpha
    man2 = S.cut(p, R.parse_dsl("## Layout\n\n```\n方 :q [图标槽] @{0 0 50 50} z=1\n```\n"), str(tmp_path / "sq"))
    assert Image.open(os.path.join(str(tmp_path / "sq"), man2[0]["file"])).mode == "RGB"


def test_cut_only_filter_keeps_stable_index(tmp_path):
    if not HAS_PIL:
        print("  (skip test_cut_only_filter_keeps_stable_index: 无 Pillow)"); return
    p = _img(tmp_path)
    dsl = ("## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1\n板 :b [面板] @{50 0 50 50} z=2\n"
           "图 :c [图标槽] @{0 50 50 50} z=3\n```\n")
    out = str(tmp_path / "sl")
    man = S.cut(p, R.parse_dsl(dsl), out, only=["图标槽"])
    assert len(man) == 1 and man[0]["id"] == "c"
    assert man[0]["file"] == "02_c.png"               # 编号仍取完整文档序(第3个=02)


def test_cut_deterministic(tmp_path):
    if not HAS_PIL:
        print("  (skip test_cut_deterministic: 无 Pillow)"); return
    p = _img(tmp_path)
    parsed = R.parse_dsl("## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1\n```\n")
    o1, o2 = str(tmp_path / "s1"), str(tmp_path / "s2")
    m1 = S.cut(p, parsed, o1); m2 = S.cut(p, parsed, o2)
    assert m1 == m2
    b1 = open(os.path.join(o1, m1[0]["file"]), "rb").read()
    b2 = open(os.path.join(o2, m2[0]["file"]), "rb").read()
    assert b1 == b2                                   # 同输入 → 切片字节一致


def test_slice_resolves_instances(tmp_path):
    if not HAS_PIL:
        print("  (skip test_slice_resolves_instances: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (20, 20, 20))
    p = tmp_path / "src.png"; img.save(str(p))
    (tmp_path / "bar.md").write_text(
        "# 资源栏 · 模块\n> 类型: 模块\n> 尺寸: 1000×200\n\n## Layout\n\n```\n金币 :gold [数值条] @{0 0 100 100} z=5\n```\n", encoding="utf-8")
    screen = R.parse_dsl("# S\n> 尺寸: 1000×1000\n\n## 引用\n\n资源栏 = bar.md\n\n## Layout\n\n```\n顶栏 :top [实例·资源栏] @{0 0} z=9\n```\n")
    flat = R.resolve(screen, str(tmp_path))
    man = S.cut(str(p), flat, str(tmp_path / "out"))
    assert any(m["id"] == "top.gold" for m in man)


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
