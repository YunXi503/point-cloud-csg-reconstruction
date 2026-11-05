"""Figure 4.5(b) v3 — L-Bracket topology node-edge graph, colour-coded faces.

Per user feedback: remove the on-figure ID numbers (which collided with edges),
colour each face node distinctly, and put a compact colour->ID key at the bottom.
Relation edges keep their mutually-exclusive type colour AND a distinct line
style, so the relation layer stays legible in greyscale even though face identity
is carried by node colour. Three-type legend and palette stay aligned with
Figure 4.5(a) v4.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image, ImageOps

from build_stepped_cylinder_independent_truth import read_stl_triangles


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"

FIGURE_STEM = "圖4.5b_L型板_拓樸關係空間視覺化_v3面色節點圖"
DPI = 450

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ADJACENCY_COLOR = "#767C82"
ORTHOGONAL_COLOR = "#17679A"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#DBE0E4"
TEXT_COLOR = "#20252A"

# Edge type -> (colour, matplotlib linestyle). Redundant colour+style => greyscale safe.
EDGE_STYLE = {
    "Adjacency": (ADJACENCY_COLOR, (0, (1.4, 1.4))),
    "OrthogonalAdjacency": (ORTHOGONAL_COLOR, "-"),
    "EndCap": (ENDCAP_COLOR, (0, (3.2, 1.4))),
}

# 12 categorical face colours, chosen to avoid the blue/orange used by edges.
FACE_PALETTE = [
    "#E15759", "#59A14F", "#B07AA1", "#9C755F", "#EDC948", "#4EA6A1",
    "#FF9DA7", "#7570B3", "#1B9E77", "#D37295", "#8C564B", "#A6A6A6",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure() -> tuple[FontProperties, FontProperties, FontProperties]:
    for path in (TIMES_PATH, KAI_PATH, MATH_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Missing font: {path}")
        font_manager.fontManager.addfont(str(path))
    times = FontProperties(family="Times New Roman", size=12)
    kai = FontProperties(family="DFKai-SB", size=12)
    math = FontProperties(family="Cambria", size=12)
    plt.rcParams.update({
        "font.family": "Times New Roman", "font.size": 12,
        "axes.unicode_minus": False, "svg.fonttype": "none",
        "svg.hashsalt": "l-bracket-4-5b-facecolor-260723-v3",
        "savefig.dpi": DPI, "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times, kai, math


def equal_3d(ax: Any, xyz: np.ndarray) -> None:
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = float(np.max(maximum - minimum) / 2.0) * 0.92
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1), zoom=1.18)


def content_occupancy(image_path: Path) -> dict:
    with Image.open(image_path).convert("RGB") as image:
        array = np.asarray(image)
        mask = np.any(array < 248, axis=2)
        ys, xs = np.nonzero(mask)
        left, right = int(xs.min()), int(xs.max())
        top, bottom = int(ys.min()), int(ys.max())
        return {"pixel_width": image.width, "pixel_height": image.height,
                "bbox": [left, top, right, bottom],
                "width_fraction": (right - left + 1) / image.width,
                "height_fraction": (bottom - top + 1) / image.height}


def inspect_svg(svg_path: Path) -> dict:
    ET.parse(svg_path)
    text = svg_path.read_text(encoding="utf-8")
    return {"xml_parse": "PASS", "dejavu_sans_occurrences": text.count("DejaVu Sans")}


def draw_bottom_key(fig, times, kai, math, counts: dict, roles: dict) -> None:
    # Relation-type legend (top strip of the key area).
    ry = 0.150
    groups = [
        (0.085, ADJACENCY_COLOR, EDGE_STYLE["Adjacency"][1], "一般相鄰", int(counts.get("Adjacency", 0))),
        (0.400, ORTHOGONAL_COLOR, EDGE_STYLE["OrthogonalAdjacency"][1], "正交相鄰", int(counts.get("OrthogonalAdjacency", 0))),
        (0.715, ENDCAP_COLOR, EDGE_STYLE["EndCap"][1], "端面關係", int(counts.get("EndCap", 0))),
    ]
    for x, color, ls, label, count in groups:
        fig.add_artist(Line2D([x, x + 0.055], [ry, ry], transform=fig.transFigure,
                              color=color, linewidth=2.4, linestyle=ls, solid_capstyle="round"))
        fig.text(x + 0.070, ry, label, color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
        fig.text(x + 0.210, ry, str(count), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")
    # Face colour -> ID key: 2 rows x 6 columns.
    fig.text(0.045, 0.088, "面", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    x0, dx = 0.130, 0.140
    rows = [0.088, 0.034]
    for cid in range(12):
        col = cid % 6
        row = cid // 6
        x = x0 + col * dx
        y = rows[row]
        fig.add_artist(Line2D([x], [y], transform=fig.transFigure, marker="o", markersize=11,
                              markerfacecolor=FACE_PALETTE[cid], markeredgecolor="#2A2A2A",
                              markeredgewidth=0.8, linestyle="none"))
        fig.text(x + 0.022, y, str(cid), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


def generate(output_dir: Path) -> dict:
    times, kai, math = configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    topology = pd.read_csv(DATA_DIR / "TopologyEdges_L_Bracket_chapter3_verified.csv")
    faces = pd.read_csv(DATA_DIR / "FaceSummary_L_Bracket_chapter3_verified.csv")
    triangles = read_stl_triangles(DATA_DIR / "BlendEvaluatedMesh_L_Bracket.stl")
    validation = json.loads((DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json").read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS":
        raise ValueError("Validation not PASS; drawing blocked.")
    counts = topology["EdgeType"].value_counts().to_dict()

    centroids = {int(r.ClusterID): np.array([r.CenterX, r.CenterY, r.CenterZ], dtype=float)
                 for r in faces.itertuples(index=False)}
    roles = {int(r.ClusterID): str(r.FeatureType) for r in faces.itertuples(index=False)}

    figure = plt.figure(figsize=(5.70, 5.05), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=MODEL_COLOR,
                                         edgecolors="none", linewidths=0, alpha=0.16))
    for r in topology.itertuples(index=False):
        a, b = int(r.FromClusterID), int(r.ToClusterID)
        p, q = centroids[a], centroids[b]
        color, ls = EDGE_STYLE[str(r.EdgeType)]
        ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], color=color, linestyle=ls,
                linewidth=1.7, alpha=0.95, zorder=20, solid_capstyle="round")
    for cid in range(12):
        c = centroids[cid]
        ax.scatter([c[0]], [c[1]], [c[2]], s=115, c=FACE_PALETTE[cid],
                   edgecolors="#2A2A2A", linewidths=0.8, depthshade=False, zorder=45)
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=25, azim=132)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.set_position([0.005, 0.185, 0.99, 0.80])
    draw_bottom_key(figure, times, kai, math, counts, roles)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white",
                   metadata={"Title": "L-Bracket topology node-edge graph (colour-coded faces)",
                             "Software": "generate_lbracket_figure_4_5b_topology_graph_v3.py"})
    figure.savefig(svg, format="svg", facecolor="white",
                   metadata={"Title": "L-Bracket topology node-edge graph v3", "Date": "2026-07-23"})
    plt.close(figure)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    occ = content_occupancy(png)
    svg_check = inspect_svg(svg)
    if svg_check["dejavu_sans_occurrences"] != 0:
        raise ValueError("Unexpected DejaVu Sans fallback in SVG.")

    edge_counts = {"Adjacency": int(counts.get("Adjacency", 0)),
                   "OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
                   "EndCap": int(counts.get("EndCap", 0))}
    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.5(b) L型板拓樸關係空間視覺化（v3 面色節點圖）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "scheme": "mutually_exclusive_most_specific",
        "edge_counts": edge_counts,
        "encoding": {
            "node_colour": "each of 12 semantic faces has a distinct colour; ID via bottom colour key",
            "edge_colour_and_style": "relation type: 正交相鄰 blue solid / 端面關係 orange dashed / 一般相鄰 gray dotted",
            "greyscale": "relation layer legible via line style; face identity is colour-coded",
        },
        "face_palette": {str(i): FACE_PALETTE[i] for i in range(12)},
        "face_roles": {str(k): v for k, v in roles.items()},
        "method_alignment": {"chapter_3_section": "3.7", "palette_aligned_with": "圖 4.5(a) v4",
                             "validation_overall": validation["overall"]},
        "format": {"figure_size_in": [5.70, 5.05], "dpi": DPI,
                   "view": {"elevation": 25, "azimuth": 132, "projection": "orthographic"},
                   "title_inside_figure": False, "occupancy": occ, "svg_check": svg_check},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg)},
        "release_boundary": "Only Figure 4.5(b) v3 is generated; awaiting user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate L-Bracket Figure 4.5(b) v3 colour-coded node graph.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps({"edge_counts": result["summary"]["edge_counts"],
                      "occ_w": round(result["summary"]["format"]["occupancy"]["width_fraction"], 3),
                      "occ_h": round(result["summary"]["format"]["occupancy"]["height_fraction"], 3),
                      "dejavu": result["summary"]["format"]["svg_check"]["dejavu_sans_occurrences"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
