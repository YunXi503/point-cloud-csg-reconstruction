from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import numpy as np
import pandas as pd
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "Stepped_Cylinder_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Stepped_Cylinder_v3逐張審查_260722"

TOPOLOGY = DATA_DIR / "TopologyEdges_Stepped_Cylinder_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_Stepped_Cylinder_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationSummary_Stepped_Cylinder_chapter3.json"

FIGURE_STEM = "圖4.2a_階梯狀圓柱_拓樸關係與幾何屬性矩陣_v4"
DPI = 450
FIGSIZE_IN = (5.70, 5.00)

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

GRID_COLOR = "#AEB6BF"
DIAGONAL_COLOR = "#F0F2F4"
ADJACENCY_FILL = "#E7F0F6"
ORTHOGONAL_COLOR = "#2E6F9E"
ENDCAP_COLOR = "#C96512"
TEXT_COLOR = "#25292D"


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
            "svg.fonttype": "none",
            "svg.hashsalt": "stepped-cylinder-v3-figure-4-2a-260722",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return times, kai


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    required = {
        "FromClusterID",
        "ToClusterID",
        "EdgeType",
        "MinDistance",
        "DirectionDot",
        "DistanceThreshold",
        "DirectionThreshold",
        "RuleStatus",
    }
    if not required.issubset(topology.columns):
        raise ValueError(f"Topology is missing columns: {sorted(required - set(topology.columns))}")
    if validation.get("overall") != "PASS" or validation["five_layer_validation"].get("topology") != "PASS":
        raise ValueError("Stepped Cylinder topology validation is not PASS.")
    if len(topology) != 6 or validation["counts"]["observed_topology_edges"] != 6:
        raise ValueError("The verified topology must contain six relations.")
    if len(faces) != 6 or sorted(faces["ClusterID"].astype(int).tolist()) != list(range(6)):
        raise ValueError("FaceSummary must contain ClusterID 0 through 5.")
    if set(topology["EdgeType"]) != {"EndCap"}:
        raise ValueError("This case must contain EndCap relations only.")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")
    topology = topology.sort_values(["FromClusterID", "ToClusterID"]).reset_index(drop=True)
    pairs = []
    for row in topology.itertuples(index=False):
        first = int(row.FromClusterID)
        second = int(row.ToClusterID)
        if first >= second:
            raise ValueError("Topology database must store the lower ClusterID first.")
        if float(row.MinDistance) > float(row.DistanceThreshold):
            raise ValueError("A relation violates the distance condition.")
        if abs(float(row.DirectionDot)) <= float(row.DirectionThreshold):
            raise ValueError("A relation violates the direction condition.")
        pairs.append((first, second))
    if len(set(pairs)) != 6:
        raise ValueError("Topology pairs must be unique.")
    return topology, faces.sort_values("ClusterID"), validation


def draw_endcap_symbol(ax, center_x: float, center_y: float, radius: float = 0.145) -> None:
    ax.add_patch(Circle((center_x, center_y), radius, facecolor="none", edgecolor=ENDCAP_COLOR, linewidth=1.35))
    ax.add_patch(Circle((center_x, center_y), radius * 0.15, facecolor=ENDCAP_COLOR, edgecolor="none"))


def draw_orthogonal_symbol(ax, center_x: float, center_y: float, size: float = 0.17) -> None:
    ax.plot(
        [center_x - size, center_x + size],
        [center_y + size * 0.45, center_y + size * 0.45],
        color=ORTHOGONAL_COLOR,
        linewidth=1.45,
        solid_capstyle="round",
    )
    ax.plot(
        [center_x, center_x],
        [center_y - size, center_y + size * 0.45],
        color=ORTHOGONAL_COLOR,
        linewidth=1.45,
        solid_capstyle="round",
    )


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


def build_explainability(topology: pd.DataFrame, faces: pd.DataFrame) -> list[dict]:
    face_lookup = faces.set_index("ClusterID").to_dict("index")
    rows = []
    for relation in topology.itertuples(index=False):
        first = int(relation.FromClusterID)
        second = int(relation.ToClusterID)
        first_feature = str(face_lookup[first]["FeatureType"])
        second_feature = str(face_lookup[second]["FeatureType"])
        cylinder_id = first if first_feature.startswith("Cylinder_") else second
        plane_id = second if first_feature.startswith("Cylinder_") else first
        cylinder = face_lookup[cylinder_id]
        plane = face_lookup[plane_id]
        axis = np.array([float(cylinder["AxisX"]), float(cylinder["AxisY"]), float(cylinder["AxisZ"])])
        normal = np.array([float(plane["NX"]), float(plane["NY"]), float(plane["NZ"])])
        axis_normal_dot = abs(float(np.dot(axis, normal)))
        if axis_normal_dot <= float(relation.DirectionThreshold):
            raise ValueError(f"Relation {(first, second)} does not support an orthogonal cylinder-plane contact.")
        rows.append(
            {
                "matrix_cell": f"({first}, {second})",
                "from_cluster_id": first,
                "to_cluster_id": second,
                "edge_type": str(relation.EdgeType),
                "from_feature": first_feature,
                "to_feature": second_feature,
                "min_distance_mm": round(float(relation.MinDistance), 9),
                "direction_dot": round(float(relation.DirectionDot), 9),
                "base_adjacency": True,
                "geometric_orthogonal_contact": True,
                "axis_plane_normal_dot": round(axis_normal_dot, 9),
                "stored_most_specific_edge_type": "EndCap",
                "body_text_boundary": "可說明兩面相鄰、在幾何上正交接觸，且資料庫以最具體 EndCap 類型儲存；不得由單一矩陣格直接判定候選單元或布林角色。",
            }
        )
    return rows


def generate(output_dir: Path) -> dict:
    times, kai = configure_fonts()
    topology, faces, validation = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    pairs = {(int(row.FromClusterID), int(row.ToClusterID)) for row in topology.itertuples(index=False)}
    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.08, 0.07, 0.84, 0.87])
    ax.set_xlim(-0.55, 6.02)
    ax.set_ylim(6.48, -0.52)
    ax.set_aspect("equal")
    ax.axis("off")

    for row in range(6):
        for column in range(row, 6):
            is_diagonal = row == column
            is_relation = (row, column) in pairs
            facecolor = DIAGONAL_COLOR if is_diagonal else ADJACENCY_FILL if is_relation else "white"
            ax.add_patch(
                Rectangle(
                    (column, row),
                    1,
                    1,
                    facecolor=facecolor,
                    edgecolor=GRID_COLOR,
                    linewidth=0.85,
                )
            )
            if is_relation:
                draw_orthogonal_symbol(ax, column + 0.32, row + 0.50, size=0.13)
                draw_endcap_symbol(ax, column + 0.68, row + 0.50, radius=0.115)

    for index in range(6):
        ax.text(index + 0.5, -0.30, str(index), ha="center", va="center", color=TEXT_COLOR, fontproperties=times)
        ax.text(-0.32, index + 0.5, str(index), ha="center", va="center", color=TEXT_COLOR, fontproperties=times)
    ax.text(-0.32, -0.30, "ID", ha="center", va="center", color=TEXT_COLOR, fontproperties=times)

    legend_y = 6.32
    ax.add_patch(Rectangle((0.10, legend_y - 0.13), 0.26, 0.26, facecolor=ADJACENCY_FILL, edgecolor=GRID_COLOR, linewidth=0.8))
    ax.text(0.46, legend_y, "相鄰面對", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(1.52, legend_y, "6", ha="left", va="center", color=TEXT_COLOR, fontproperties=times)
    draw_orthogonal_symbol(ax, 2.25, legend_y, size=0.13)
    ax.text(2.50, legend_y, "正交接觸", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(3.56, legend_y, "6", ha="left", va="center", color=TEXT_COLOR, fontproperties=times)
    draw_endcap_symbol(ax, 4.27, legend_y, radius=0.12)
    ax.text(4.52, legend_y, "端面關係", ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
    ax.text(5.58, legend_y, "6", ha="left", va="center", color=TEXT_COLOR, fontproperties=times)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(
        png,
        dpi=DPI,
        metadata={
            "Title": "Stepped Cylinder topology and geometric-property upper-triangular matrix",
            "Author": "Chapter 4 verified-figure pipeline",
            "Subject": "Six adjacent face pairs, six geometric orthogonal contacts, and six stored EndCap relations",
            "Software": "generate_stepped_cylinder_v3_figure_4_2a_topology_matrix.py",
        },
    )
    fig.savefig(
        svg,
        format="svg",
        metadata={
            "Title": "Stepped Cylinder topology and geometric-property upper-triangular matrix",
            "Description": "Six adjacent face pairs; each is a geometric orthogonal contact stored with the most-specific EndCap EdgeType",
            "Creator": "generate_stepped_cylinder_v3_figure_4_2a_topology_matrix.py",
            "Date": "2026-07-22",
            "Keywords": ["Stepped Cylinder", "topology matrix", "EndCap"],
        },
    )
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))
    occupancy = content_occupancy(png)
    if occupancy["width_fraction"] < 0.70 or occupancy["height_fraction"] < 0.78:
        raise ValueError(f"Excessive white space: {occupancy}")
    left, top, right, bottom = occupancy["bbox"]
    safe_margin_px = 20
    if (
        left < safe_margin_px
        or top < safe_margin_px
        or right > occupancy["pixel_width"] - 1 - safe_margin_px
        or bottom > occupancy["pixel_height"] - 1 - safe_margin_px
    ):
        raise ValueError(f"Figure content reaches the crop safety margin: {occupancy}")

    explainability = build_explainability(topology, faces)
    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.2(a) 階梯狀圓柱拓樸關係與幾何屬性矩陣",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "matrix_rule": "undirected pair stored once with lower ClusterID as FromClusterID",
            "relation_hierarchy": "all six rows are adjacent face pairs; geometric orthogonal contact is a derived property; EndCap is the single stored most-specific EdgeType",
            "relation_priority": "EndCap is the most specific applicable EdgeType for all six recorded pairs",
            "visual_encoding": "filled cell represents base adjacency; perpendicular symbol represents geometric orthogonal contact; circle-with-center-dot represents stored EndCap",
            "does_not_encode": ["point-level segmentation", "candidate primitive", "BooleanType", "CSG"],
            "validation_overall": validation["overall"],
            "topology_validation": validation["five_layer_validation"]["topology"],
        },
        "data": {
            "face_ids": list(range(6)),
            "upper_triangle_cells_excluding_diagonal": 15,
            "relation_symbols": int(len(topology)),
            "base_adjacent_pairs": int(len(topology)),
            "geometric_orthogonal_contacts": int(len(topology)),
            "edge_type_counts": {"EndCap": int(len(topology))},
            "generic_adjacency_edge_type_rows": 0,
            "orthogonal_adjacency_edge_type_rows": 0,
            "database_pairs": [[int(row.FromClusterID), int(row.ToClusterID)] for row in topology.itertuples(index=False)],
            "duplicate_unordered_pairs": 0,
            "lower_triangle_symbols": 0,
        },
        "explainability": {
            "matrix_cell_mapping": explainability,
            "figure_claim": "本圖證明六組無向面對皆相鄰、皆為幾何正交接觸，且資料庫各以最具體 EndCap EdgeType 儲存一次。",
            "caption_draft": "本圖將階梯狀圓柱六個語義特徵面的關係以矩陣呈現。淡藍色格表示相鄰面對，垂直符號表示圓柱側面與水平平面在幾何上正交接觸，圓圈中央加點表示資料庫所儲存的最具體端面關係；無向面對只顯示於上三角。",
            "body_text_requirement": "正文須區分相鄰母關係、幾何正交屬性與資料庫最具體 EdgeType；不得把六組面誤寫為不相鄰，也不得新增重複 Adjacency 資料列。",
        },
        "format": {
            "figure_size_in": list(FIGSIZE_IN),
            "figure_width_cm": round(FIGSIZE_IN[0] * 2.54, 3),
            "dpi": DPI,
            "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font": "DFKai-SB 12 pt",
            "title_inside_figure": False,
            "matrix_shape": "upper triangular including blank diagonal",
            "adjacency_encoding": "pale blue cell fill",
            "geometric_orthogonality_encoding": "blue perpendicular symbol",
            "stored_edge_type_encoding": "orange circle-with-center-dot EndCap symbol",
            "occupancy": occupancy,
        },
        "source_sha256": {
            TOPOLOGY.name: sha256(TOPOLOGY),
            FACES.name: sha256(FACES),
            VALIDATION.name: sha256(VALIDATION),
        },
        "outputs": {
            png.name: sha256(png),
            svg.name: sha256(svg),
            str(gray.relative_to(output_dir)): sha256(gray),
        },
        "release_boundary": "Only revised Figure 4.2(a) is generated. Revised Figure 4.2(b) and Figure 4.3 remain blocked until user confirmation.",
    }
    qa_path = output_dir / f"{FIGURE_STEM}_QA.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "qa": str(qa_path), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate only Stepped Cylinder v3 Figure 4.2(a).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
