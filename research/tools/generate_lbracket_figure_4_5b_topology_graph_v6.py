"""Figure 4.5(b) v6 — L-Bracket topology graph, algorithmic (stress) layout.

Earlier 3D-positioned versions piled coincident faces and bent edges. Here the
12 faces are laid out by a Kamada-Kawai / stress-majorization algorithm (graph
distances -> 2D positions) so nodes separate and edge crossings are minimised
automatically. Deterministic circular seed => reproducible. Mutually-exclusive
three-type edges (colour + line style) and the face colour key stay aligned with
Figure 4.5(a) v4.
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
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from scipy.optimize import minimize
from scipy.sparse.csgraph import shortest_path
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"

FIGURE_STEM = "圖4.5b_L型板_拓樸關係圖_v6演算法排版"
DPI = 450

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ADJACENCY_COLOR = "#767C82"
ORTHOGONAL_COLOR = "#17679A"
ENDCAP_COLOR = "#C65D08"
TEXT_COLOR = "#20252A"

EDGE_STYLE = {
    "Adjacency": (ADJACENCY_COLOR, (0, (1.4, 1.4)), 1.2, 0.7),
    "OrthogonalAdjacency": (ORTHOGONAL_COLOR, "-", 1.35, 0.72),
    "EndCap": (ENDCAP_COLOR, (0, (3.4, 1.5)), 2.4, 0.97),
}

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
        "svg.hashsalt": "l-bracket-4-5b-stress-260723-v6",
        "savefig.dpi": DPI, "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times, kai, math


def stress_layout(n: int, edges: list[tuple[int, int]]) -> np.ndarray:
    """Kamada-Kawai stress layout: place nodes so |pi-pj| ~ graph distance."""
    adjacency = np.zeros((n, n), dtype=float)
    for i, j in edges:
        adjacency[i, j] = adjacency[j, i] = 1.0
    graph_dist = shortest_path(adjacency, method="D", unweighted=True)
    finite = np.isfinite(graph_dist)
    graph_dist[~finite] = graph_dist[finite].max() + 1.0  # keep disconnected pairs bounded
    weight = np.zeros_like(graph_dist)
    nonzero = graph_dist > 0
    weight[nonzero] = 1.0 / (graph_dist[nonzero] ** 2)

    # deterministic circular seed
    angles = 2.0 * np.pi * np.arange(n) / n
    seed = np.column_stack([np.cos(angles), np.sin(angles)]) * (n / (2.0 * np.pi))

    iu, ju = np.triu_indices(n, 1)
    target = graph_dist[iu, ju]
    wij = weight[iu, ju]

    def stress(flat: np.ndarray) -> float:
        pos = flat.reshape(n, 2)
        diff = pos[iu] - pos[ju]
        dist = np.sqrt((diff ** 2).sum(axis=1) + 1e-12)
        return float(np.sum(wij * (dist - target) ** 2))

    def gradient(flat: np.ndarray) -> np.ndarray:
        pos = flat.reshape(n, 2)
        grad = np.zeros_like(pos)
        diff = pos[iu] - pos[ju]
        dist = np.sqrt((diff ** 2).sum(axis=1) + 1e-12)
        coeff = (2.0 * wij * (dist - target) / dist)[:, None] * diff
        np.add.at(grad, iu, coeff)
        np.add.at(grad, ju, -coeff)
        return grad.flatten()

    result = minimize(stress, seed.flatten(), jac=gradient, method="L-BFGS-B",
                      options={"maxiter": 5000, "ftol": 1e-12, "gtol": 1e-9})
    pos = result.x.reshape(n, 2)

    # deterministic orientation: align principal axis to x, fix reflection/scale
    pos = pos - pos.mean(axis=0)
    u, s, vt = np.linalg.svd(pos, full_matrices=False)
    pos = pos @ vt.T
    if pos[np.argmax(np.abs(pos[:, 0])), 0] < 0:
        pos[:, 0] *= -1.0
    if pos[np.argmax(np.abs(pos[:, 1])), 1] < 0:
        pos[:, 1] *= -1.0
    span = np.max(pos.max(axis=0) - pos.min(axis=0))
    pos = pos / span * 10.0
    pos = pos - (pos.max(axis=0) + pos.min(axis=0)) / 2.0
    return pos


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


def draw_bottom_key(fig, times, kai, counts: dict) -> None:
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
    fig.text(0.045, 0.088, "面", color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
    x0, dx = 0.130, 0.140
    rows = [0.088, 0.034]
    for cid in range(12):
        x = x0 + (cid % 6) * dx
        y = rows[cid // 6]
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
    validation = json.loads((DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json").read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS":
        raise ValueError("Validation not PASS; drawing blocked.")
    counts = topology["EdgeType"].value_counts().to_dict()
    edges = [(int(r.FromClusterID), int(r.ToClusterID)) for r in topology.itertuples(index=False)]

    pos = stress_layout(12, edges)

    figure = plt.figure(figsize=(5.70, 5.05), facecolor="white")
    ax = figure.add_axes([0.02, 0.20, 0.96, 0.79])
    ax.set_aspect("equal")
    ax.axis("off")

    ordered = sorted(topology.itertuples(index=False),
                     key=lambda r: 1 if str(r.EdgeType) == "EndCap" else 0)
    for r in ordered:
        a, b = int(r.FromClusterID), int(r.ToClusterID)
        color, ls, lw, alpha = EDGE_STYLE[str(r.EdgeType)]
        zo = 8 if str(r.EdgeType) == "EndCap" else 4
        ax.plot([pos[a, 0], pos[b, 0]], [pos[a, 1], pos[b, 1]], color=color, linestyle=ls,
                linewidth=lw, alpha=alpha, zorder=zo, solid_capstyle="round")
    for cid in range(12):
        ax.add_patch(Circle((pos[cid, 0], pos[cid, 1]), 0.42, facecolor=FACE_PALETTE[cid],
                            edgecolor="#2A2A2A", linewidth=0.9, zorder=20))
    margin = 0.9
    ax.set_xlim(pos[:, 0].min() - margin, pos[:, 0].max() + margin)
    ax.set_ylim(pos[:, 1].min() - margin, pos[:, 1].max() + margin)

    draw_bottom_key(figure, times, kai, counts)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white",
                   metadata={"Title": "L-Bracket topology graph (stress layout)",
                             "Software": "generate_lbracket_figure_4_5b_topology_graph_v6.py"})
    figure.savefig(svg, format="svg", facecolor="white",
                   metadata={"Title": "L-Bracket topology graph v6", "Date": "2026-07-23"})
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
        "figure": "圖 4.5(b) L型板拓樸關係圖（v6 演算法排版）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "layout": "Kamada-Kawai / stress majorisation (deterministic circular seed, L-BFGS-B)",
        "scheme": "mutually_exclusive_most_specific",
        "edge_counts": edge_counts,
        "note": "節點位置由拓樸圖距離決定，非零件實際座標；真實面位見圖 4.4／FaceSummary。",
        "encoding": {
            "node_colour": "12 distinct face colours; ID via bottom colour key",
            "edge": "正交相鄰 blue solid / 端面關係 orange dashed / 一般相鄰 gray dotted",
        },
        "method_alignment": {"chapter_3_section": "3.7", "palette_aligned_with": "圖 4.5(a) v4",
                             "validation_overall": validation["overall"]},
        "format": {"figure_size_in": [5.70, 5.05], "dpi": DPI, "title_inside_figure": False,
                   "occupancy": occ, "svg_check": svg_check},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg)},
        "release_boundary": "Only Figure 4.5(b) v6 is generated; awaiting user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate L-Bracket Figure 4.5(b) v6 stress-layout topology graph.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps({"edge_counts": result["summary"]["edge_counts"],
                      "occ_w": round(result["summary"]["format"]["occupancy"]["width_fraction"], 3),
                      "dejavu": result["summary"]["format"]["svg_check"]["dejavu_sans_occurrences"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
