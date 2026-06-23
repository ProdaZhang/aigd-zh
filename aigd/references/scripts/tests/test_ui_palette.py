import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ui_render as R
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
import ui_palette as P


def _rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def test_sample_known_colors(tmp_path):
    if not HAS_PIL:
        print("  (skip test_sample_known_colors: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (10, 10, 10))
    img.paste((220, 20, 20), (0, 0, 50, 50))     # 左上红
    img.paste((20, 20, 220), (50, 0, 100, 50))   # 右上蓝
    p = tmp_path / "t.png"; img.save(str(p))
    dsl = "## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1\n蓝 :b [按钮] @{50 0 50 50} z=1\n```\n"
    skin = P.sample(str(p), R.parse_dsl(dsl))
    ra, rb = _rgb(skin["a"]["fill"]), _rgb(skin["b"]["fill"])
    assert ra[0] > 180 and ra[2] < 80, skin["a"]   # a 偏红
    assert rb[2] > 180 and rb[0] < 80, skin["b"]   # b 偏蓝


def test_sample_skips_art_and_no_id(tmp_path):
    if not HAS_PIL:
        print("  (skip test_sample_skips_art_and_no_id: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (30, 30, 30))
    p = tmp_path / "t.png"; img.save(str(p))
    dsl = "## Layout\n\n```\n底图 :bg [背景槽] @{0 0 100 100} z=1\n无名 [按钮] @{0 0 10 10} z=2\n卡 :c [面板] @{20 20 30 30} z=3\n```\n"
    skin = P.sample(str(p), R.parse_dsl(dsl))
    assert "bg" not in skin     # 背景槽(美术)不采
    assert "c" in skin          # 有 id 的面板采
    assert len(skin) == 1       # 无 id 的不采


def test_sample_circle_takes_center(tmp_path):
    if not HAS_PIL:
        print("  (skip test_sample_circle_takes_center: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (20, 20, 20))   # 深底
    img.paste((230, 40, 160), (25, 25, 75, 75))        # 居中洋红块(占 25% 面积)
    p = tmp_path / "t.png"; img.save(str(p))
    sq = P.sample(str(p), R.parse_dsl("## Layout\n\n```\nA :a [按钮] @{0 0 100 100} z=1\n```\n"))
    ci = P.sample(str(p), R.parse_dsl("## Layout\n\n```\nA :a [按钮] @{0 0 100 100} z=1 形=圆\n```\n"))
    aq, ac = _rgb(sq["a"]["fill"]), _rgb(ci["a"]["fill"])
    assert aq[0] < 80, sq                       # 方:深底主导
    assert ac[0] > 180 and ac[1] < 110, ci      # 圆:取中心→洋红


def test_sample_deterministic(tmp_path):
    if not HAS_PIL:
        print("  (skip test_sample_deterministic: 无 Pillow)"); return
    img = Image.new("RGB", (60, 60), (40, 80, 120))
    img.paste((200, 200, 40), (0, 0, 30, 60))
    p = tmp_path / "t.png"; img.save(str(p))
    parsed = R.parse_dsl("## Layout\n\n```\nA :a [按钮] @{0 0 50 100} z=1\n```\n")
    assert P.sample(str(p), parsed) == P.sample(str(p), parsed)


def test_merge_writes_skin_section(tmp_path):
    if not HAS_PIL:
        print("  (skip test_merge_writes_skin_section: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (10, 10, 10))
    img.paste((220, 20, 20), (0, 0, 50, 50))
    p = tmp_path / "t.png"; img.save(str(p))
    md = "## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1 \"R\"\n```\n"
    skin = P.sample(str(p), R.parse_dsl(md))
    merged = P.merge(md, skin)
    assert "## 皮肤" in merged and "色=" not in merged     # 写成皮肤段、不再塞行内 色=
    parsed = R.parse_dsl(merged)
    assert parsed["skin"].get("a", {}).get("fill", "").startswith("#")  # 皮肤段可被解析回来
    assert P.merge(md, skin) == P.merge(md, skin)         # 确定性


def test_merge_replaces_existing_skin_section(tmp_path):
    if not HAS_PIL:
        print("  (skip test_merge_replaces_existing_skin_section: 无 Pillow)"); return
    img = Image.new("RGB", (100, 100), (10, 10, 10))
    img.paste((220, 20, 20), (0, 0, 50, 50))
    p = tmp_path / "t.png"; img.save(str(p))
    md = "## Layout\n\n```\n红 :a [按钮] @{0 0 50 50} z=1 \"R\"\n```\n\n## 皮肤\n\na  #000000\n"
    skin = P.sample(str(p), R.parse_dsl(md))
    merged = P.merge(md, skin)
    assert merged.count("## 皮肤") == 1                    # 旧皮肤段被替换,不重复
    assert "#000000" not in merged                         # 旧色被新采样色取代


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
