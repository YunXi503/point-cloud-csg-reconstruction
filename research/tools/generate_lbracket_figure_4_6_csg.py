"""Figure 4.6 — L-Bracket hierarchical CSG inference tree (schematic).

Matches the confirmed Stepped Cylinder Fig 4.3 style: geometric profile symbols
for candidate primitives, ∪ / − operator nodes, arrows bottom-up. Structure read
from the verified CSGTree: Difference(Union(LB_U01,LB_U02,LB_U03), LB_D01,LB_D02).
Deterministic + reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrowPatch
import numpy as np
import pandas as pd
from PIL import Image, ImageOps

ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"
FIGURE_STEM = "圖4.6_L型板_階層式CSG推論_v1"
DPI = 450

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

SOLID_A = "#F2B705"   # base plate (yellow)
SOLID_B = "#4E9A93"   # upright / boss (teal)
HOLE = "#D98026"      # subtracted holes (orange dashed)
EDGE = "#2E3A43"
ARROW = "#5B6670"
TEXT_COLOR = "#20252A"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def configure(hashsalt: str):
    fm.fontManager.addfont(str(TIMES_PATH)); fm.fontManager.addfont(str(KAI_PATH))
    times = fm.FontProperties(family="Times New Roman", size=12)
    kai = fm.FontProperties(family="DFKai-SB", size=12)
    plt.rcParams.update({"font.family": times.get_name(), "font.size": 12, "svg.fonttype": "none",
                         "svg.hashsalt": hashsalt, "figure.facecolor": "white", "savefig.facecolor": "white"})
    return times, kai


def rect(ax, x, y, w, h, color, dashed=False, z=5):
    ax.add_patch(Rectangle((x, y), w, h, facecolor="none" if dashed else color,
                           edgecolor=HOLE if dashed else EDGE, linewidth=2.0 if dashed else 1.6,
                           linestyle=(0, (4, 2)) if dashed else "-", zorder=z))


def lbracket(ax, cx, cy, s=1.0, holes=False, z=5):
    """Compact L profile: horizontal base + vertical upright + boss; optional holes."""
    base_w, base_h = 2.4 * s, 0.5 * s
    up_w, up_h = 0.5 * s, 1.7 * s
    bx, by = cx - base_w / 2, cy
    rect(ax, bx, by, base_w, base_h, SOLID_A, z=z)                      # base plate
    rect(ax, bx, by + base_h, up_w, up_h, SOLID_B, z=z)                 # upright plate
    boss_w, boss_h = 0.42 * s, 0.95 * s                                 # boss
    rect(ax, bx + base_w - boss_w - 0.30 * s, by + base_h, boss_w, boss_h, SOLID_B, z=z)
    if holes:
        rect(ax, bx + 0.95 * s, by - 0.02 * s, 0.30 * s, base_h + 0.04 * s, HOLE, dashed=True, z=z + 2)  # base hole
        rect(ax, bx + 0.02 * s, by + base_h + 0.45 * s, up_w - 0.04 * s, 0.55 * s, HOLE, dashed=True, z=z + 2)  # upright hole


def op_node(ax, x, y, symbol, times):
    ax.add_patch(Circle((x, y), 0.34, facecolor="white", edgecolor=EDGE, linewidth=1.6, zorder=8))
    ax.text(x, y, symbol, ha="center", va="center", color=TEXT_COLOR, fontproperties=times, zorder=9, fontsize=15)


def arrow(ax, x0, y0, x1, y1):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=15,
                                 color=ARROW, linewidth=1.5, zorder=3, shrinkA=6, shrinkB=6))


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
    times, kai = configure(hashsalt)
    tree = json.loads((DATA_DIR / "CSGTree_L_Bracket_chapter3_verified.json").read_text(encoding="utf-8"))
    cand = pd.read_csv(DATA_DIR / "PrimitiveCandidates_L_Bracket_chapter3_verified.csv")
    unions = [c["candidate"] for c in tree["tree"]["base"]["children"]]
    subtractors = [c["candidate"] for c in tree["tree"]["subtractors"]]
    assert unions == ["LB_U01", "LB_U02", "LB_U03"] and subtractors == ["LB_D01", "LB_D02"], "unexpected CSG tree"

    output_dir.mkdir(parents=True, exist_ok=True); (output_dir / "qa").mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(5.70, 5.35), dpi=DPI)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.98])
    ax.set_xlim(0, 11.4); ax.set_ylim(0, 10.7); ax.set_aspect("equal"); ax.axis("off")

    # --- bottom row: three union primitives ---
    names = {"LB_U01": "底板", "LB_U02": "立板", "LB_U03": "凸台"}
    rect(ax, 0.5, 0.7, 2.2, 0.55, SOLID_A)                       # LB_U01 base plate (wide)
    ax.text(1.6, 0.30, "底板 LB_U01", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    rect(ax, 4.55, 0.55, 0.55, 1.7, SOLID_B)                     # LB_U02 upright plate (tall)
    ax.text(4.82, 0.30, "立板 LB_U02", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    rect(ax, 7.3, 0.6, 0.7, 1.5, SOLID_B)                        # LB_U03 boss
    ax.text(7.65, 0.30, "凸台 LB_U03", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)

    op_node(ax, 4.9, 3.35, "∪", times)
    for sx, sy in [(1.6, 1.35), (4.82, 2.35), (7.65, 2.2)]:
        arrow(ax, sx, sy, 4.9, 3.15)

    # --- middle: union result (L + boss, no holes) ---
    lbracket(ax, 4.9, 4.35, s=1.15, holes=False)
    ax.text(4.9, 4.05, "聯集結果", ha="center", va="center", color="#5A636B", fontproperties=kai)

    # --- two subtractor holes on the right ---
    rect(ax, 9.6, 3.4, 0.55, 1.5, HOLE, dashed=True)
    ax.text(9.87, 3.15, "底板孔 LB_D01", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)
    rect(ax, 9.6, 5.7, 0.55, 1.5, HOLE, dashed=True)
    ax.text(9.87, 5.45, "立板孔 LB_D02", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)

    op_node(ax, 5.6, 7.2, "−", times)
    arrow(ax, 4.9, 5.65, 5.45, 7.0)          # union result -> minus
    arrow(ax, 9.55, 4.15, 5.9, 7.05)         # base hole -> minus
    arrow(ax, 9.55, 6.45, 5.9, 7.35)         # upright hole -> minus

    # --- top: final result (L + boss with two holes) ---
    lbracket(ax, 5.6, 8.35, s=1.25, holes=True)
    arrow(ax, 5.6, 7.55, 5.6, 8.05)
    ax.text(5.6, 10.35, "L型板重建結果", ha="center", va="center", color=TEXT_COLOR, fontproperties=kai)

    png, svg = output_dir / f"{FIGURE_STEM}.png", output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(png, dpi=DPI, bbox_inches="tight", pad_inches=0.06, metadata={"Title": FIGURE_STEM})
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.06, metadata={"Title": FIGURE_STEM, "Date": "2026-07-23"})
    plt.close(fig)
    with Image.open(png) as im:
        ImageOps.grayscale(im.convert("RGB")).save(output_dir / "qa" / f"{FIGURE_STEM}_灰階檢查.png", dpi=(DPI, DPI))
    o = occ(png); sc = svg_check(svg)
    if sc["dejavu_sans_occurrences"] != 0:
        raise ValueError("DejaVu fallback in SVG.")
    qa = {"figure": FIGURE_STEM, "status": "PASS_AWAITING_USER_CONFIRMATION",
          "csg_structure": "Difference(Union(LB_U01,LB_U02,LB_U03), LB_D01, LB_D02)",
          "unions": unions, "subtractors": subtractors,
          "candidate_rows": int(len(cand)), "occupancy": o, "svg_check": sc,
          "outputs": {png.name: sha256(png), svg.name: sha256(svg)}}
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return qa


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--hashsalt", default="l-bracket-4-6-csg-260723-v1")
    a = p.parse_args()
    qa = generate(a.output_dir.resolve(), a.hashsalt)
    print(json.dumps({"csg": qa["csg_structure"], "occ_w": round(qa["occupancy"]["width_fraction"], 3),
                      "dejavu": qa["svg_check"]["dejavu_sans_occurrences"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
