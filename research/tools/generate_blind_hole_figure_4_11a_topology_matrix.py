"""Figure 4.11(a) — Blind-Hole Hex Base topology matrix, mutually-exclusive types.

Same figure family as the confirmed Model A 圖4.8(a) v2 (staircase upper triangle,
ID labels at the head of each row/column, uniform three-type legend along the
bottom, DFKai-SB + Times New Roman, 450 dpi, greyscale QA copy, QA JSON).

Case facts (all asserted, never hard-drawn):
  * 12 accepted semantic faces with CONTIGUOUS ClusterIDs 0-11, so unlike Model A
    this case needs no "non-contiguous ClusterID" caption note.
  * 22 relations = 12 OrthogonalAdjacency + 6 Adjacency + 4 EndCap.
  * The 4 EndCap pairs are (0,9), (0,10), (1,10), (1,11); (1,11) couples the blind
    hole side wall with the blind hole floor and is the evidence for a BLIND hole
    (a through hole would leave the inner cylinder without a floor end cap).
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
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260725" / "Blind_Hole_Hex_Base_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Blind_Hole_Hex_Base_260725"

TOPOLOGY = DATA_DIR / "TopologyEdges_Blind_Hole_Hex_Base_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_Blind_Hole_Hex_Base_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationAgainstIndependentTruth_Blind_Hole_Hex_Base.json"

FIGURE_STEM = "圖4.11a_盲孔六角座_拓樸關係矩陣"
DPI = 450
# Scaled from 圖4.8(a) v2 (13 faces, 5.30 x 5.86 in) so that one data unit keeps
# the same physical size and the fonts stay visually identical at 12 pt.
FIGSIZE_IN = (4.71, 5.43)

EXPECTED_FACE_COUNT = 12
EXPECTED_FACE_IDS = list(range(EXPECTED_FACE_COUNT))  # contiguous 0-11
EXPECTED_TOTAL_RELATIONS = 22
EXPECTED_COUNTS = {"OrthogonalAdjacency": 12, "Adjacency": 6, "EndCap": 4}
EXPECTED_ENDCAP_PAIRS = [(0, 9), (0, 10), (1, 10), (1, 11)]
BLIND_HOLE_ENDCAP_PAIR = (1, 11)
EXPECTED_ROLES = {
    0: "ring_outer_side", 1: "blind_hole_side", 2: "hex_bottom",
    3: "hex_side_6", 4: "hex_side_3", 5: "hex_side_5",
    6: "hex_side_2", 7: "hex_side_4", 8: "hex_side_1",
    9: "hex_shelf", 10: "ring_top", 11: "blind_hole_floor",
}

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
        "svg.fonttype": "none", "svg.hashsalt": "blind-hole-hex-base-figure-4-11a-260725",
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times, kai


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, list[int], dict]:
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or validation["five_layer_validation"].get("topology") != "PASS":
        raise ValueError("Blind-Hole Hex Base topology validation is not PASS.")
    if validation.get("method_source_separation", {}).get("status") != "PASS":
        raise ValueError("Method / independent truth separation is not PASS.")
    if int(validation["counts"]["accepted_faces"]) != EXPECTED_FACE_COUNT:
        raise ValueError(f"Validation accepted_faces != {EXPECTED_FACE_COUNT}.")
    if int(validation["counts"]["topology_edges"]) != EXPECTED_TOTAL_RELATIONS:
        raise ValueError(f"Validation topology_edges != {EXPECTED_TOTAL_RELATIONS}.")
    if len(topology) != EXPECTED_TOTAL_RELATIONS:
        raise ValueError(f"Verified topology must contain {EXPECTED_TOTAL_RELATIONS} relations.")

    face_ids = sorted(faces["ClusterID"].astype(int).tolist())
    if len(faces) != EXPECTED_FACE_COUNT or face_ids != EXPECTED_FACE_IDS:
        raise ValueError(f"Unexpected FaceSummary ClusterIDs: {face_ids}")
    # This case's ClusterIDs are contiguous; the caption must NOT carry Model A's
    # non-contiguous note.
    if face_ids != list(range(min(face_ids), max(face_ids) + 1)):
        raise ValueError("ClusterIDs were expected to be contiguous for this case.")

    counts = topology["EdgeType"].value_counts().to_dict()
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"Unexpected EdgeType counts: {counts}")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")

    topology = topology.sort_values(["FromClusterID", "ToClusterID"]).reset_index(drop=True)
    faces = faces.sort_values("ClusterID").reset_index(drop=True)
    face_lookup = faces.set_index("ClusterID").to_dict("index")

    roles = {int(key): str(row["SemanticRole"]) for key, row in face_lookup.items()}
    if roles != EXPECTED_ROLES:
        raise ValueError(f"Unexpected SemanticRole assignment: {roles}")

    # Mutual exclusivity: each unordered pair appears once, smaller ClusterID first.
    pairs: set[tuple[int, int]] = set()
    endcap_by_cylinder: dict[int, list[int]] = {}
    endcap_pairs: list[tuple[int, int]] = []
    adjacency_pairs: list[tuple[int, int]] = []
    orthogonal_pairs: list[tuple[int, int]] = []
    for row in topology.itertuples(index=False):
        first, second = int(row.FromClusterID), int(row.ToClusterID)
        if first >= second or (first, second) in pairs:
            raise ValueError("Pairs must be unique with the smaller ClusterID first.")
        if first not in face_lookup or second not in face_lookup:
            raise ValueError(f"Relation references an unknown face: {(first, second)}")
        pairs.add((first, second))
        edge_type = str(row.EdgeType)
        if edge_type == "EndCap":
            endcap_pairs.append((first, second))
            first_is_cylinder = str(face_lookup[first]["FeatureType"]).startswith("Cylinder_")
            cylinder = first if first_is_cylinder else second
            plane = second if cylinder == first else first
            if not str(face_lookup[cylinder]["FeatureType"]).startswith("Cylinder_"):
                raise ValueError(f"EndCap pair without a cylinder: {(first, second)}")
            if not str(face_lookup[plane]["FeatureType"]).startswith("Plane_"):
                raise ValueError(f"EndCap pair without a bounding plane: {(first, second)}")
            endcap_by_cylinder.setdefault(cylinder, []).append(plane)
        elif edge_type == "Adjacency":
            adjacency_pairs.append((first, second))
        else:
            orthogonal_pairs.append((first, second))

    if sorted(endcap_pairs) != EXPECTED_ENDCAP_PAIRS:
        raise ValueError(f"Unexpected EndCap pairs: {sorted(endcap_pairs)}")

    # Every cylinder must be closed by at least two end planes.
    cylinder_ids = sorted(int(key) for key, row in face_lookup.items()
                          if str(row["FeatureType"]).startswith("Cylinder_"))
    if len(cylinder_ids) != 2:
        raise ValueError(f"Expected two cylinders (ring outer wall, blind hole wall): {cylinder_ids}")
    for cylinder in cylinder_ids:
        if len(endcap_by_cylinder.get(cylinder, [])) < 2:
            raise ValueError(f"Cylinder {cylinder} is not closed by at least two EndCap planes.")

    # Blind-hole evidence: the inner cylinder wall is capped by a floor plane.
    hole_side, hole_floor = BLIND_HOLE_ENDCAP_PAIR
    if roles[hole_side] != "blind_hole_side" or roles[hole_floor] != "blind_hole_floor":
        raise ValueError("The blind-hole EndCap pair does not join the hole wall to the hole floor.")
    if BLIND_HOLE_ENDCAP_PAIR not in endcap_pairs:
        raise ValueError("Missing the blind-hole EndCap relation (1,11).")

    # 6 一般相鄰 must each join two hex side walls meeting at 120 deg (|n·n| = 0.5).
    if len(adjacency_pairs) != 6:
        raise ValueError(f"Expected 6 Adjacency relations: {adjacency_pairs}")
    for first, second in adjacency_pairs:
        if not (roles[first].startswith("hex_side_") and roles[second].startswith("hex_side_")):
            raise ValueError(f"Adjacency {(first, second)} does not join two hex side walls.")
    adjacency_dots = [abs(float(row.DirectionDot)) for row in topology.itertuples(index=False)
                      if str(row.EdgeType) == "Adjacency"]
    if not all(abs(value - 0.5) < 1e-6 for value in adjacency_dots):
        raise ValueError(f"Adjacency pairs are not the 120-deg hex side pairs: {adjacency_dots}")

    # 12 正交相鄰 = each of the 6 hex side walls against hex_bottom and hex_shelf.
    hex_sides = sorted(key for key, role in roles.items() if role.startswith("hex_side_"))
    if len(hex_sides) != 6:
        raise ValueError(f"Expected 6 hex side walls: {hex_sides}")
    bottom = next(key for key, role in roles.items() if role == "hex_bottom")
    shelf = next(key for key, role in roles.items() if role == "hex_shelf")
    expected_orthogonal = sorted(tuple(sorted((side, plane)))
                                 for side in hex_sides for plane in (bottom, shelf))
    if sorted(orthogonal_pairs) != expected_orthogonal:
        raise ValueError(f"Unexpected OrthogonalAdjacency pairs: {sorted(orthogonal_pairs)}")

    edge_counts = {
        "Adjacency": int(counts.get("Adjacency", 0)),
        "OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
        "EndCap": int(counts.get("EndCap", 0)),
    }
    assertions = {
        "accepted_faces_is_12": len(faces) == EXPECTED_FACE_COUNT,
        "cluster_ids_contiguous_0_to_11": face_ids == EXPECTED_FACE_IDS,
        "total_relations_is_22": len(topology) == EXPECTED_TOTAL_RELATIONS,
        "edge_type_counts_12_6_4": counts == EXPECTED_COUNTS,
        "endcap_pairs_match": sorted(endcap_pairs) == EXPECTED_ENDCAP_PAIRS,
        "blind_hole_endcap_1_11_present": BLIND_HOLE_ENDCAP_PAIR in endcap_pairs,
        "every_cylinder_closed_by_two_planes": True,
        "adjacency_all_hex_side_120deg": True,
        "orthogonal_is_6_sides_x_bottom_and_shelf": True,
        "semantic_roles_match": roles == EXPECTED_ROLES,
        "all_rule_status_pass": True,
    }
    return topology, faces, validation, edge_counts, face_ids, assertions


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
    topology, faces, validation, edge_counts, face_ids, assertions = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    # Drawn by position; labels keep the real ClusterID (here they coincide).
    index_of = {value: position for position, value in enumerate(face_ids)}
    count = len(face_ids)
    relation_lookup = {(index_of[int(row.FromClusterID)], index_of[int(row.ToClusterID)]): str(row.EdgeType)
                       for row in topology.itertuples(index=False)}

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.022, 0.045, 0.956, 0.925])
    ax.set_xlim(-0.48, count - 0.92)
    ax.set_ylim(count + 0.12, -0.56)
    ax.set_aspect("equal")
    ax.axis("off")

    for first in range(count - 1):
        for second in range(first + 1, count):
            x, y = second - 1, first
            edge_type = relation_lookup.get((first, second))
            fill = STYLE[edge_type][0] if edge_type else "white"
            ax.add_patch(Rectangle((x, y), 1, 1, facecolor=fill, edgecolor=GRID_COLOR, linewidth=0.78))
            if edge_type:
                draw_cell_symbol(ax, STYLE[edge_type][2], x + 0.50, y + 0.50)

    for second in range(1, count):
        ax.text(second - 0.5, -0.32, str(face_ids[second]), ha="center", va="center",
                color=TEXT_COLOR, fontproperties=times)
    for first in range(count - 1):
        ax.text(first - 0.27, first + 0.50, str(face_ids[first]), ha="center", va="center",
                color=TEXT_COLOR, fontproperties=times)
    ax.text(-0.36, -0.32, "ID", ha="center", va="center", color=TEXT_COLOR, fontproperties=times)

    # Uniform three-type legend (mutually exclusive), centred under the matrix.
    # Step is 3.70 (vs 3.95 for the 13-face Model A matrix) so the legend still
    # fits inside the narrower 12-face plotting box; symbols and gaps are identical.
    ly = count - 0.28
    start, step = 0.62, 3.70
    for offset, (symbol, label, value) in enumerate((
        ("adjacency", "一般相鄰", edge_counts["Adjacency"]),
        ("orthogonal", "正交相鄰", edge_counts["OrthogonalAdjacency"]),
        ("endcap", "端面關係", edge_counts["EndCap"]),
    )):
        base = start + step * offset
        if symbol == "adjacency":
            draw_adjacency_symbol(ax, base, ly, size=0.16)
        elif symbol == "orthogonal":
            draw_orthogonal_symbol(ax, base, ly, size=0.15)
        else:
            draw_endcap_symbol(ax, base, ly, radius=0.14)
        ax.text(base + 0.36, ly, label, ha="left", va="center", color=TEXT_COLOR, fontproperties=kai)
        ax.text(base + 2.34, ly, str(value), ha="left", va="center", color=TEXT_COLOR, fontproperties=times)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(png, dpi=DPI, metadata={"Title": "Blind-Hole Hex Base topology matrix (mutually-exclusive types)",
                                        "Software": "generate_blind_hole_figure_4_11a_topology_matrix.py"})
    fig.savefig(svg, format="svg", metadata={"Title": "Blind-Hole Hex Base topology matrix", "Date": "2026-07-25",
                                             "Creator": "generate_blind_hole_figure_4_11a_topology_matrix.py"})
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

    def pairs_of(edge_type: str) -> list[list[int]]:
        return [[int(row.FromClusterID), int(row.ToClusterID)] for row in topology.itertuples(index=False)
                if str(row.EdgeType) == edge_type]

    qa = {
        "schema_version": "2.0",
        "figure": "圖 4.11(a) 盲孔六角座拓樸關係矩陣（互斥型別）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "figure_family": "與已定稿之 圖4.8(a) v2（模型A）同一圖族：階梯上三角、行列首標 ID、底部統一三型別圖例。",
        "scheme": "mutually_exclusive_most_specific",
        "edge_counts": edge_counts,
        "assertions": assertions,
        "data": {
            "face_ids": face_ids,
            "semantic_roles": {str(key): value for key, value in EXPECTED_ROLES.items()},
            "possible_unordered_pairs": len(face_ids) * (len(face_ids) - 1) // 2,
            "orthogonal_pairs": pairs_of("OrthogonalAdjacency"),
            "endcap_pairs": pairs_of("EndCap"),
            "adjacency_pairs": pairs_of("Adjacency"),
            "sum_check": sum(edge_counts.values()),
        },
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "rule": "每一面對只指定一個最具體關係（端面 > 正交相鄰 > 一般相鄰）",
            "matches_body_text": "12 正交相鄰 + 6 一般相鄰 + 4 端面關係 = 22",
            "orthogonal_reading": "6 個六角側面各對六角底面（ID 2）與六角肩面（ID 9），共 12 條。",
            "adjacency_reading": "6 條為相鄰兩個六角側面（法向內積 0.5，夾角 120°）。",
            "endcap_reading": "4 條為 (0,9)、(0,10)、(1,10)、(1,11)；(1,11) 連接盲孔內壁與盲孔底面，"
                              "是判定「盲孔」而非通孔的依據。",
            "validation_overall": validation["overall"],
            "validation_topology": validation["five_layer_validation"]["topology"],
        },
        "cluster_id_is_non_contiguous": False,
        "text_must_mention_non_contiguous_cluster_id": False,
        "cluster_id_note": "本案例 ClusterID 為連續之 0–11（與模型A 的非連續不同），故圖題不需加註非連續說明。",
        "format": {"figure_size_in": list(FIGSIZE_IN), "dpi": DPI,
                   "chinese_font": "DFKai-SB 12 pt", "english_numbers_font": "Times New Roman 12 pt",
                   "title_inside_figure": False,
                   "legend": "一般相鄰 / 正交相鄰 / 端面關係 (uniform three-type)",
                   "occupancy": occ, "svg_check": svg_check},
        "source_sha256": {TOPOLOGY.name: sha256(TOPOLOGY), FACES.name: sha256(FACES),
                          VALIDATION.name: sha256(VALIDATION)},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg),
                    str(gray.relative_to(output_dir)).replace("\\", "/"): sha256(gray)},
        "release_boundary": "Only Figure 4.11(a) is generated; awaiting user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "gray": str(gray), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Blind-Hole Hex Base Figure 4.11(a) topology matrix.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps({"face_ids": result["summary"]["data"]["face_ids"],
                      "edge_counts": result["summary"]["edge_counts"],
                      "assertions": result["summary"]["assertions"],
                      "occupancy_w": round(result["summary"]["format"]["occupancy"]["width_fraction"], 3),
                      "occupancy_h": round(result["summary"]["format"]["occupancy"]["height_fraction"], 3),
                      "dejavu": result["summary"]["format"]["svg_check"]["dejavu_sans_occurrences"],
                      "png": result["summary"]["outputs"][Path(result["png"]).name][:16]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
