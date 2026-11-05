"""Figure 4.5(a) v4 — L-Bracket topology matrix, mutually-exclusive types.

v4 aligns the figure with Chapter 3 (3.7) and the Chapter 4 body text: each face
pair carries exactly ONE most-specific stored EdgeType. The earlier v1–v3
"overlapping layer" reading (相鄰 24 / 正交 24 / 端面 6) is dropped because 3.7
explicitly forbids counting the same pair as both 相鄰 and 正交相鄰, and the body
text states 18 正交相鄰 + 6 端面關係 (0 一般相鄰). The three-type legend
(一般相鄰 / 正交相鄰 / 端面關係) is uniform across all three cases so L-Bracket,
Stepped Cylinder and Model A read consistently.
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
from matplotlib.patches import Circle, Rectangle
import numpy as np
import pandas as pd
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "L_Bracket_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_L_Bracket_v3逐張審查_260722"

TOPOLOGY = DATA_DIR / "TopologyEdges_L_Bracket_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_L_Bracket_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationSummary_L_Bracket_chapter3.json"

FIGURE_STEM = "圖4.5a_L型板_拓樸關係矩陣_v4"
DPI = 450
FIGSIZE_IN = (5.70, 5.55)

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

GRID_COLOR = "#89949E"
ORTHOGONAL_FILL = "#DCEBF4"
ORTHOGONAL_COLOR = "#17679A"
ENDCAP_FILL = "#FBE7D6"
ENDCAP_COLOR = "#C65D08"
ADJACENCY_FILL = "#ECECEC"
ADJACENCY_COLOR = "#767C82"
TEXT_COLOR = "#20252A"

# Fill and symbol per mutually-exclusive stored EdgeType.
STYLE = {
    "Adjacency": (ADJACENCY_FILL, ADJACENCY_COLOR, "adjacency"),
    "OrthogonalAdjacency": (ORTHOGONAL_FILL, ORTHOGONAL_COLOR, "orthogonal"),
    "EndCap": (ENDCAP_FILL, ENDCAP_COLOR, "endcap"),
}


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
    plt.rcParams.update({
        "font.family": times.get_name(), "font.size": 12,
        "svg.fonttype": "none", "svg.hashsalt": "l-bracket-figure-4-5a-260723-v4",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times, kai


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or validation["five_layer_validation"].get("topology") != "PASS":
        raise ValueError("L-Bracket topology validation is not PASS.")
    if len(topology) != 24:
        raise ValueError("Verified topology must contain 24 relations.")
    if len(faces) != 12 or sorted(faces["ClusterID"].astype(int).tolist()) != list(range(12)):
        raise ValueError("FaceSummary must contain ClusterID 0 through 11.")
    counts = topology["EdgeType"].value_counts().to_dict()
    if counts != {"OrthogonalAdjacency": 18, "EndCap": 6}:
        raise ValueError(f"Unexpected EdgeType counts: {counts}")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")

    topology = topology.sort_values(["FromClusterID", "ToClusterID"]).reset_index(drop=True)
    faces = faces.sort_values("ClusterID").reset_index(drop=True)
    face_lookup = faces.set_index("ClusterID").to_dict("index")

    # Mutual-exclusivity + endcap-per-cylinder invariants (data-checked).
    pairs: set[tuple[int, int]] = set()
    endcap_by_cyl: dict[int, list[int]] = {}
    for r in topology.itertuples(index=False):
        a, b = int(r.FromClusterID), int(r.ToClusterID)
        if a >= b or (a, b) in pairs:
            raise ValueError("Pairs must be unique with the smaller ClusterID first.")
        pairs.add((a, b))
        if str(r.EdgeType) == "EndCap":
            fa, fb = face_lookup[a], face_lookup[b]
            cyl = a if str(fa["FeatureType"]).startswith("Cylinder_") else b
            plane = b if cyl == a else a
            endcap_by_cyl.setdefault(cyl, []).append(plane)
    cyl_ids = sorted(int(c) for c, row in face_lookup.items() if str(row["FeatureType"]).startswith("Cylinder_"))
    for c in cyl_ids:
        if len(endcap_by_cyl.get(c, [])) != 2:
            raise ValueError(f"Cylinder {c} must be closed by exactly two EndCap planes.")

    edge_counts = {
        "Adjacency": int(counts.get("Adjacency", 0)),
        "OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
        "EndCap": int(counts.get("EndCap", 0)),
    }
    return topology, faces, validation, edge_counts


def draw_endcap_symbol(ax, cx: float, cy: float, radius: float = 0.15) -> None:
    ax.add_patch(Circle((cx, cy), radius, facecolor="white", edgecolor=ENDCAP_COLOR, linewidth=1.45))
    ax.add_patch(Circle((cx, cy), radius * 0.17, facecolor=ENDCAP_COLOR, edgecolor="none"))


def draw_orthogonal_symbol(ax, cx: float, cy: float, size: float = 0.17) -> None:
    ax.plot([cx - size, cx + size], [cy + size * 0.45, cy + size * 0.45],
            color=ORTHOGONAL_COLOR, linewidth=1.55, solid_capstyle="round")
    ax.plot([cx, cx], [cy - size, cy + size * 0.45],
            color=ORTHOGONAL_COLOR, linewidth=1.55, solid_capstyle="round")


def draw_adjacency_symbol(ax, cx: float, cy: float, size: float = 0.17) -> None:
    ax.plot([cx - size, cx + size], [cy, cy], color=ADJACENCY_COLOR, linewidth=1.7, solid_capstyle="round")


def draw_cell_symbol(ax, kind: str, cx: float, cy: float) -> None:
    if kind == "orthogonal":
        draw_orthogonal_symbol(ax, cx, cy, size=0.17)
    elif kind == "endcap":
        draw_endcap_symbol(ax, cx, cy, radius=0.15)
    elif kind == "adjacency":
        draw_adjacency_symbol(ax, cx, cy, size=0.17)


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


def generate(output_dir: Path) -> dict:
    times, kai = configure_fonts()
    topology, faces, validation, edge_counts = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    relation_lookup = {(int(r.FromClusterID), int(r.ToClusterID)): str(r.EdgeType)
                       for r in topology.itertuples(index=False)}

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.022, 0.045, 0.956, 0.925])
    ax.set_xlim(-0.48, 11.08)
    ax.set_ylim(12.12, -0.56)
    ax.set_aspect("equal")
    ax.axis("off")

    for first in range(11):
        for second in range(first + 1, 12):
            x, y = second - 1, first
            edge_type = relation_lookup.get((first, second))
            fill = STYLE[edge_type][0] if edge_type else "white"
            ax.add_patch(Rectangle((x, y), 1, 1, facecolor=fill, edgecolor=GRID_COLOR, linewidth=0.78))
            if edge_type:
                draw_cell_symbol(ax, STYLE[edge_type][2], x + 0.50, y + 0.50)

    for second in range(1, 12):
        ax.text(second - 0.5, -0.32, str(second), ha="center", va="center", color=TEXT_COLOR, fontproperties=times)
    for first in range(11):
        ax.text(first - 0.27, first + 0.50, str(first), ha="center", va="center", color=TEXT_COLOR, fontproperties=times)
    ax.text(-0.36, -0.32, "ID", ha="center", va="center", color=TEXT_COLOR, fontproperties=times)

    # Uniform three-type legend (mutually exclusive): 一般相鄰 / 正交相鄰 / 端面關係.
    ly = 11.72
    draw_adjacency_symbol(ax, 0.18, ly, size=0.16)
    ax.text(0.46, ly, "一般相鄰", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(2.36, ly, str(edge_counts["Adjacency"]), ha="left", va="center", color=TEXT_COLOR, fontproperties=times)
    draw_orthogonal_symbol(ax, 3.24, ly, size=0.15)
    ax.text(3.52, ly, "正交相鄰", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(5.42, ly, str(edge_counts["OrthogonalAdjacency"]), ha="left", va="center", color=TEXT_COLOR, fontproperties=times)
    draw_endcap_symbol(ax, 6.54, ly, radius=0.14)
    ax.text(6.82, ly, "端面關係", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(8.72, ly, str(edge_counts["EndCap"]), ha="left", va="center", color=TEXT_COLOR, fontproperties=times)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(png, dpi=DPI, metadata={"Title": "L-Bracket topology matrix (v4, mutually-exclusive types)",
                                        "Software": "generate_lbracket_figure_4_5a_topology_matrix_v4.py"})
    fig.savefig(svg, format="svg", metadata={"Title": "L-Bracket topology matrix (v4)", "Date": "2026-07-23",
                                             "Creator": "generate_lbracket_figure_4_5a_topology_matrix_v4.py"})
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    occ = content_occupancy(png)
    if occ["width_fraction"] < 0.80 or occ["height_fraction"] < 0.80:
        raise ValueError(f"Excessive white space: {occ}")
    left, top, right, bottom = occ["bbox"]
    if left < 20 or top < 20 or right > occ["pixel_width"] - 21 or bottom > occ["pixel_height"] - 21:
        raise ValueError(f"Content reaches crop safety margin: {occ}")
    svg_check = inspect_svg(svg)
    if svg_check["dejavu_sans_occurrences"] != 0:
        raise ValueError("Unexpected DejaVu Sans fallback in SVG.")

    orthogonal_pairs = [[int(r.FromClusterID), int(r.ToClusterID)] for r in topology.itertuples(index=False)
                        if str(r.EdgeType) == "OrthogonalAdjacency"]
    endcap_pairs = [[int(r.FromClusterID), int(r.ToClusterID)] for r in topology.itertuples(index=False)
                    if str(r.EdgeType) == "EndCap"]
    qa = {
        "schema_version": "2.0",
        "figure": "圖 4.5(a) L型板拓樸關係矩陣（v4 互斥型別）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "revision_note": "v4 每一面對只顯示一個最具體儲存型別，與 3.7『避免重複計入相鄰與正交相鄰』及第四章正文 18 正交相鄰＋6 端面（0 一般相鄰）完全一致；v1–v3 的重疊分層數法停用、降為差異追溯。三型別圖例統一。",
        "scheme": "mutually_exclusive_most_specific",
        "edge_counts": edge_counts,
        "data": {
            "face_ids": list(range(12)),
            "possible_unordered_pairs": 66,
            "orthogonal_pairs": orthogonal_pairs,
            "endcap_pairs": endcap_pairs,
            "adjacency_pairs": [],
            "sum_check": sum(edge_counts.values()),
        },
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "rule": "每一面對只指定一個最具體關係（端面 > 正交相鄰 > 一般相鄰）",
            "matches_body_text": "4.3 與 4.5：18 正交相鄰 + 6 端面關係，0 一般相鄰",
            "validation_overall": validation["overall"],
        },
        "format": {"figure_size_in": list(FIGSIZE_IN), "dpi": DPI,
                   "chinese_font": "DFKai-SB 12 pt", "english_numbers_font": "Times New Roman 12 pt",
                   "legend": "一般相鄰 / 正交相鄰 / 端面關係 (uniform three-type)",
                   "occupancy": occ, "svg_check": svg_check},
        "source_sha256": {TOPOLOGY.name: sha256(TOPOLOGY), FACES.name: sha256(FACES), VALIDATION.name: sha256(VALIDATION)},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg)},
        "release_boundary": "Only Figure 4.5(a) v4 is generated; awaiting user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate L-Bracket Figure 4.5(a) v4 (mutually-exclusive types).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps({"edge_counts": result["summary"]["edge_counts"],
                      "occupancy_w": result["summary"]["format"]["occupancy"]["width_fraction"],
                      "dejavu": result["summary"]["format"]["svg_check"]["dejavu_sans_occurrences"],
                      "png": result["summary"]["outputs"][Path(result["png"]).name][:16]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
