"""Figure 4.2(b) — Stepped Cylinder topology spatial visualization (single view).

Stepped-Cylinder counterpart of L 4.5(b) / Model A 4.8(b): the verified solid is
drawn translucent and every method topology relation is drawn ON its real contact
boundary. Stepped Cylinder has 6 EndCap relations only (0 orthogonal, 0 adjacency),
so each relation is an orange dashed ring where a cylinder meets a cap plane.

Unlike L / Model A, the Stepped-Cylinder independent truth stores no per-triangle
cluster map, so the solid and the rings are built PARAMETRICALLY from the verified
FaceSummary geometry (radii, axial ranges) and the ring for each EndCap edge is
placed at (cylinder radius, cap plane z). Relation TYPES/pairs come from the
verified v3 TopologyEdges (method output). Deterministic / reproducible.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from PIL import Image, ImageOps

ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "Stepped_Cylinder_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Stepped_Cylinder_v3逐張審查_260722"

FIGURE_STEM = "圖4.2b_階梯狀圓柱_拓樸關係空間圖_v1實體接觸"
DPI = 450
VIEW_ELEV, VIEW_AZIM = 20, -60

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ORTHOGONAL_COLOR = "#17679A"
ADJACENCY_COLOR = "#767C82"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#D9DEE2"
TEXT_COLOR = "#20252A"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure():
    for path in (TIMES_PATH, KAI_PATH, MATH_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Missing font: {path}")
        font_manager.fontManager.addfont(str(path))
    times = FontProperties(family="Times New Roman", size=12)
    kai = FontProperties(family="DFKai-SB", size=12)
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12, "axes.unicode_minus": False,
                         "svg.fonttype": "none", "svg.hashsalt": "sc-figure-4-2b-spatial-260723",
                         "savefig.dpi": DPI, "figure.facecolor": "white", "savefig.facecolor": "white"})
    return times, kai


def cyl_side(ax, r, z0, z1, color, alpha, n=80):
    th = np.linspace(0, 2 * np.pi, n)
    Z, T = np.meshgrid(np.array([z0, z1]), th)
    ax.plot_surface(r * np.cos(T), r * np.sin(T), Z, color=color, alpha=alpha,
                    edgecolor="none", linewidth=0, shade=True, antialiased=True, zorder=2)


def annulus(ax, r_in, r_out, z, color, alpha, n=80):
    th = np.linspace(0, 2 * np.pi, n)
    R, T = np.meshgrid(np.array([r_in, r_out]), th)
    ax.plot_surface(R * np.cos(T), R * np.sin(T), np.full_like(R, z), color=color, alpha=alpha,
                    edgecolor="none", linewidth=0, shade=False, zorder=2)


def ring(ax, r, z, color, n=240):
    th = np.linspace(0, 2 * np.pi, n)
    ax.plot(r * np.cos(th), r * np.sin(th), np.full_like(th, z), color=color,
            linestyle=(0, (3.0, 1.25)), linewidth=2.4, solid_capstyle="round", zorder=30)


def equal_3d(ax, rmax, z0, z1):
    span = max(2 * rmax, z1 - z0)
    cx, cy, cz = 0.0, 0.0, (z0 + z1) / 2.0
    h = span / 2.0 * 0.98
    ax.set_xlim(cx - h, cx + h); ax.set_ylim(cy - h, cy + h); ax.set_zlim(cz - h, cz + h)
    ax.set_box_aspect((1, 1, 1), zoom=1.32)


def content_occupancy(image_path):
    with Image.open(image_path).convert("RGB") as image:
        arr = np.asarray(image); mask = np.any(arr < 248, axis=2)
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            raise ValueError("Rendered figure is blank.")
        l, r, t, b = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        return {"pixel_width": image.width, "pixel_height": image.height, "bbox": [l, t, r, b],
                "width_fraction": (r - l + 1) / image.width, "height_fraction": (b - t + 1) / image.height}


def inspect_svg(svg_path):
    ET.parse(svg_path)
    return {"xml_parse": "PASS", "dejavu_sans_occurrences": svg_path.read_text(encoding="utf-8").count("DejaVu Sans")}


def draw_legend(fig, times, kai, counts):
    ry = 0.062
    groups = [(0.075, ADJACENCY_COLOR, (0, (1.4, 1.4)), "一般相鄰", int(counts.get("Adjacency", 0))),
              (0.400, ORTHOGONAL_COLOR, "-", "正交相鄰", int(counts.get("OrthogonalAdjacency", 0))),
              (0.715, ENDCAP_COLOR, (0, (3.0, 1.25)), "端面關係", int(counts.get("EndCap", 0)))]
    for x, color, ls, label, cnt in groups:
        fig.add_artist(Line2D([x, x + 0.052], [ry, ry], transform=fig.transFigure,
                              color=color, linewidth=2.3, linestyle=ls, solid_capstyle="round"))
        fig.text(x + 0.066, ry, label, color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
        fig.text(x + 0.205, ry, str(cnt), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


def generate(output_dir: Path) -> dict:
    times, kai = configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"; qa_dir.mkdir(parents=True, exist_ok=True)

    faces = pd.read_csv(glob.glob(str(DATA_DIR / "FaceSummary*.csv"))[0], encoding="utf-8-sig")
    topo = pd.read_csv(glob.glob(str(DATA_DIR / "TopologyEdges*.csv"))[0], encoding="utf-8-sig")
    validation = json.loads(Path(glob.glob(str(DATA_DIR / "ValidationSummary*.json"))[0]).read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS":
        raise ValueError("Stepped Cylinder validation not PASS; drawing blocked.")
    counts = topo["EdgeType"].value_counts().to_dict()
    if counts.get("EndCap") != 6 or len(topo) != 6:
        raise ValueError(f"Unexpected SC topology counts: {counts}")

    face = {int(r.ClusterID): r for r in faces.itertuples(index=False)}

    def is_cyl(rec):
        return not (isinstance(rec.Radius, float) and math.isnan(rec.Radius))

    # place one ring per EndCap edge at (cylinder radius, cap plane z)
    ring_specs = []
    for e in topo.itertuples(index=False):
        a, b = int(e.FromClusterID), int(e.ToClusterID)
        fa, fb = face[a], face[b]
        cyl_face, plane_face = (fa, fb) if is_cyl(fa) else (fb, fa)
        if not is_cyl(cyl_face) or is_cyl(plane_face):
            raise ValueError(f"EndCap {a}-{b} is not cylinder+plane as expected.")
        ring_specs.append({"pair": [a, b], "radius": float(cyl_face.Radius), "z": float(plane_face.CenterZ)})

    # solid geometry from the verified cylinder faces
    hole = face[0]; lower = face[1]; upper = face[5]
    r_hole, r_low, r_up = float(hole.Radius), float(lower.Radius), float(upper.Radius)
    z_bot, z_step, z_top = 0.0, float(face[3].CenterZ), float(face[4].CenterZ)

    fig = plt.figure(figsize=(5.70, 4.55), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    a_solid = 0.42
    cyl_side(ax, r_low, z_bot, z_step, MODEL_COLOR, a_solid)
    cyl_side(ax, r_up, z_step, z_top, MODEL_COLOR, a_solid)
    cyl_side(ax, r_hole, z_bot, z_top, MODEL_COLOR, min(a_solid + 0.12, 0.6))
    annulus(ax, r_hole, r_low, z_bot, MODEL_COLOR, a_solid)      # bottom annulus
    annulus(ax, r_up, r_low, z_step, MODEL_COLOR, a_solid)       # shoulder annulus
    annulus(ax, r_hole, r_up, z_top, MODEL_COLOR, a_solid)       # top annulus
    for spec in ring_specs:
        ring(ax, spec["radius"], spec["z"], ENDCAP_COLOR)

    equal_3d(ax, r_low, z_bot, z_top)
    ax.view_init(elev=VIEW_ELEV, azim=VIEW_AZIM)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)
    ax.set_position([0.005, 0.085, 0.99, 0.905])
    draw_legend(fig, times, kai, counts)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08,
                metadata={"Title": "Stepped Cylinder topology spatial visualization",
                          "Software": "generate_sc_figure_4_2b_spatial.py"})
    fig.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                metadata={"Title": "Stepped Cylinder topology spatial visualization", "Date": "2026-07-23",
                          "Creator": "generate_sc_figure_4_2b_spatial.py"})
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))
    occ = content_occupancy(png)
    svg_check = inspect_svg(svg)
    if svg_check["dejavu_sans_occurrences"] != 0:
        raise ValueError("Unexpected DejaVu Sans fallback in SVG.")

    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.2(b) 階梯狀圓柱拓樸關係空間視覺化（v1 實體接觸）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "note_prioritised_department_format_pdf": "已優先對照系上格式PDF（圖無標題、英數 Times New Roman、中文 DFKai-SB）",
        "purpose": "single-view physical contact-boundary visualization; L 4.5(b) 家族，取代抽象六邊形拓樸圖",
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "model_source": "parametric solid from verified FaceSummary (SC truth has no per-triangle cluster map)",
            "relations_source": "verified v3 TopologyEdges (method output)",
            "encoding": "orange dashed ring = EndCap contact boundary (cylinder meets cap plane)",
            "counts": {k: int(counts.get(k, 0)) for k in ("Adjacency", "OrthogonalAdjacency", "EndCap")},
            "endcap_rings": ring_specs,
            "validation_overall": validation["overall"],
        },
        "format": {
            "figure_size_in": [5.70, 4.55], "dpi": DPI,
            "view": {"elevation": VIEW_ELEV, "azimuth": VIEW_AZIM, "projection": "orthographic"},
            "english_numbers_font": "Times New Roman 12 pt", "chinese_font": "DFKai-SB 12 pt",
            "title_inside_figure": False, "occupancy": occ, "svg_check": svg_check,
        },
        "source_sha256": {Path(p).name: sha256(Path(p))
                          for p in (glob.glob(str(DATA_DIR / "FaceSummary*.csv"))[0],
                                    glob.glob(str(DATA_DIR / "TopologyEdges*.csv"))[0],
                                    glob.glob(str(DATA_DIR / "ValidationSummary*.json"))[0])},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg),
                    str(gray.relative_to(output_dir)): sha256(gray)},
        "release_boundary": "Only Figure 4.2(b) spatial candidate is generated; awaits user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "counts": qa["method_alignment"]["counts"],
            "rings": len(ring_specs), "occ_w": round(occ["width_fraction"], 3),
            "dejavu": svg_check["dejavu_sans_occurrences"]}


def main():
    parser = argparse.ArgumentParser(description="Generate only Stepped Cylinder Figure 4.2(b) topology spatial visualization.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(generate(args.output_dir.resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
