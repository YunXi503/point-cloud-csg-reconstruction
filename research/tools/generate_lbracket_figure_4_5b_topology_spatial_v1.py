"""Figure 4.5(b) — L-Bracket topology spatial visualization (single view).

Standalone regeneration after Figure 4.5(a) v3 was user-confirmed. The model
is the verified evaluated mesh; blue solid lines are the 18 OrthogonalAdjacency
contact boundaries and orange dashed rings are the 6 EndCap boundaries, both
taken from the confirmed v3 TopologyEdges. Colours are aligned to the confirmed
Figure 4.5(a) v3 palette so the 4.5(a)/(b) pair is consistent.
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
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"

FIGURE_STEM = "圖4.5b_L型板_拓樸關係空間視覺化_v1"
DPI = 450

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

# Palette aligned with confirmed Figure 4.5(a) v3.
ORTHOGONAL_COLOR = "#17679A"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#D9DEE2"
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
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": 12,
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "l-bracket-figure-4-5b-spatial-260723-v1",
            "savefig.dpi": DPI,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return times, kai, math


def equal_3d(ax: Any, xyz: np.ndarray) -> None:
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = float(np.max(maximum - minimum) / 2.0) * 0.92
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1), zoom=1.22)


def content_occupancy(image_path: Path) -> dict:
    with Image.open(image_path).convert("RGB") as image:
        array = np.asarray(image)
        mask = np.any(array < 248, axis=2)
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            raise ValueError("Rendered figure is blank.")
        left, right = int(xs.min()), int(xs.max())
        top, bottom = int(ys.min()), int(ys.max())
        return {
            "pixel_width": image.width,
            "pixel_height": image.height,
            "bbox": [left, top, right, bottom],
            "width_fraction": (right - left + 1) / image.width,
            "height_fraction": (bottom - top + 1) / image.height,
            "dpi": list(image.info.get("dpi", ())),
        }


def inspect_svg(svg_path: Path) -> dict:
    ET.parse(svg_path)
    text = svg_path.read_text(encoding="utf-8")
    return {
        "xml_parse": "PASS",
        "times_new_roman_occurrences": text.count("Times New Roman"),
        "dfkai_sb_occurrences": text.count("DFKai-SB"),
        "cambria_occurrences": text.count("Cambria"),
        "dejavu_sans_occurrences": text.count("DejaVu Sans"),
    }


def draw_legend(fig, times: FontProperties, kai: FontProperties, math: FontProperties, counts: dict) -> None:
    ortho = int(counts.get("OrthogonalAdjacency", 0))
    endcap = int(counts.get("EndCap", 0))
    y = 0.066
    endcap_dash = (0, (3.0, 1.25))
    # Orthogonal group
    fig.add_artist(Line2D([0.150, 0.212], [y, y], transform=fig.transFigure,
                          color=ORTHOGONAL_COLOR, linewidth=2.1, solid_capstyle="round"))
    fig.text(0.228, y, "⊥", color=ORTHOGONAL_COLOR, fontproperties=math, ha="left", va="center")
    fig.text(0.262, y, "正交", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    fig.text(0.352, y, str(ortho), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")
    # EndCap group
    fig.add_artist(Line2D([0.520, 0.582], [y, y], transform=fig.transFigure,
                          color=ENDCAP_COLOR, linewidth=2.1, linestyle=endcap_dash, solid_capstyle="round"))
    fig.text(0.598, y, "⊙", color=ENDCAP_COLOR, fontproperties=math, ha="left", va="center")
    fig.text(0.632, y, "端面", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    fig.text(0.722, y, str(endcap), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


def generate(output_dir: Path) -> dict:
    times, kai, math = configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    topology_path = DATA_DIR / "TopologyEdges_L_Bracket_chapter3_verified.csv"
    truth_path = DATA_DIR / "GroundTruth_L_Bracket_independent.json"
    mesh_path = DATA_DIR / "BlendEvaluatedMesh_L_Bracket.stl"
    validation_path = DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json"

    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or validation.get("provenance_separation") != "PASS":
        raise ValueError("L-Bracket chapter-3 method and independent truth have not passed; drawing is blocked.")
    topology = pd.read_csv(topology_path)
    counts = topology["EdgeType"].value_counts().to_dict()
    if counts.get("OrthogonalAdjacency") != 18 or counts.get("EndCap") != 6 or len(topology) != 24:
        raise ValueError(f"Unexpected topology counts: {counts}")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    triangles = read_stl_triangles(mesh_path)

    boundaries, _ = shared_boundaries(triangles, truth, topology)

    figure = plt.figure(figsize=(5.70, 3.55), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(triangles, facecolors=MODEL_COLOR, edgecolors="none", linewidths=0, alpha=0.68)
    )
    styles = {
        "OrthogonalAdjacency": (ORTHOGONAL_COLOR, 1.65, "-"),
        "EndCap": (ENDCAP_COLOR, 2.45, (0, (3.0, 1.25))),
        "Adjacency": ("#5B5B5B", 1.5, (0, (1.2, 1.2))),
    }
    for (_, _, edge_type), segments in boundaries.items():
        color, width, line_style = styles[edge_type]
        for start, end in segments:
            ax.plot(
                [start[0], end[0]], [start[1], end[1]], [start[2], end[2]],
                color=color, linewidth=width, linestyle=line_style,
                solid_capstyle="round", alpha=0.99, zorder=30,
            )
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=25, azim=132)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)
    ax.set_position([0.005, 0.075, 0.99, 0.915])

    draw_legend(figure, times, kai, math, counts)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "L-Bracket topology spatial visualization",
                             "Software": "generate_lbracket_figure_4_5b_topology_spatial_v1.py"})
    figure.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "L-Bracket topology spatial visualization",
                             "Date": "2026-07-23",
                             "Creator": "generate_lbracket_figure_4_5b_topology_spatial_v1.py"})
    plt.close(figure)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    occupancy = content_occupancy(png)
    svg_check = inspect_svg(svg)
    if svg_check["dejavu_sans_occurrences"] != 0:
        raise ValueError("Unexpected DejaVu Sans fallback in SVG.")

    endcap_pairs = [
        sorted((int(r.FromClusterID), int(r.ToClusterID)))
        for r in topology.itertuples(index=False)
        if str(r.EdgeType) == "EndCap"
    ]
    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.5(b) L型板拓樸關係空間視覺化（v1）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "purpose": "single-view physical contact-boundary visualization; complements the Fig 4.5(a) matrix",
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "model_source": "verified evaluated mesh BlendEvaluatedMesh_L_Bracket.stl",
            "relations_source": "confirmed v3 TopologyEdges (method output)",
            "encoding": "blue solid line = OrthogonalAdjacency contact boundary; orange dashed ring = EndCap boundary",
            "palette_aligned_with": "圖 4.5(a) v3 (ORTHOGONAL #17679A, ENDCAP #C65D08)",
            "counts": {"OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
                        "EndCap": int(counts.get("EndCap", 0)),
                        "Adjacency": int(counts.get("Adjacency", 0))},
            "endcap_pairs": endcap_pairs,
            "does_not_encode": ["per-face ID labels", "candidate primitive", "CSG"],
            "validation_overall": validation["overall"],
            "provenance_separation": validation.get("provenance_separation"),
        },
        "format": {
            "figure_size_in": [5.70, 3.55],
            "dpi": DPI,
            "view": {"elevation": 25, "azimuth": 132, "projection": "orthographic"},
            "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font": "DFKai-SB 12 pt",
            "symbol_font": "Cambria 12 pt (⊥ ⊙)",
            "title_inside_figure": False,
            "occupancy": occupancy,
            "svg_check": svg_check,
        },
        "source_sha256": {
            topology_path.name: sha256(topology_path),
            truth_path.name: sha256(truth_path),
            mesh_path.name: sha256(mesh_path),
            validation_path.name: sha256(validation_path),
        },
        "outputs": {
            png.name: sha256(png),
            svg.name: sha256(svg),
            str(gray.relative_to(output_dir)): sha256(gray),
        },
        "release_boundary": "Only Figure 4.5(b) v1 is generated. Figure 4.6, body text and Word remain blocked until user confirmation.",
    }
    qa_path = output_dir / f"{FIGURE_STEM}_QA.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "qa": str(qa_path), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate only L-Bracket Figure 4.5(b) topology spatial visualization.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps(result["summary"]["format"]["occupancy"], ensure_ascii=False))
    print("PNG", result["summary"]["outputs"][Path(result["png"]).name])


if __name__ == "__main__":
    main()
