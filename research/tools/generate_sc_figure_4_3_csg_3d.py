"""Figure 4.3 — Stepped Cylinder hierarchical CSG tree, 3D geometric style.

Rebuilds the CSG construction from the verified candidate geometry (parametric
cylinders) as an isometric 3D shape tree with ∪ / − operators, matching the
L-Bracket conference-CSG visual family. Structure from the verified CSGTree:
Difference(Union(SC_U01 lower cyl, SC_U02 upper cyl), SC_D01 through-hole).
Deterministic / reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyArrowPatch
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(r"C:\Users\Admin\Desktop\云析论文") if False else Path(r"C:\Users\Admin\Desktop\云析論文")
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Stepped_Cylinder_v3逐張審查_260722"
FIGURE_STEM = "圖4.3_階梯狀圓柱_階層式CSG推論_3D_v1"
DPI = 450
TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

SOLID = "#C7CDD3"
SOLID_EDGE = "#5A636B"
HOLE = "#D98026"
ARROW = "#5B6670"
TEXT_COLOR = "#20252A"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cyl(ax, r, z0, z1, color, alpha=0.95, cap_top=True, cap_bottom=False, n=48):
    th = np.linspace(0, 2 * np.pi, n)
    Z = np.array([z0, z1])
    T, Zg = np.meshgrid(th, Z)
    ax.plot_surface(r * np.cos(T), r * np.sin(T), Zg, color=color, alpha=alpha,
                    edgecolor="none", linewidth=0, shade=True, zorder=2, antialiased=True)
    rr = np.linspace(0, r, 2)
    Tc, Rc = np.meshgrid(th, rr)
    for do, z in ((cap_top, z1), (cap_bottom, z0)):
        if do:
            ax.plot_surface(Rc * np.cos(Tc), Rc * np.sin(Tc), np.full_like(Tc, z),
                            color=color, alpha=alpha, edgecolor="none", shade=True, zorder=2)


def iso(ax, extent):
    ax.set_box_aspect((1, 1, 1.15))
    ax.view_init(elev=20, azim=-62)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.set_xlim(-extent, extent); ax.set_ylim(-extent, extent); ax.set_zlim(0, 2 * extent)


def occ(path):
    with Image.open(path).convert("RGB") as im:
        a = np.asarray(im); m = np.any(a < 248, 2); ys, xs = np.nonzero(m)
        return {"pixel_width": im.width, "pixel_height": im.height,
                "width_fraction": (int(xs.max()) - int(xs.min()) + 1) / im.width,
                "height_fraction": (int(ys.max()) - int(ys.min()) + 1) / im.height}


def svg_check(path):
    ET.parse(path)
    return {"xml_parse": "PASS", "dejavu_sans_occurrences": path.read_text(encoding="utf-8").count("DejaVu Sans")}


def generate(output_dir: Path, hashsalt: str) -> dict:
    fm.fontManager.addfont(str(TIMES_PATH)); fm.fontManager.addfont(str(KAI_PATH))
    times = fm.FontProperties(family="Times New Roman", size=15)
    kai = fm.FontProperties(family="DFKai-SB", size=12)
    plt.rcParams.update({"font.family": times.get_name(), "svg.fonttype": "none",
                         "svg.hashsalt": hashsalt, "figure.facecolor": "white", "savefig.facecolor": "white"})
    output_dir.mkdir(parents=True, exist_ok=True); (output_dir / "qa").mkdir(parents=True, exist_ok=True)

    # verify structure
    d = ROOT / "碩士論文" / "第四章驗證結果_260722" / "Stepped_Cylinder_chapter3_verified_v3"
    import glob
    tree = json.loads(Path(glob.glob(str(d / "CSGTree*.json"))[0]).read_text(encoding="utf-8"))["tree"]
    unions = [c["candidate"] for c in tree["base"]["children"]]
    subs = [c["candidate"] for c in tree["subtractors"]]
    assert unions == ["SC_U01", "SC_U02"] and subs == ["SC_D01"], "unexpected SC CSG tree"

    fig = plt.figure(figsize=(5.70, 5.55), dpi=DPI)
    ov = fig.add_axes([0, 0, 1, 1]); ov.set_xlim(0, 1); ov.set_ylim(0, 1); ov.axis("off")

    def node(rect, extent):
        ax = fig.add_axes(rect, projection="3d"); iso(ax, extent); return ax

    # leaves: lower cyl (r40 h40), upper cyl (r25 h60)
    a1 = node([0.02, 0.03, 0.30, 0.30], 42); cyl(a1, 39.97, 0, 40, SOLID, cap_bottom=True)
    ov.text(0.17, 0.03, "下階外圓柱 SC_U01", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    a2 = node([0.34, 0.03, 0.26, 0.30], 42); cyl(a2, 24.97, 0, 60, SOLID, cap_bottom=True)
    ov.text(0.47, 0.03, "上階外圓柱 SC_U02", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    # union -> stepped
    a3 = node([0.10, 0.36, 0.32, 0.32], 44)
    cyl(a3, 39.97, 0, 40, SOLID, cap_bottom=True); cyl(a3, 24.97, 40, 100, SOLID)
    ov.text(0.26, 0.35, "聯集結果（階梯圓柱）", ha="center", va="center", color="#5A636B", fontproperties=kai)
    # subtractor hole
    a4 = node([0.62, 0.36, 0.26, 0.30], 42); cyl(a4, 14.97, 0, 100, HOLE, alpha=0.95, cap_bottom=True)
    ov.text(0.75, 0.35, "貫穿孔 SC_D01", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    # final: stepped translucent + orange bore
    a5 = node([0.30, 0.67, 0.34, 0.32], 44)
    cyl(a5, 39.97, 0, 40, SOLID, alpha=0.55, cap_bottom=True); cyl(a5, 24.97, 40, 100, SOLID, alpha=0.55)
    cyl(a5, 14.97, 0, 100, HOLE, alpha=1.0, cap_top=True, cap_bottom=True)
    ov.text(0.47, 0.985, "階梯狀圓柱重建結果", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)

    def op(x, y, s):
        ov.text(x, y, s, ha="center", va="center", color=TEXT_COLOR, fontproperties=times,
                bbox=dict(boxstyle="circle,pad=0.28", facecolor="white", edgecolor=SOLID_EDGE, linewidth=1.4))

    def arr(x0, y0, x1, y1):
        ov.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=15,
                                     color=ARROW, linewidth=1.5, shrinkA=2, shrinkB=2))

    op(0.315, 0.30, "∪")
    arr(0.20, 0.24, 0.29, 0.31); arr(0.44, 0.24, 0.345, 0.31); arr(0.315, 0.345, 0.27, 0.44)
    op(0.545, 0.60, "−")
    arr(0.40, 0.54, 0.515, 0.585); arr(0.70, 0.52, 0.575, 0.585); arr(0.545, 0.645, 0.49, 0.70)

    png, svg = output_dir / f"{FIGURE_STEM}.png", output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(png, dpi=DPI, metadata={"Title": FIGURE_STEM})
    fig.savefig(svg, format="svg", metadata={"Title": FIGURE_STEM, "Date": "2026-07-23"})
    plt.close(fig)
    with Image.open(png) as im:
        ImageOps.grayscale(im.convert("RGB")).save(output_dir / "qa" / f"{FIGURE_STEM}_灰階檢查.png", dpi=(DPI, DPI))
    o = occ(png); sc = svg_check(svg)
    if sc["dejavu_sans_occurrences"] != 0:
        raise ValueError("DejaVu fallback in SVG.")
    qa = {"figure": FIGURE_STEM, "status": "PASS_AWAITING_USER_CONFIRMATION", "style": "3D geometric CSG tree",
          "csg_structure": "Difference(Union(SC_U01,SC_U02), SC_D01)", "unions": unions, "subtractors": subs,
          "occupancy": o, "svg_check": sc, "outputs": {png.name: sha256(png), svg.name: sha256(svg)}}
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return qa


def main():
    p = argparse.ArgumentParser(); p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--hashsalt", default="sc-4-3-csg3d-260723-v1")
    a = p.parse_args()
    qa = generate(a.output_dir.resolve(), a.hashsalt)
    print(json.dumps({"csg": qa["csg_structure"], "occ_w": round(qa["occupancy"]["width_fraction"], 3),
                      "dejavu": qa["svg_check"]["dejavu_sans_occurrences"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
