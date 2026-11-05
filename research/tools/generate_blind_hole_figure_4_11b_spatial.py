"""Figure 4.11(b) — Blind-Hole Hex Base topology spatial visualization (single view).

Same figure family as the confirmed Model A 圖4.8(b): the independently evaluated
mesh is drawn as a translucent solid and every method topology relation is drawn ON
the real contact boundary — blue solid = OrthogonalAdjacency, orange dashed =
EndCap, grey dotted = Adjacency (一般相鄰). Contact segments come from the
independent truth mesh via shared_boundaries(); relation TYPES come from the
verified v3 TopologyEdges (method output).

Case facts (asserted, never hard-drawn): 12 accepted faces with CONTIGUOUS
ClusterIDs 0-11, and 22 relations = 12 OrthogonalAdjacency + 6 Adjacency +
4 EndCap. The EndCap ring at ID (1,11) — blind hole wall against blind hole floor
— is the evidence for a blind rather than a through hole, so the chosen view must
show the floor ring inside the bore.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as path_effects
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
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260725" / "Blind_Hole_Hex_Base_chapter3_verified_v3"
TRUTH_DIR = ROOT / "碩士論文" / "第四章驗證結果_260725" / "Blind_Hole_Hex_Base_truth"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Blind_Hole_Hex_Base_260725"

FIGURE_STEM = "圖4.11b_盲孔六角座_拓樸關係空間圖"
DPI = 450

# Chosen after comparing candidate views (see VIEW_CANDIDATES / QA JSON).
VIEW_ELEV, VIEW_AZIM = 16, 140

VIEW_CANDIDATES = [
    {"elevation": 22, "azimuth": 140, "selected": False,
     "note": "與模型A 圖4.8(b) 相同視角。整體可讀，但俯角較大使兩圈半徑 35 mm 的端面環"
             "（六角肩面 z=60 與環台頂面 z=75，相距僅 15 mm）在左右兩側明顯交叉，"
             "孔口環（1,10）也壓在肩面環上，四條端面關係不易一眼分辨。"},
    {"elevation": 16, "azimuth": 140, "selected": True,
     "note": "採用。俯角降低後橢圓短軸變小，四條端面關係環（0,9）、（0,10）、（1,10）、（1,11）"
             "彼此分離；盲孔底面環（1,11）獨立落在半透明實體中段，可直接看出孔底停在 z=25、"
             "未穿透 z=0 的六角底面，即「盲孔」的視覺證據。方位角 140° 不落在六角柱的鏡射面上，"
             "六條 120° 側面相鄰稜線（灰點線）投影為六條互不重疊的線；"
             "六角底面與六角肩面的兩圈六邊形輪廓（共 12 條正交相鄰）也完整可見。"},
    {"elevation": 34, "azimuth": 128, "selected": False,
     "note": "俯角過大：孔底橢圓雖較開，但六角肩面的六邊形輪廓橫切過孔底環，"
             "兩圈半徑 35 mm 的端面環重疊更嚴重，反而更難分辨。"},
]
VIEW_CANDIDATE_EXTRA_NOTE = ("另試過 (26,150)、(20,150)：正對六角平面的方位角會使前後兩對側面稜線投影重合，"
                             "六條一般相鄰只看得到四條位置，故不採用；(48,120)、(30,115) 則因正對六角頂點、"
                             "輪廓與端面環大量重疊而不採用。")

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")
MATH_PATH = Path(r"C:\Windows\Fonts\cambria.ttc")

ORTHOGONAL_COLOR = "#17679A"
ADJACENCY_COLOR = "#3F464C"
ENDCAP_COLOR = "#C65D08"
MODEL_COLOR = "#D9DEE2"
TEXT_COLOR = "#20252A"

EXPECTED_FACE_COUNT = 12
EXPECTED_FACE_IDS = list(range(EXPECTED_FACE_COUNT))
EXPECTED_TOTAL_RELATIONS = 22
EXPECTED_COUNTS = {"OrthogonalAdjacency": 12, "Adjacency": 6, "EndCap": 4}
EXPECTED_ENDCAP_PAIRS = [(0, 9), (0, 10), (1, 10), (1, 11)]
BLIND_HOLE_ENDCAP_PAIR = (1, 11)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure():
    for path in (TIMES_PATH, KAI_PATH, MATH_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Missing font: {path}")
        font_manager.fontManager.addfont(str(path))
    times = FontProperties(family="Times New Roman", size=12)
    kai = FontProperties(family="DFKai-SB", size=12)
    math = FontProperties(family="Cambria", size=12)
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12, "axes.unicode_minus": False,
                         "svg.fonttype": "none", "svg.hashsalt": "blind-hole-hex-base-figure-4-11b-spatial-260725",
                         "savefig.dpi": DPI, "figure.facecolor": "white", "savefig.facecolor": "white"})
    return times, kai, math


def equal_3d(ax, xyz):
    mn, mx = xyz.min(axis=0), xyz.max(axis=0)
    center = (mn + mx) / 2.0
    radius = float(np.max(mx - mn) / 2.0) * 0.92
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1), zoom=1.20)


def content_occupancy(image_path):
    with Image.open(image_path).convert("RGB") as image:
        arr = np.asarray(image)
        mask = np.any(arr < 248, axis=2)
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            raise ValueError("Rendered figure is blank.")
        left, right, top, bottom = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        return {"pixel_width": image.width, "pixel_height": image.height,
                "bbox": [left, top, right, bottom],
                "width_fraction": (right - left + 1) / image.width,
                "height_fraction": (bottom - top + 1) / image.height}


def inspect_svg(svg_path):
    ET.parse(svg_path)
    text = svg_path.read_text(encoding="utf-8")
    return {"xml_parse": "PASS", "dejavu_sans_occurrences": text.count("DejaVu Sans")}


def draw_legend(fig, times, kai, counts):
    ry = 0.062
    groups = [(0.075, ADJACENCY_COLOR, (0, (2.6, 1.8)), "一般相鄰", int(counts.get("Adjacency", 0))),
              (0.400, ORTHOGONAL_COLOR, "-", "正交相鄰", int(counts.get("OrthogonalAdjacency", 0))),
              (0.715, ENDCAP_COLOR, (0, (3.0, 1.25)), "端面關係", int(counts.get("EndCap", 0)))]
    for x, color, ls, label, cnt in groups:
        fig.add_artist(Line2D([x, x + 0.052], [ry, ry], transform=fig.transFigure,
                              color=color, linewidth=2.3, linestyle=ls, solid_capstyle="round"))
        fig.text(x + 0.066, ry, label, color=TEXT_COLOR, fontproperties=kai, ha="left", va="center")
        fig.text(x + 0.205, ry, str(cnt), color=TEXT_COLOR, fontproperties=times, ha="left", va="center")


def load_and_validate():
    topology_path = DATA_DIR / "TopologyEdges_Blind_Hole_Hex_Base_chapter3_verified.csv"
    faces_path = DATA_DIR / "FaceSummary_Blind_Hole_Hex_Base_chapter3_verified.csv"
    validation_path = DATA_DIR / "ValidationAgainstIndependentTruth_Blind_Hole_Hex_Base.json"
    truth_path = TRUTH_DIR / "GroundTruth_Blind_Hole_Hex_Base.json"
    mesh_path = TRUTH_DIR / "Blind_Hole_Hex_Base_evaluated.stl"

    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or \
            validation.get("method_source_separation", {}).get("status") != "PASS":
        raise ValueError("Blind-Hole Hex Base method / independent truth not PASS; drawing blocked.")
    if validation["five_layer_validation"].get("topology") != "PASS":
        raise ValueError("Topology layer is not PASS; drawing blocked.")
    if int(validation["counts"]["accepted_faces"]) != EXPECTED_FACE_COUNT or \
            int(validation["counts"]["topology_edges"]) != EXPECTED_TOTAL_RELATIONS:
        raise ValueError("Validation counts do not match 12 faces / 22 relations.")

    topology = pd.read_csv(topology_path)
    faces = pd.read_csv(faces_path)
    counts = topology["EdgeType"].value_counts().to_dict()
    if counts != EXPECTED_COUNTS or len(topology) != EXPECTED_TOTAL_RELATIONS:
        raise ValueError(f"Unexpected topology counts: {counts}")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")

    face_ids = sorted(faces["ClusterID"].astype(int).tolist())
    if len(faces) != EXPECTED_FACE_COUNT or face_ids != EXPECTED_FACE_IDS:
        raise ValueError(f"Unexpected FaceSummary ClusterIDs: {face_ids}")
    roles = {int(row.ClusterID): str(row.SemanticRole) for row in faces.itertuples(index=False)}

    endcap_pairs = sorted(tuple(sorted((int(row.FromClusterID), int(row.ToClusterID))))
                          for row in topology.itertuples(index=False) if str(row.EdgeType) == "EndCap")
    if endcap_pairs != EXPECTED_ENDCAP_PAIRS:
        raise ValueError(f"Unexpected EndCap pairs: {endcap_pairs}")
    hole_side, hole_floor = BLIND_HOLE_ENDCAP_PAIR
    if roles.get(hole_side) != "blind_hole_side" or roles.get(hole_floor) != "blind_hole_floor":
        raise ValueError("The blind-hole EndCap pair does not join the hole wall to the hole floor.")

    adjacency_pairs = [tuple(sorted((int(row.FromClusterID), int(row.ToClusterID))))
                       for row in topology.itertuples(index=False) if str(row.EdgeType) == "Adjacency"]
    for first, second in adjacency_pairs:
        if not (roles[first].startswith("hex_side_") and roles[second].startswith("hex_side_")):
            raise ValueError(f"Adjacency {(first, second)} does not join two hex side walls.")

    orthogonal_pairs = sorted(tuple(sorted((int(row.FromClusterID), int(row.ToClusterID))))
                              for row in topology.itertuples(index=False)
                              if str(row.EdgeType) == "OrthogonalAdjacency")
    hex_sides = sorted(key for key, role in roles.items() if role.startswith("hex_side_"))
    bottom = next(key for key, role in roles.items() if role == "hex_bottom")
    shelf = next(key for key, role in roles.items() if role == "hex_shelf")
    expected_orthogonal = sorted(tuple(sorted((side, plane)))
                                 for side in hex_sides for plane in (bottom, shelf))
    if len(hex_sides) != 6 or orthogonal_pairs != expected_orthogonal:
        raise ValueError(f"Unexpected OrthogonalAdjacency pairs: {orthogonal_pairs}")

    assertions = {
        "accepted_faces_is_12": True,
        "cluster_ids_contiguous_0_to_11": True,
        "total_relations_is_22": True,
        "edge_type_counts_12_6_4": True,
        "endcap_pairs_match": True,
        "blind_hole_endcap_1_11_present": True,
        "adjacency_all_hex_side_pairs": True,
        "orthogonal_is_6_sides_x_bottom_and_shelf": True,
        "all_rule_status_pass": True,
    }
    paths = {"topology": topology_path, "faces": faces_path, "validation": validation_path,
             "truth": truth_path, "mesh": mesh_path}
    return topology, faces, validation, counts, roles, assertions, paths


def generate(output_dir: Path, elev: int | None = None, azim: int | None = None) -> dict:
    view_elev = VIEW_ELEV if elev is None else int(elev)
    view_azim = VIEW_AZIM if azim is None else int(azim)
    times, kai, _math = configure()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"; qa_dir.mkdir(parents=True, exist_ok=True)

    topology, faces, validation, counts, roles, assertions, paths = load_and_validate()
    truth = json.loads(paths["truth"].read_text(encoding="utf-8"))
    triangles = read_stl_triangles(paths["mesh"])

    boundaries, evidence = shared_boundaries(triangles, truth, topology)

    figure = plt.figure(figsize=(5.70, 4.15), facecolor="white")
    ax = figure.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=MODEL_COLOR, edgecolors="none",
                                         linewidths=0, alpha=0.55))
    styles = {"OrthogonalAdjacency": (ORTHOGONAL_COLOR, 1.65, "-"),
              "EndCap": (ENDCAP_COLOR, 2.45, (0, (3.0, 1.25))),
              "Adjacency": (ADJACENCY_COLOR, 2.7, (0, (2.6, 1.8)))}
    # 繪製層級：一般相鄰置於最上層。端面關係為封閉端環，若層級較高會在與
    # 面間接觸邊重疊處把灰點線整段蓋掉，使一般相鄰在圖上消失。
    zo = {"OrthogonalAdjacency": 20, "EndCap": 26, "Adjacency": 32}
    for (_, _, edge_type), segments in boundaries.items():
        color, width, line_style = styles[edge_type]
        for start, end in segments:
            # 一般相鄰為圖中最短的特徵（共用邊界僅 20–24 mm），且需跨越較粗的
            # 端面環，故加白色描邊光暈以確保可辨識。
            effects = ([path_effects.withStroke(linewidth=width + 2.6, foreground="white")]
                       if edge_type == "Adjacency" else None)
            ax.plot([start[0], end[0]], [start[1], end[1]], [start[2], end[2]],
                    color=color, linewidth=width, linestyle=line_style,
                    solid_capstyle="round", alpha=0.99, zorder=zo[edge_type],
                    path_effects=effects)
    equal_3d(ax, triangles.reshape(-1, 3))
    ax.view_init(elev=view_elev, azim=view_azim)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)
    ax.set_position([0.005, 0.085, 0.99, 0.905])

    draw_legend(figure, times, kai, counts)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    figure.savefig(png, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "Blind-Hole Hex Base topology spatial visualization",
                             "Software": "generate_blind_hole_figure_4_11b_spatial.py"})
    figure.savefig(svg, format="svg", facecolor="white", bbox_inches="tight", pad_inches=0.08,
                   metadata={"Title": "Blind-Hole Hex Base topology spatial visualization", "Date": "2026-07-25",
                             "Creator": "generate_blind_hole_figure_4_11b_spatial.py"})
    plt.close(figure)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    occ = content_occupancy(png)
    svg_check = inspect_svg(svg)
    if svg_check["dejavu_sans_occurrences"] != 0:
        raise ValueError("Unexpected DejaVu Sans fallback in SVG.")

    by_type = {"OrthogonalAdjacency": [], "EndCap": [], "Adjacency": []}
    for (a, b, et), segs in boundaries.items():
        by_type[et].append({"pair": [a, b], "segments": len(segs),
                            "length_mm": round(float(sum(np.linalg.norm(e - s) for s, e in segs)), 3)})
    for key in by_type:
        by_type[key].sort(key=lambda item: item["pair"])
    adjacency_gaps = [float(row.MinDistance) for row in topology.itertuples(index=False)
                      if str(row.EdgeType) == "Adjacency"]
    adjacency_boundary_lengths = [item["length_mm"] for item in by_type["Adjacency"]]
    qa = {
        "schema_version": "2.0",
        "figure": "圖 4.11(b) 盲孔六角座拓樸關係空間視覺化（實體接觸）",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "figure_family": "與已定稿之 圖4.8(b)（模型A）同一圖族：半透明實體＋真實接觸邊界、"
                         "藍實線／橙虛線／灰點線三型別、底部統一圖例。",
        "note_prioritised_department_format_pdf": "已優先對照系上格式PDF（圖無標題、英數 Times New Roman、中文 DFKai-SB、⊥⊙ 用 Cambria）",
        "purpose": "single-view physical contact-boundary visualization; L 4.5(b) / 模型A 4.8(b) 家族",
        "assertions": assertions,
        "method_alignment": {
            "chapter_3_section": "3.7 語義拓樸：拓樸關係建構",
            "model_source": "independent evaluated mesh Blind_Hole_Hex_Base_evaluated.stl (independent truth)",
            "relations_source": "verified v3 TopologyEdges (method output)",
            "encoding": "blue solid=OrthogonalAdjacency; orange dashed=EndCap; grey dotted=Adjacency",
            "counts": {k: int(counts.get(k, 0)) for k in ("Adjacency", "OrthogonalAdjacency", "EndCap")},
            "semantic_roles": {str(key): roles[key] for key in sorted(roles)},
            "adjacency_note": (
                f"方法量得 {len(adjacency_gaps)} 個一般相鄰面對相距 "
                f"{min(adjacency_gaps):.3f}–{max(adjacency_gaps):.3f} mm；於獨立評估網格上此 "
                f"{len(adjacency_boundary_lengths)} 對仍共用 "
                f"{min(adjacency_boundary_lengths):.1f}–{max(adjacency_boundary_lengths):.1f} mm 邊界，"
                "故能畫於實體接觸處，型別仍採方法輸出之 Adjacency（相鄰兩六角側面夾 120°）。"),
            "endcap_note": "4 條端面關係為 (0,9)、(0,10)、(1,10)、(1,11)；其中 (1,11) 連接盲孔內壁與盲孔底面，"
                           "是判定「盲孔」而非通孔的依據，故視角須看得見孔內底面的橙色環。",
            "boundaries_by_type": by_type,
            "boundary_evidence_rows": len(evidence),
            "validation_overall": validation["overall"],
            "method_source_separation": validation["method_source_separation"]["status"],
        },
        "cluster_id_is_non_contiguous": False,
        "text_must_mention_non_contiguous_cluster_id": False,
        "cluster_id_note": "本案例 ClusterID 為連續之 0–11，與模型A 的非連續情形不同，圖題不需加註。",
        "required_caption_note_zh": (
            "本圖以驗證後之獨立評估網格為實體；線段畫於面間真實接觸邊界，型別取自方法之 TopologyEdges："
            "藍實線為正交相鄰、橙虛線為端面關係、灰點線為一般相鄰。ClusterID 為連續之 0–11，"
            "與圖 4.11(a) 一致；孔內下方之橙色環為盲孔內壁與盲孔底面之端面關係，即盲孔之判定依據。"),
        "format": {
            "figure_size_in": [5.70, 4.15], "dpi": DPI,
            "view": {"elevation": view_elev, "azimuth": view_azim, "projection": "orthographic"},
            "view_is_script_default": (view_elev, view_azim) == (VIEW_ELEV, VIEW_AZIM),
            "view_candidates_considered": VIEW_CANDIDATES,
            "view_candidates_extra_note": VIEW_CANDIDATE_EXTRA_NOTE,
            "view_selection_reason": next((item["note"] for item in VIEW_CANDIDATES
                                           if item["elevation"] == view_elev and item["azimuth"] == view_azim),
                                          f"CLI 覆寫視角 elev={view_elev}, azim={view_azim}（非預設候選）。"),
            "english_numbers_font": "Times New Roman 12 pt", "chinese_font": "DFKai-SB 12 pt",
            "title_inside_figure": False, "occupancy": occ, "svg_check": svg_check,
        },
        "source_sha256": {p.name: sha256(p) for p in (paths["topology"], paths["faces"], paths["truth"],
                                                      paths["mesh"], paths["validation"])},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg),
                    str(gray.relative_to(output_dir)).replace("\\", "/"): sha256(gray)},
        "release_boundary": "Only Figure 4.11(b) spatial candidate is generated; awaits user confirmation.",
    }
    (output_dir / f"{FIGURE_STEM}_QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "gray": str(gray),
            "counts": qa["method_alignment"]["counts"], "assertions": assertions,
            "view": qa["format"]["view"],
            "occ_w": round(occ["width_fraction"], 3), "occ_h": round(occ["height_fraction"], 3),
            "dejavu": svg_check["dejavu_sans_occurrences"],
            "png_sha256_16": qa["outputs"][png.name][:16]}


def main():
    parser = argparse.ArgumentParser(
        description="Generate only Blind-Hole Hex Base Figure 4.11(b) topology spatial visualization.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--elev", type=int, default=None, help=f"View elevation override (default {VIEW_ELEV})")
    parser.add_argument("--azim", type=int, default=None, help=f"View azimuth override (default {VIEW_AZIM})")
    args = parser.parse_args()
    print(json.dumps(generate(args.output_dir.resolve(), args.elev, args.azim), ensure_ascii=False))


if __name__ == "__main__":
    main()
