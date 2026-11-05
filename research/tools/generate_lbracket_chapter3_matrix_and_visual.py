from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image

from build_stepped_cylinder_independent_truth import read_stl_triangles
from generate_lbracket_chapter3_topology_boundary_figure import shared_boundaries


DPI = 450
TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")
for _font_path in (TIMES_PATH, KAI_PATH, MATH_PATH):
    font_manager.fontManager.addfont(str(_font_path))
TIMES = FontProperties(family="Times New Roman", size=12)
KAI = FontProperties(family="DFKai-SB", size=12)
MATH = FontProperties(family="Cambria", size=12)

ORTHOGONAL_COLOR = "#3F6F93"
ORTHOGONAL_FILL = "#E5EEF4"
ENDCAP_COLOR = "#C86F1A"
ENDCAP_FILL = "#FAEBDD"
ADJACENCY_COLOR = "#5B5B5B"
GRID_COLOR = "#AEB7BE"
MODEL_COLOR = "#D9DEE2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure() -> None:
    if not TIMES_PATH.exists() or not KAI_PATH.exists() or not MATH_PATH.exists():
        raise FileNotFoundError("缺少 Times New Roman、標楷體或 Cambria Math 字型檔。")
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": 12,
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "l-bracket-chapter3-matrix-visual-260722",
            "savefig.dpi": DPI,
            "savefig.facecolor": "white",
        }
    )


def relation_lookup(topology: pd.DataFrame) -> dict[tuple[int, int], str]:
    return {
        tuple(sorted((int(row.FromClusterID), int(row.ToClusterID)))): str(row.EdgeType)
        for row in topology.itertuples(index=False)
    }


def add_symbol_legend(ax: Any, x: float, y: float, counts: dict[str, int], spacing: float) -> None:
    items = [
        ("⊥", int(counts.get("OrthogonalAdjacency", 0)), ORTHOGONAL_COLOR),
        ("⊙", int(counts.get("EndCap", 0)), ENDCAP_COLOR),
        ("—", int(counts.get("Adjacency", 0)), ADJACENCY_COLOR),
    ]
    for index, (symbol, count, color) in enumerate(items):
        item_x = x + index * spacing
        ax.text(
            item_x, y, symbol, color=color,
            fontproperties=MATH if symbol in {"⊥", "⊙"} else TIMES,
            ha="left", va="center",
        )
        ax.text(
            item_x + 0.48, y, str(count), color=color,
            fontproperties=TIMES, ha="left", va="center",
        )


def draw_upper_triangle_matrix(topology: pd.DataFrame, output_dir: Path) -> tuple[Path, Path]:
    lookup = relation_lookup(topology)
    counts = topology["EdgeType"].value_counts().to_dict()
    cluster_ids = list(range(12))
    figure, ax = plt.subplots(figsize=(5.7, 4.15), facecolor="white")
    ax.set_aspect("auto")
    ax.axis("off")
    cell_height = 0.76

    style = {
        "OrthogonalAdjacency": (ORTHOGONAL_FILL, ORTHOGONAL_COLOR, "⊥"),
        "EndCap": (ENDCAP_FILL, ENDCAP_COLOR, "⊙"),
        "Adjacency": ("#EFEFEF", ADJACENCY_COLOR, "—"),
    }
    for row in range(11):
        row_y = row * cell_height
        for column in range(row + 1, 12):
            edge_type = lookup.get((row, column))
            fill = "white" if edge_type is None else style[edge_type][0]
            ax.add_patch(
                Rectangle(
                    (column - 0.5, row_y - cell_height / 2.0), 1.0, cell_height,
                    facecolor=fill, edgecolor=GRID_COLOR, linewidth=0.72,
                )
            )
            if edge_type is not None:
                _, color, symbol = style[edge_type]
                ax.text(
                    column, row_y, symbol, color=color,
                    fontproperties=MATH if symbol in {"⊥", "⊙"} else TIMES,
                    ha="center", va="center",
                )

    for column in cluster_ids:
        ax.text(
            column, -0.62, str(column), fontproperties=TIMES,
            ha="center", va="center", color="#222222",
        )
    for row in range(11):
        ax.text(
            row + 0.12, row * cell_height, str(row), fontproperties=TIMES,
            ha="right", va="center", color="#222222",
        )
    ax.text(-0.66, -0.62, "ID", fontproperties=TIMES, ha="left", va="center", color="#222222")

    # Use the otherwise empty lower-left triangle for the symbol key, avoiding
    # the large unused white area seen in the previous square matrix.
    add_symbol_legend(ax, 0.20, 6.92, counts, spacing=2.35)

    ax.set_xlim(-0.72, 11.58)
    ax.set_ylim(8.18, -0.90)
    figure.subplots_adjust(left=0.015, right=0.995, top=0.995, bottom=0.01)
    base = "圖4.5a_L_Bracket_拓樸關係矩陣_上三角版"
    png = output_dir / f"{base}.png"
    svg = output_dir / f"{base}.svg"
    figure.savefig(png, dpi=DPI, bbox_inches="tight", pad_inches=0.025, facecolor="white")
    figure.savefig(
        svg, bbox_inches="tight", pad_inches=0.025, facecolor="white",
        metadata={"Date": "2026-07-22"},
    )
    plt.close(figure)
    return png, svg


def equal_3d(ax: Any, xyz: np.ndarray) -> None:
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = float(np.max(maximum - minimum) / 2.0) * 0.92
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1), zoom=1.22)


def draw_single_view_visual(
    topology: pd.DataFrame,
    truth: dict[str, Any],
    triangles: np.ndarray,
    output_dir: Path,
) -> tuple[Path, Path]:
    boundaries, _ = shared_boundaries(triangles, truth, topology)
    counts = topology["EdgeType"].value_counts().to_dict()
    figure = plt.figure(figsize=(5.7, 3.55), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(
            triangles, facecolors=MODEL_COLOR, edgecolors="none",
            linewidths=0, alpha=0.68,
        )
    )
    styles = {
        "OrthogonalAdjacency": (ORTHOGONAL_COLOR, 1.65, "-"),
        "EndCap": (ENDCAP_COLOR, 2.45, (0, (3.0, 1.25))),
        "Adjacency": (ADJACENCY_COLOR, 1.5, (0, (1.2, 1.2))),
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
    ax.set_position([0.005, 0.005, 0.99, 0.99])

    legend_items = [
        (0.16, ORTHOGONAL_COLOR, "-", "⊥", int(counts.get("OrthogonalAdjacency", 0))),
        (0.39, ENDCAP_COLOR, (0, (3.0, 1.25)), "⊙", int(counts.get("EndCap", 0))),
    ]
    for x, color, line_style, symbol, count in legend_items:
        figure.add_artist(
            Line2D(
                [x - 0.075, x - 0.018], [0.075, 0.075], transform=figure.transFigure,
                color=color, linewidth=2.1, linestyle=line_style, solid_capstyle="round",
            )
        )
        figure.text(
            x, 0.075, symbol, color=color,
            fontproperties=MATH if symbol in {"⊥", "⊙"} else TIMES,
            ha="left", va="center",
        )
        figure.text(
            x + 0.043, 0.075, str(count), color=color,
            fontproperties=TIMES, ha="left", va="center",
        )

    base = "圖4.5b_L_Bracket_拓樸關係_單視角實體版"
    png = output_dir / f"{base}.png"
    svg = output_dir / f"{base}.svg"
    figure.savefig(png, dpi=DPI, bbox_inches="tight", pad_inches=0.025, facecolor="white")
    figure.savefig(
        svg, bbox_inches="tight", pad_inches=0.025, facecolor="white",
        metadata={"Date": "2026-07-22"},
    )
    plt.close(figure)
    return png, svg


def image_metadata(path: Path) -> dict[str, Any]:
    image = Image.open(path)
    dpi = image.info.get("dpi", (0.0, 0.0))
    return {
        "filename": path.name,
        "sha256": sha256(path),
        "pixels": [int(image.width), int(image.height)],
        "dpi": [float(dpi[0]), float(dpi[1])],
    }


def generate(data_dir: Path, output_dir: Path) -> None:
    configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    topology_path = data_dir / "TopologyEdges_L_Bracket_chapter3_verified.csv"
    truth_path = data_dir / "GroundTruth_L_Bracket_independent.json"
    mesh_path = data_dir / "BlendEvaluatedMesh_L_Bracket.stl"
    validation_path = data_dir / "ValidationSummary_L_Bracket_chapter3.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or validation.get("provenance_separation") != "PASS":
        raise ValueError("L型板第三章方法與獨立真值尚未通過，禁止產圖。")
    topology = pd.read_csv(topology_path)
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    triangles = read_stl_triangles(mesh_path)
    matrix_png, matrix_svg = draw_upper_triangle_matrix(topology, output_dir)
    visual_png, visual_svg = draw_single_view_visual(topology, truth, triangles, output_dir)

    counts = topology["EdgeType"].value_counts().to_dict()
    manifest = {
        "schema_version": "1.0",
        "case": "L-Bracket",
        "data_kind": "real verified experiment result",
        "purpose_separation": {
            "matrix": "upper-triangular database relationship representation",
            "visual": "single-view physical contact-boundary visualization",
        },
        "sources": {
            "topology": {"filename": topology_path.name, "sha256": sha256(topology_path)},
            "truth": {"filename": truth_path.name, "sha256": sha256(truth_path)},
            "mesh": {"filename": mesh_path.name, "sha256": sha256(mesh_path)},
            "validation": {"filename": validation_path.name, "sha256": sha256(validation_path)},
        },
        "relationship_counts": {
            "Adjacency": int(counts.get("Adjacency", 0)),
            "OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
            "EndCap": int(counts.get("EndCap", 0)),
        },
        "font_policy": {
            "Chinese": {"font": "標楷體", "size_pt": 12, "file": str(KAI_PATH)},
            "English_numbers": {"font": "Times New Roman", "size_pt": 12, "file": str(TIMES_PATH)},
            "mathematical_symbols": {"font": "Cambria", "size_pt": 12, "file": str(MATH_PATH)},
            "formal_figure_title_inside_image": False,
        },
        "matrix": {
            "retained_half": "strict upper triangle only; diagonal and lower triangle not drawn",
            "png": image_metadata(matrix_png),
            "svg": {"filename": matrix_svg.name, "sha256": sha256(matrix_svg)},
        },
        "visual": {
            "view": {"elevation": 25, "azimuth": 132, "projection": "orthographic"},
            "png": image_metadata(visual_png),
            "svg": {"filename": visual_svg.name, "sha256": sha256(visual_svg)},
        },
    }
    (output_dir / "L_Bracket_拓樸矩陣與實體視覺化_資料清單.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact L-Bracket topology matrix and physical visualization figures.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    generate(arguments.data_dir.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
