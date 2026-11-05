from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import BoundaryNorm, ListedColormap
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"

RESULT = DATA_DIR / "Result_L_Bracket_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_L_Bracket_chapter3_verified.csv"
TOPOLOGY = DATA_DIR / "TopologyEdges_L_Bracket_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json"

FIGURE_STEM = "圖4.4_L型板_驗證後幾何特徵分割結果_v3"
DPI = 450
FIGSIZE_IN = (5.70, 4.10)
VIEW_ELEV = 25
VIEW_AZIM = 132
POINT_MARKER = "."
POINT_SIZE_PT2 = 5.0
POINT_ALPHA = 1.0
MIN_ADJACENT_DELTA_E = 70.0

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

# Candidate colors are assigned to ClusterID values with the verified topology
# graph.  This affects color selection only: the figure still encodes ClusterID,
# and it does not visualize topology or semantic relations.
PALETTE_CANDIDATES = [
    "#E6F000",
    "#D600A9",
    "#F2C500",
    "#FF3B30",
    "#0057E7",
    "#111111",
    "#7AC943",
    "#8E44AD",
    "#00C2FF",
    "#1B9E77",
    "#C51B7D",
    "#B5D334",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_fonts() -> tuple[fm.FontProperties, fm.FontProperties]:
    if not TIMES_PATH.exists() or not KAI_PATH.exists():
        raise FileNotFoundError("Times New Roman or DFKai-SB font file is missing.")
    fm.fontManager.addfont(str(TIMES_PATH))
    fm.fontManager.addfont(str(KAI_PATH))
    times = fm.FontProperties(family="Times New Roman", size=12)
    kai = fm.FontProperties(family="DFKai-SB", size=12)
    plt.rcParams.update(
        {
            "font.family": times.get_name(),
            "font.size": 12,
            "axes.labelsize": 12,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "l-bracket-v3-figure-4-4-260722",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return times, kai


def hex_to_lab(color: str) -> np.ndarray:
    rgb = np.array([int(color[index : index + 2], 16) for index in (1, 3, 5)], dtype=float) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = np.array(
        [
            0.4124564 * linear[0] + 0.3575761 * linear[1] + 0.1804375 * linear[2],
            0.2126729 * linear[0] + 0.7151522 * linear[1] + 0.0721750 * linear[2],
            0.0193339 * linear[0] + 0.1191920 * linear[1] + 0.9503041 * linear[2],
        ]
    )
    ratio = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    transformed = np.where(ratio > delta**3, np.cbrt(ratio), ratio / (3 * delta**2) + 4 / 29)
    return np.array(
        [116 * transformed[1] - 16, 500 * (transformed[0] - transformed[1]), 200 * (transformed[1] - transformed[2])]
    )


def delta_e76(color_a: str, color_b: str) -> float:
    return float(np.linalg.norm(hex_to_lab(color_a) - hex_to_lab(color_b)))


def assign_topology_contrast_colors(topology: pd.DataFrame) -> tuple[list[str], list[dict]]:
    edges = [
        (int(row.FromClusterID), int(row.ToClusterID))
        for row in topology.itertuples(index=False)
    ]
    labs = np.vstack([hex_to_lab(color) for color in PALETTE_CANDIDATES])
    distances = np.linalg.norm(labs[:, None, :] - labs[None, :, :], axis=2)

    def score(permutation: np.ndarray) -> tuple[float, float]:
        edge_distances = np.array([distances[permutation[a], permutation[b]] for a, b in edges])
        return float(edge_distances.min()), float(edge_distances.mean())

    rng = np.random.default_rng(42)
    best = np.arange(12, dtype=int)
    best_score = score(best)
    for _ in range(200000):
        candidate = rng.permutation(12)
        candidate_score = score(candidate)
        if candidate_score > best_score:
            best, best_score = candidate, candidate_score

    improved = True
    while improved:
        improved = False
        for first in range(11):
            for second in range(first + 1, 12):
                candidate = best.copy()
                candidate[first], candidate[second] = candidate[second], candidate[first]
                candidate_score = score(candidate)
                if candidate_score > best_score:
                    best, best_score = candidate, candidate_score
                    improved = True

    colors = [PALETTE_CANDIDATES[index] for index in best]
    contrast = [
        {
            "from_cluster_id": a,
            "to_cluster_id": b,
            "edge_type": str(topology.iloc[index]["EdgeType"]),
            "delta_e76": round(delta_e76(colors[a], colors[b]), 3),
        }
        for index, (a, b) in enumerate(edges)
    ]
    if min(item["delta_e76"] for item in contrast) < MIN_ADJACENT_DELTA_E:
        raise ValueError(f"Adjacent-face color contrast is below {MIN_ADJACENT_DELTA_E}: {contrast}")
    return colors, contrast


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    points = pd.read_csv(RESULT, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    required = {"X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"}
    if not required.issubset(points.columns):
        raise ValueError(f"Result is missing columns: {sorted(required - set(points.columns))}")
    if validation.get("overall") != "PASS":
        raise ValueError("The L-Bracket v3 validation summary is not PASS.")
    if validation.get("provenance_separation") != "PASS":
        raise ValueError("Method source separation is not PASS.")
    if any(value != "PASS" for value in validation["five_layer_validation"].values()):
        raise ValueError("At least one validation layer is not PASS.")

    expected_counts = validation["counts"]
    if len(points) != expected_counts["total_points"] or len(points) != 10000:
        raise ValueError("Point count is not 10000.")
    ids = sorted(int(value) for value in points["ClusterID"].unique())
    if ids != list(range(12)):
        raise ValueError(f"Expected ClusterID 0 through 11, received {ids}.")
    if int((points["ClusterID"] == -1).sum()) != expected_counts["residual_points"]:
        raise ValueError("Residual-point count does not match validation summary.")
    if len(faces) != expected_counts["accepted_faces"] or len(faces) != 12:
        raise ValueError("Face count is not 12.")
    required_topology = {"FromClusterID", "ToClusterID", "EdgeType", "RuleStatus"}
    if not required_topology.issubset(topology.columns):
        raise ValueError(f"Topology is missing columns: {sorted(required_topology - set(topology.columns))}")
    if len(topology) != expected_counts["topology_edges"] or len(topology) != 24:
        raise ValueError("Topology relation count is not 24.")
    if set(topology["EdgeType"]) != {"OrthogonalAdjacency", "EndCap"}:
        raise ValueError("Unexpected topology relation type.")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")
    pairs = [tuple(sorted((int(row.FromClusterID), int(row.ToClusterID)))) for row in topology.itertuples(index=False)]
    if len(set(pairs)) != 24 or any(a == b for a, b in pairs):
        raise ValueError("Topology relations must be 24 unique unordered face pairs.")

    observed = points.groupby("ClusterID").size().sort_index()
    declared = faces.set_index("ClusterID")["PointCount"].astype(int).sort_index()
    if not observed.equals(declared):
        raise ValueError("Result point counts do not match FaceSummary.")
    return points, faces, topology, validation


def set_axis_style(ax, points: pd.DataFrame, times: fm.FontProperties) -> None:
    ax.view_init(elev=VIEW_ELEV, azim=VIEW_AZIM)
    ax.set_proj_type("ortho")
    ax.set_xlim(float(points["X"].min()), float(points["X"].max()))
    ax.set_ylim(float(points["Y"].min()), float(points["Y"].max()))
    ax.set_zlim(float(points["Z"].min()), float(points["Z"].max()))
    ax.set_box_aspect(
        (
            float(points["X"].max() - points["X"].min()),
            float(points["Y"].max() - points["Y"].min()),
            float(points["Z"].max() - points["Z"].min()),
        ),
        zoom=1.04,
    )
    ax.set_xlabel("X (mm)", fontproperties=times, labelpad=5)
    ax.set_ylabel("Y (mm)", fontproperties=times, labelpad=5)
    ax.set_zlabel("Z (mm)", fontproperties=times, labelpad=4)
    ax.tick_params(axis="x", which="major", labelsize=12, pad=1)
    ax.tick_params(axis="y", which="major", labelsize=12, pad=1)
    ax.tick_params(axis="z", which="major", labelsize=12, pad=1)
    ax.grid(True, color="#C8CDD2", linewidth=0.50, alpha=0.72)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.975, 0.975, 0.975, 1.0))
        axis.pane.set_edgecolor("#AEB5BC")
        for label in axis.get_ticklabels():
            label.set_fontproperties(times)


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


def generate(output_dir: Path) -> dict:
    times, _kai = configure_fonts()
    points, faces, topology, validation = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    cluster_colors, adjacent_contrast = assign_topology_contrast_colors(topology)
    cmap = ListedColormap(cluster_colors, name="lbracket_clusters_v3")
    norm = BoundaryNorm(np.arange(-0.5, 12.5, 1.0), cmap.N)

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.005, 0.065, 0.825, 0.915], projection="3d")
    ax.scatter(
        points["X"],
        points["Y"],
        points["Z"],
        c=points["ClusterID"].astype(int),
        cmap=cmap,
        norm=norm,
        s=POINT_SIZE_PT2,
        marker=POINT_MARKER,
        linewidths=0,
        alpha=POINT_ALPHA,
        depthshade=False,
        rasterized=False,
    )
    set_axis_style(ax, points, times)

    cax = fig.add_axes([0.875, 0.175, 0.027, 0.650])
    colorbar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=cmap),
        cax=cax,
        boundaries=np.arange(-0.5, 12.5, 1.0),
        ticks=np.arange(12),
        spacing="uniform",
    )
    colorbar.set_label("ClusterID", fontproperties=times, rotation=90, labelpad=7)
    colorbar.ax.tick_params(labelsize=12, width=0.8, length=3)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(times)
    colorbar.outline.set_linewidth(0.8)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    png_metadata = {
        "Title": "L-Bracket verified geometric feature segmentation",
        "Author": "Chapter 4 verified-figure pipeline",
        "Subject": "ClusterID 0-11 from method-only v3 output",
        "Software": "generate_lbracket_v3_figure_4_4_segmentation.py",
    }
    svg_metadata = {
        "Title": "L-Bracket verified geometric feature segmentation",
        "Description": "ClusterID 0-11 from method-only v3 output",
        "Creator": "generate_lbracket_v3_figure_4_4_segmentation.py",
        "Date": "2026-07-22",
        "Keywords": ["L-Bracket", "ClusterID", "geometric feature segmentation"],
    }
    fig.savefig(png, dpi=DPI, metadata=png_metadata)
    fig.savefig(svg, format="svg", metadata=svg_metadata)
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    occupancy = content_occupancy(png)
    if occupancy["width_fraction"] < 0.78 or occupancy["height_fraction"] < 0.78:
        raise ValueError(f"Excessive white space: {occupancy}")
    safe_margin_px = 20
    left, top, right, bottom = occupancy["bbox"]
    if (
        left < safe_margin_px
        or top < safe_margin_px
        or right > occupancy["pixel_width"] - 1 - safe_margin_px
        or bottom > occupancy["pixel_height"] - 1 - safe_margin_px
    ):
        raise ValueError(f"Figure content reaches the crop safety margin: {occupancy}")

    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.4 L型板驗證後幾何特徵分割結果",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "method_alignment": {
            "chapter_3_sections": ["3.4 特徵分割", "3.5 平面與圓柱特徵辨識"],
            "visual_encoding": "color represents ClusterID only",
            "topology_use_boundary": "verified topology is used only to assign contrasting colors to adjacent faces",
            "does_not_encode": ["semantic component", "topology edge or relation type", "BooleanType", "CSG"],
            "validation_overall": validation["overall"],
            "provenance_separation": validation["provenance_separation"],
            "five_layer_validation": validation["five_layer_validation"],
        },
        "data": {
            "points": int(len(points)),
            "accepted_points": int((points["ClusterID"] >= 0).sum()),
            "residual_points": int((points["ClusterID"] == -1).sum()),
            "cluster_ids": [int(value) for value in sorted(points["ClusterID"].unique())],
            "faces": int(len(faces)),
            "topology_relations_used_for_color_qa": int(len(topology)),
        },
        "format": {
            "figure_size_in": list(FIGSIZE_IN),
            "figure_width_cm": round(FIGSIZE_IN[0] * 2.54, 3),
            "dpi": DPI,
            "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font_if_used": "DFKai-SB 12 pt",
            "title_inside_figure": False,
            "view_elevation_deg": VIEW_ELEV,
            "view_azimuth_deg": VIEW_AZIM,
            "point_marker": POINT_MARKER,
            "point_size_pt2": POINT_SIZE_PT2,
            "point_alpha": POINT_ALPHA,
            "cluster_colors_by_id": cluster_colors,
            "adjacent_face_contrast_metric": "CIE 1976 Delta E",
            "adjacent_face_minimum_required_delta_e76": MIN_ADJACENT_DELTA_E,
            "adjacent_face_minimum_observed_delta_e76": min(item["delta_e76"] for item in adjacent_contrast),
            "adjacent_face_contrast": adjacent_contrast,
            "occupancy": occupancy,
        },
        "source_sha256": {
            RESULT.name: sha256(RESULT),
            FACES.name: sha256(FACES),
            TOPOLOGY.name: sha256(TOPOLOGY),
            VALIDATION.name: sha256(VALIDATION),
        },
        "outputs": {
            png.name: sha256(png),
            svg.name: sha256(svg),
            str(gray.relative_to(output_dir)): sha256(gray),
        },
        "release_boundary": "Only Figure 4.4 is generated. Later L-Bracket figures remain blocked until user confirmation.",
    }
    qa_path = output_dir / f"{FIGURE_STEM}_QA.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "qa": str(qa_path), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate only the L-Bracket v3 Figure 4.4 review image.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
