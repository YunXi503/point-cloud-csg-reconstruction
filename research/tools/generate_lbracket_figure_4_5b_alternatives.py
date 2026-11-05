"""Figure 4.5(b) alternatives for user comparison.

Option A: conference-style node-edge topology graph (face centroids as nodes,
          relations as type-coloured edges) over a faint solid for context.
Option B: annotated solid — semi-transparent model with face-ID labels, blue
          orthogonal contact boundaries with ⊥ markers, and orange EndCap rings.

Both read the confirmed v3 data and use the Fig 4.5(a) v3 palette so the whole
4.5 group stays consistent. Neither is a confirmed figure; both await the user's
choice.
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
from generate_lbracket_chapter3_topology_boundary_figure import shared_boundaries


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722" / "圖4.5b_方案比較_260723"

DPI = 450
TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ORTHOGONAL_COLOR = "#17679A"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#D9DEE2"
NODE_COLOR = "#20252A"
TEXT_COLOR = "#20252A"


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
        "svg.hashsalt": "l-bracket-4-5b-alternatives-260723",
        "savefig.dpi": DPI, "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times, kai, math


def equal_3d(ax: Any, xyz: np.ndarray, zoom: float = 1.22) -> None:
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = float(np.max(maximum - minimum) / 2.0) * 0.92
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1), zoom=zoom)


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
    return {"xml_parse": "PASS",
            "dejavu_sans_occurrences": text.count("DejaVu Sans")}


def legend_two(fig, times, kai, math, ortho, endcap, dashed_endcap: bool) -> None:
    y = 0.066
    endcap_style = (0, (3.0, 1.25)) if dashed_endcap else "-"
    fig.add_artist(Line2D([0.150, 0.212], [y, y], transform=fig.transFigure,
                          color=ORTHOGONAL_COLOR, linewidth=2.1, solid_capstyle="round"))
    fig.text(0.228, y, "⊥", color=ORTHOGONAL_COLOR, fontproperties=math, ha="left", va="center")
    fig.text(0.262, y, "正交", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    fig.text(0.352, y, str(ortho), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")
    fig.add_artist(Line2D([0.520, 0.582], [y, y], transform=fig.transFigure,
                          color=ENDCAP_COLOR, linewidth=2.1, linestyle=endcap_style, solid_capstyle="round"))
    fig.text(0.598, y, "⊙", color=ENDCAP_COLOR, fontproperties=math, ha="left", va="center")
    fig.text(0.632, y, "端面", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    fig.text(0.722, y, str(endcap), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


def draw_option_a(faces: pd.DataFrame, topology: pd.DataFrame, triangles: np.ndarray,
                  times, kai, math, output_dir: Path) -> tuple[Path, Path]:
    """Node-edge topology graph over a faint solid."""
    centroids = {int(r.ClusterID): np.array([r.CenterX, r.CenterY, r.CenterZ], dtype=float)
                 for r in faces.itertuples(index=False)}
    counts = topology["EdgeType"].value_counts().to_dict()
    figure = plt.figure(figsize=(5.70, 4.20), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=MODEL_COLOR,
                                         edgecolors="none", linewidths=0, alpha=0.14))
    for r in topology.itertuples(index=False):
        a, b = int(r.FromClusterID), int(r.ToClusterID)
        p, q = centroids[a], centroids[b]
        color = ORTHOGONAL_COLOR if str(r.EdgeType) == "OrthogonalAdjacency" else ENDCAP_COLOR
        ax.plot([p[0], q[0]], [p[1], q[1]], [p[2], q[2]], color=color,
                linewidth=1.7, alpha=0.95, zorder=20, solid_capstyle="round")
    pts = np.array(list(centroids.values()))
    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=42, c=NODE_COLOR, depthshade=False, zorder=40)
    for cid, c in centroids.items():
        ax.text(c[0], c[1], c[2] + 2.4, str(cid), color=TEXT_COLOR, fontproperties=times,
                ha="center", va="bottom", zorder=50)
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=25, azim=132)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.set_position([0.005, 0.075, 0.99, 0.915])
    legend_two(figure, times, kai, math, int(counts.get("OrthogonalAdjacency", 0)),
               int(counts.get("EndCap", 0)), dashed_endcap=False)
    stem = "圖4.5b_L型板_拓樸關係_方案A節點邊圖_v1"
    png, svg = output_dir / f"{stem}.png", output_dir / f"{stem}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08)
    figure.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Date": "2026-07-23"})
    plt.close(figure)
    return png, svg


def draw_option_b(faces: pd.DataFrame, topology: pd.DataFrame, truth: dict, triangles: np.ndarray,
                  times, kai, math, output_dir: Path) -> tuple[Path, Path]:
    """Annotated solid: face-ID labels, ⊥ at orthogonal contacts, EndCap rings."""
    centroids = {int(r.ClusterID): np.array([r.CenterX, r.CenterY, r.CenterZ], dtype=float)
                 for r in faces.itertuples(index=False)}
    counts = topology["EdgeType"].value_counts().to_dict()
    boundaries, _ = shared_boundaries(triangles, truth, topology)
    figure = plt.figure(figsize=(5.70, 4.20), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=MODEL_COLOR,
                                         edgecolors="none", linewidths=0, alpha=0.55))
    ortho_midpoints = []
    for (a, b, edge_type), segments in boundaries.items():
        if edge_type == "OrthogonalAdjacency":
            color, width, ls = ORTHOGONAL_COLOR, 1.6, "-"
            allpts = np.array([p for seg in segments for p in seg])
            ortho_midpoints.append(allpts.mean(axis=0))
        elif edge_type == "EndCap":
            color, width, ls = ENDCAP_COLOR, 2.4, (0, (3.0, 1.25))
        else:
            color, width, ls = "#5B5B5B", 1.4, (0, (1.2, 1.2))
        for start, end in segments:
            ax.plot([start[0], end[0]], [start[1], end[1]], [start[2], end[2]],
                    color=color, linewidth=width, linestyle=ls, solid_capstyle="round",
                    alpha=0.99, zorder=30)
    for mid in ortho_midpoints:
        ax.text(mid[0], mid[1], mid[2], "⊥", color=ORTHOGONAL_COLOR, fontproperties=math,
                ha="center", va="center", zorder=45)
    for cid, c in centroids.items():
        ax.text(c[0], c[1], c[2], str(cid), color=TEXT_COLOR, fontproperties=times,
                ha="center", va="center", zorder=50,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.75))
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=25, azim=132)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.set_position([0.005, 0.075, 0.99, 0.915])
    legend_two(figure, times, kai, math, int(counts.get("OrthogonalAdjacency", 0)),
               int(counts.get("EndCap", 0)), dashed_endcap=True)
    stem = "圖4.5b_L型板_拓樸關係_方案B標註實體_v1"
    png, svg = output_dir / f"{stem}.png", output_dir / f"{stem}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08)
    figure.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Date": "2026-07-23"})
    plt.close(figure)
    return png, svg


def generate(output_dir: Path) -> dict:
    times, kai, math = configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    topology = pd.read_csv(DATA_DIR / "TopologyEdges_L_Bracket_chapter3_verified.csv")
    faces = pd.read_csv(DATA_DIR / "FaceSummary_L_Bracket_chapter3_verified.csv")
    truth = json.loads((DATA_DIR / "GroundTruth_L_Bracket_independent.json").read_text(encoding="utf-8"))
    triangles = read_stl_triangles(DATA_DIR / "BlendEvaluatedMesh_L_Bracket.stl")
    validation = json.loads((DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json").read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS":
        raise ValueError("Validation not PASS; drawing blocked.")

    a_png, a_svg = draw_option_a(faces, topology, triangles, times, kai, math, output_dir)
    b_png, b_svg = draw_option_b(faces, topology, truth, triangles, times, kai, math, output_dir)

    result = {}
    for name, png, svg in (("A", a_png, a_svg), ("B", b_png, b_svg)):
        occ = content_occupancy(png)
        svgc = inspect_svg(svg)
        if svgc["dejavu_sans_occurrences"] != 0:
            raise ValueError(f"Option {name}: DejaVu fallback in SVG.")
        result[name] = {"png": str(png), "svg": str(svg),
                        "png_sha256": sha256(png), "svg_sha256": sha256(svg),
                        "occupancy": occ, "svg_check": svgc}
    (output_dir / "圖4.5b_方案比較_QA.json").write_text(
        json.dumps({"schema_version": "1.0", "status": "AWAITING_USER_CHOICE",
                    "options": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Figure 4.5(b) alternatives A and B for comparison.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    for name in ("A", "B"):
        print(name, result[name]["png_sha256"][:16], result[name]["occupancy"]["width_fraction"])


if __name__ == "__main__":
    main()
