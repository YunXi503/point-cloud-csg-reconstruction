"""Figure 4.5(b) v1 — L-Bracket topology node-edge graph (chosen: Option A).

Face centroids are nodes; each stored topology relation is one edge coloured by
its mutually-exclusive type (一般相鄰 / 正交相鄰 / 端面關係), over a faint solid
for spatial context. Node labels use per-node offsets with thin leaders to keep
the crowded upright-plate and base-centre faces legible. The three-type legend
and palette match Figure 4.5(a) v4, and the scheme generalises to Model A 4.8.
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

FIGURE_STEM = "圖4.5b_L型板_拓樸關係空間視覺化_v2節點邊圖"
DPI = 450

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ADJACENCY_COLOR = "#767C82"
ORTHOGONAL_COLOR = "#17679A"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#D9DEE2"
NODE_COLOR = "#20252A"
TEXT_COLOR = "#20252A"
LEADER_COLOR = "#9AA1A7"

EDGE_STYLE = {
    "Adjacency": ADJACENCY_COLOR,
    "OrthogonalAdjacency": ORTHOGONAL_COLOR,
    "EndCap": ENDCAP_COLOR,
}

# Per-node label offset (dx, dy, dz) to separate crowded upright/base clusters.
LABEL_OFFSET = {
    0: (0.0, 1.5, -6.0),
    1: (0.0, 13.0, -3.0),
    2: (0.0, 3.0, 6.5),
    3: (0.0, 0.0, 4.5),
    4: (0.0, -5.5, 0.0),
    5: (5.5, 0.0, 0.0),
    6: (0.0, 4.5, 3.0),
    7: (0.0, 0.0, 11.0),
    8: (5.0, 0.0, -1.0),
    9: (0.0, -8.0, -2.0),
    10: (0.0, 4.5, 0.0),
    11: (-10.0, -6.0, -1.0),
}


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
        "svg.hashsalt": "l-bracket-4-5b-graph-260723-v1",
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
    ax.set_box_aspect((1, 1, 1), zoom=1.16)


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


def legend_three(fig, times, kai, math, counts: dict) -> None:
    y = 0.058
    groups = [
        (0.075, ADJACENCY_COLOR, "一般相鄰", int(counts.get("Adjacency", 0))),
        (0.400, ORTHOGONAL_COLOR, "正交相鄰", int(counts.get("OrthogonalAdjacency", 0))),
        (0.725, ENDCAP_COLOR, "端面關係", int(counts.get("EndCap", 0))),
    ]
    for x, color, label, count in groups:
        fig.add_artist(Line2D([x, x + 0.052], [y, y], transform=fig.transFigure,
                              color=color, linewidth=2.4, solid_capstyle="round"))
        fig.text(x + 0.066, y, label, color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
        fig.text(x + 0.205, y, str(count), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


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

    figure = plt.figure(figsize=(5.70, 4.35), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=MODEL_COLOR,
                                         edgecolors="none", linewidths=0, alpha=0.13))
    # edges coloured by mutually-exclusive stored type
    for r in topology.itertuples(index=False):
        a, b = int(r.FromClusterID), int(r.ToClusterID)
        p, q = centroids[a], centroids[b]
        color = EDGE_STYLE[str(r.EdgeType)]
        ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], color=color,
                linewidth=1.7, alpha=0.95, zorder=20, solid_capstyle="round")
    pts = np.array([centroids[i] for i in range(12)])
    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=40, c=NODE_COLOR, depthshade=False, zorder=40)
    for cid in range(12):
        c = centroids[cid]
        dx, dy, dz = LABEL_OFFSET.get(cid, (0.0, 0.0, 2.6))
        lp = c + np.array([dx, dy, dz])
        ax.plot([c[0], lp[0]], [c[1], lp[1]], [c[2], lp[2]], color=LEADER_COLOR,
                linewidth=0.7, alpha=0.85, zorder=35)
        ax.text(lp[0], lp[1], lp[2], str(cid), color=TEXT_COLOR, fontproperties=times,
                ha="center", va="center", zorder=50)
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=25, azim=132)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.set_position([0.005, 0.065, 0.99, 0.925])
    legend_three(figure, times, kai, math, counts)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "L-Bracket topology node-edge graph",
                             "Software": "generate_lbracket_figure_4_5b_topology_graph_v1.py"})
    figure.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "L-Bracket topology node-edge graph", "Date": "2026-07-23"})
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
        "figure": "圖 4.5(b) L型板拓樸關係空間視覺化（v1 節點-邊圖）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "scheme": "mutually_exclusive_most_specific",
        "edge_counts": edge_counts,
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "model_source": "verified evaluated mesh (faint context)",
            "relations_source": "confirmed v3 TopologyEdges",
            "encoding": "node = 語義特徵面形心; edge colour = mutually-exclusive stored type",
            "palette_aligned_with": "圖 4.5(a) v4",
            "legend": "一般相鄰 / 正交相鄰 / 端面關係 (uniform three-type)",
            "validation_overall": validation["overall"],
        },
        "format": {"figure_size_in": [5.70, 4.35], "dpi": DPI,
                   "view": {"elevation": 25, "azimuth": 132, "projection": "orthographic"},
                   "chinese_font": "DFKai-SB 12 pt", "english_numbers_font": "Times New Roman 12 pt",
                   "title_inside_figure": False, "occupancy": occ, "svg_check": svg_check},
        "source_sha256": {p.name: sha256(DATA_DIR / p.name) for p in [
            Path("TopologyEdges_L_Bracket_chapter3_verified.csv"),
            Path("FaceSummary_L_Bracket_chapter3_verified.csv"),
            Path("BlendEvaluatedMesh_L_Bracket.stl")]},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg)},
        "release_boundary": "Only Figure 4.5(b) v1 (graph) is generated; awaiting user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate L-Bracket Figure 4.5(b) v1 topology node-edge graph.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps({"edge_counts": result["summary"]["edge_counts"],
                      "occ_w": round(result["summary"]["format"]["occupancy"]["width_fraction"], 3),
                      "dejavu": result["summary"]["format"]["svg_check"]["dejavu_sans_occurrences"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
