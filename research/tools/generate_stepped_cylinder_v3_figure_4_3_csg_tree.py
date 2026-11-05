from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle
import numpy as np
import pandas as pd
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "Stepped_Cylinder_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Stepped_Cylinder_v3逐張審查_260722"

CANDIDATES = DATA_DIR / "PrimitiveCandidates_Stepped_Cylinder_chapter3_verified.csv"
CSG_TREE = DATA_DIR / "CSGTree_Stepped_Cylinder_chapter3_verified.json"
VALIDATION = DATA_DIR / "ValidationSummary_Stepped_Cylinder_chapter3.json"

FIGURE_STEM = "圖4.3_階梯狀圓柱_階層式CSG推論_v1"
DPI = 450
FIGSIZE_IN = (5.70, 4.75)

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

LOWER_COLOR = "#5B9F7C"
UPPER_COLOR = "#5B9696"
SUBTRACT_COLOR = "#D18432"
OUTLINE_COLOR = "#30363D"
ARROW_COLOR = "#626A73"
WHITE = "#FFFFFF"


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
            "axes.unicode_minus": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "stepped-cylinder-v3-figure-4-3-csg-260722",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return times, kai


def load_and_validate() -> tuple[pd.DataFrame, dict, dict, dict]:
    candidates = pd.read_csv(CANDIDATES, encoding="utf-8-sig").sort_values("CandidateID").reset_index(drop=True)
    tree = json.loads(CSG_TREE.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    if validation.get("overall") != "PASS":
        raise ValueError("Stepped Cylinder overall validation is not PASS.")
    if validation["five_layer_validation"].get("primitive_candidates") != "PASS":
        raise ValueError("Primitive-candidate validation is not PASS.")
    if validation["five_layer_validation"].get("csg_symbolic_tree") != "PASS":
        raise ValueError("CSG symbolic-tree validation is not PASS.")
    if len(candidates) != 3 or set(candidates["RuleStatus"]) != {"PASS"}:
        raise ValueError("Expected three PASS candidate rows.")

    expected = {
        "SC_U01": {"PrimitiveType": "CylinderLower", "BooleanType": "Union", "RelatedClusters": "1;2;3"},
        "SC_U02": {"PrimitiveType": "CylinderUpper", "BooleanType": "Union", "RelatedClusters": "3;4;5"},
        "SC_D01": {"PrimitiveType": "ThroughHole", "BooleanType": "Difference", "RelatedClusters": "0;2;4"},
    }
    lookup = candidates.set_index("CandidateID")
    if set(lookup.index) != set(expected):
        raise ValueError(f"Unexpected candidate IDs: {sorted(lookup.index)}")
    for candidate_id, fields in expected.items():
        for field, expected_value in fields.items():
            if str(lookup.loc[candidate_id, field]) != expected_value:
                raise ValueError(f"{candidate_id}.{field} does not match the verified result.")

    expected_tree = {
        "op": "Difference",
        "base": {
            "op": "Union",
            "children": [{"candidate": "SC_U01"}, {"candidate": "SC_U02"}],
        },
        "subtractors": [{"candidate": "SC_D01"}],
    }
    if tree.get("tree") != expected_tree:
        raise ValueError("Canonical CSG tree does not match the verified hierarchy.")

    geometry = {
        "lower_radius_mm": float(lookup.loc["SC_U01", "Radius"]),
        "lower_depth_mm": float(lookup.loc["SC_U01", "Depth"]),
        "upper_radius_mm": float(lookup.loc["SC_U02", "Radius"]),
        "upper_depth_mm": float(lookup.loc["SC_U02", "Depth"]),
        "hole_radius_mm": float(lookup.loc["SC_D01", "Radius"]),
        "hole_depth_mm": float(lookup.loc["SC_D01", "Depth"]),
    }
    if not all(value > 0 for value in geometry.values()):
        raise ValueError("Candidate dimensions must be positive.")
    if abs((geometry["lower_depth_mm"] + geometry["upper_depth_mm"]) - geometry["hole_depth_mm"]) > 1e-6:
        raise ValueError("The verified through-hole depth must span the union base height.")
    if not (geometry["hole_radius_mm"] < geometry["upper_radius_mm"] < geometry["lower_radius_mm"]):
        raise ValueError("Verified radius ordering is inconsistent with the stepped-cylinder hierarchy.")
    return candidates, tree, validation, geometry


def arrow(ax, start: tuple[float, float], end: tuple[float, float]) -> None:
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.45,
        color=ARROW_COLOR,
        shrinkA=1.5,
        shrinkB=1.5,
        zorder=1,
    )
    ax.add_patch(patch)


def draw_operator(ax, center: tuple[float, float], symbol: str, times: fm.FontProperties) -> None:
    x, y = center
    ax.add_patch(Circle((x, y), radius=6.6, facecolor=WHITE, edgecolor=OUTLINE_COLOR, linewidth=1.4, zorder=4))
    if symbol == "Union":
        left_y = np.linspace(y + 2.5, y - 0.5, 20)
        arc_theta = np.linspace(np.pi, 2.0 * np.pi, 40)
        right_y = np.linspace(y - 0.5, y + 2.5, 20)
        union_x = np.concatenate(
            [
                np.full_like(left_y, x - 2.6),
                x + 2.6 * np.cos(arc_theta),
                np.full_like(right_y, x + 2.6),
            ]
        )
        union_y = np.concatenate(
            [
                left_y,
                y - 0.5 + 2.6 * np.sin(arc_theta),
                right_y,
            ]
        )
        ax.plot(union_x, union_y, color=OUTLINE_COLOR, linewidth=1.6, solid_capstyle="round", zorder=5)
    else:
        ax.text(x, y - 0.1, symbol, ha="center", va="center", fontproperties=times, fontsize=19, color=OUTLINE_COLOR, zorder=5)


def draw_candidate_rect(
    ax,
    center_x: float,
    bottom_y: float,
    radius: float,
    depth: float,
    scale: float,
    facecolor: str,
    dashed: bool = False,
) -> tuple[float, float, float, float]:
    width = 2.0 * radius * scale
    height = depth * scale
    left = center_x - width / 2.0
    patch = Rectangle(
        (left, bottom_y),
        width,
        height,
        facecolor=WHITE if dashed else facecolor,
        edgecolor=SUBTRACT_COLOR if dashed else OUTLINE_COLOR,
        linewidth=1.6,
        linestyle=(0, (4.0, 2.7)) if dashed else "-",
        zorder=4,
    )
    ax.add_patch(patch)
    return left, bottom_y, width, height


def stepped_polygon(center_x: float, bottom_y: float, geometry: dict, scale: float) -> np.ndarray:
    lower_r = geometry["lower_radius_mm"] * scale
    upper_r = geometry["upper_radius_mm"] * scale
    lower_h = geometry["lower_depth_mm"] * scale
    upper_h = geometry["upper_depth_mm"] * scale
    return np.array(
        [
            [center_x - lower_r, bottom_y],
            [center_x + lower_r, bottom_y],
            [center_x + lower_r, bottom_y + lower_h],
            [center_x + upper_r, bottom_y + lower_h],
            [center_x + upper_r, bottom_y + lower_h + upper_h],
            [center_x - upper_r, bottom_y + lower_h + upper_h],
            [center_x - upper_r, bottom_y + lower_h],
            [center_x - lower_r, bottom_y + lower_h],
        ]
    )


def draw_union_result(ax, center_x: float, bottom_y: float, geometry: dict, scale: float) -> tuple[float, float, float, float]:
    lower_r = geometry["lower_radius_mm"] * scale
    upper_r = geometry["upper_radius_mm"] * scale
    lower_h = geometry["lower_depth_mm"] * scale
    upper_h = geometry["upper_depth_mm"] * scale
    ax.add_patch(
        Rectangle(
            (center_x - lower_r, bottom_y),
            2 * lower_r,
            lower_h,
            facecolor=LOWER_COLOR,
            edgecolor="none",
            zorder=3,
        )
    )
    ax.add_patch(
        Rectangle(
            (center_x - upper_r, bottom_y + lower_h),
            2 * upper_r,
            upper_h,
            facecolor=UPPER_COLOR,
            edgecolor="none",
            zorder=3,
        )
    )
    polygon = stepped_polygon(center_x, bottom_y, geometry, scale)
    ax.add_patch(Polygon(polygon, closed=True, facecolor="none", edgecolor=OUTLINE_COLOR, linewidth=1.6, zorder=4))
    return center_x - lower_r, bottom_y, 2 * lower_r, lower_h + upper_h


def draw_final_result(ax, center_x: float, bottom_y: float, geometry: dict, scale: float) -> tuple[float, float, float, float]:
    left, bottom, width, height = draw_union_result(ax, center_x, bottom_y, geometry, scale)
    hole_width = 2.0 * geometry["hole_radius_mm"] * scale
    hole_height = geometry["hole_depth_mm"] * scale
    ax.add_patch(
        Rectangle(
            (center_x - hole_width / 2.0, bottom_y),
            hole_width,
            hole_height,
            facecolor=WHITE,
            edgecolor=SUBTRACT_COLOR,
            linewidth=1.6,
            linestyle=(0, (4.0, 2.7)),
            zorder=5,
        )
    )
    return left, bottom, width, height


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
    times, kai = configure_fonts()
    candidates, tree, validation, geometry = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.035, 0.035, 0.93, 0.93])
    ax.set_xlim(10, 170)
    ax.set_ylim(0, 205)
    ax.axis("off")

    # Tree geometry: verified leaves -> Union base -> Difference root -> symbolic result.
    lower_center, upper_center, hole_center = 30.0, 78.0, 151.0
    leaf_bottom = 13.0
    leaf_scale = 0.36
    lower_box = draw_candidate_rect(
        ax,
        lower_center,
        leaf_bottom,
        geometry["lower_radius_mm"],
        geometry["lower_depth_mm"],
        leaf_scale,
        LOWER_COLOR,
    )
    upper_box = draw_candidate_rect(
        ax,
        upper_center,
        leaf_bottom,
        geometry["upper_radius_mm"],
        geometry["upper_depth_mm"],
        leaf_scale,
        UPPER_COLOR,
    )
    hole_bottom = 34.0
    hole_box = draw_candidate_rect(
        ax,
        hole_center,
        hole_bottom,
        geometry["hole_radius_mm"],
        geometry["hole_depth_mm"],
        leaf_scale,
        WHITE,
        dashed=True,
    )

    ax.text(lower_center, 7.2, "SC_U01", ha="center", va="center", fontproperties=times, color=OUTLINE_COLOR)
    ax.text(upper_center, 7.2, "SC_U02", ha="center", va="center", fontproperties=times, color=OUTLINE_COLOR)
    ax.text(hole_center, 27.0, "SC_D01", ha="center", va="center", fontproperties=times, color=OUTLINE_COLOR)

    union_node = (55.0, 61.0)
    union_result_bottom = 78.0
    union_result_scale = 0.37
    union_result = draw_union_result(ax, union_node[0], union_result_bottom, geometry, union_result_scale)

    difference_node = (101.0, 135.0)
    final_bottom = 155.0
    final_scale = 0.43
    final_result = draw_final_result(ax, difference_node[0], final_bottom, geometry, final_scale)

    # Draw arrows behind nodes and geometry.
    arrow(ax, (lower_center, lower_box[1] + lower_box[3] + 1.0), (union_node[0] - 3.0, union_node[1] - 6.0))
    arrow(ax, (upper_center, upper_box[1] + upper_box[3] + 1.0), (union_node[0] + 3.0, union_node[1] - 6.0))
    arrow(ax, (union_node[0], union_node[1] + 6.5), (union_node[0], union_result_bottom - 1.0))
    arrow(
        ax,
        (union_result[0] + union_result[2], union_result[1] + union_result[3] * 0.72),
        (difference_node[0] - 5.0, difference_node[1] - 4.0),
    )
    arrow(
        ax,
        (hole_center - hole_box[2] / 2.0, hole_box[1] + hole_box[3] * 0.88),
        (difference_node[0] + 5.0, difference_node[1] - 4.0),
    )
    arrow(ax, (difference_node[0], difference_node[1] + 6.5), (difference_node[0], final_bottom - 1.0))

    draw_operator(ax, union_node, "Union", times)
    draw_operator(ax, difference_node, "−", times)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(
        png,
        dpi=DPI,
        metadata={
            "Title": "Stepped Cylinder hierarchical CSG inference",
            "Author": "Chapter 4 verified-figure pipeline",
            "Subject": "Union of SC_U01 and SC_U02 followed by Difference of SC_D01",
            "Software": "generate_stepped_cylinder_v3_figure_4_3_csg_tree.py",
        },
    )
    fig.savefig(
        svg,
        format="svg",
        metadata={
            "Title": "Stepped Cylinder hierarchical CSG inference",
            "Description": "Verified symbolic CSG tree with two Union leaves and one Difference subtractor",
            "Creator": "generate_stepped_cylinder_v3_figure_4_3_csg_tree.py",
            "Date": "2026-07-22",
            "Keywords": ["Stepped Cylinder", "CSG", "Union", "Difference", "symbolic tree"],
        },
    )
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))
    occupancy = content_occupancy(png)
    if occupancy["width_fraction"] < 0.82 or occupancy["height_fraction"] < 0.86:
        raise ValueError(f"Excessive white space: {occupancy}")
    left, top, right, bottom = occupancy["bbox"]
    if left < 18 or top < 18 or right > occupancy["pixel_width"] - 19 or bottom > occupancy["pixel_height"] - 19:
        raise ValueError(f"Figure content reaches crop safety margin: {occupancy}")

    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.3 階梯狀圓柱階層式 CSG 推論",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "design_review": {
            "selected_type": "bottom-up symbolic geometry tree",
            "reading_direction": "bottom to top",
            "selected_reason": "matches the verified operation hierarchy while allowing every leaf and intermediate result to be recognized as geometry rather than a text node",
            "rejected_alternatives": {
                "text_only_tree": "exact but forces the reader to translate candidate names into geometry",
                "final_model_only": "cannot prove the Union-before-Difference hierarchy",
            },
            "reviewer_improvements": [
                "use verified candidate proportions rather than generic rectangles",
                "show the intermediate Union base before the Difference node",
                "keep only three CandidateID labels and operation symbols",
            ],
        },
        "method_alignment": {
            "chapter_3_sections": ["3.8 候選幾何單元推論", "3.9 階層式 CSG 推論"],
            "candidate_validation": validation["five_layer_validation"]["primitive_candidates"],
            "csg_validation": validation["five_layer_validation"]["csg_symbolic_tree"],
            "canonical_tree": tree["tree"],
            "reading_statement": "Union(SC_U01, SC_U02) forms the base; Difference removes SC_D01 from that base",
            "does_not_claim": ["executed solid Boolean operation", "STEP export", "IGES export", "B-rep export", "editable CAD solid"],
        },
        "data": {
            "candidate_count": int(len(candidates)),
            "union_candidates": ["SC_U01", "SC_U02"],
            "difference_candidates": ["SC_D01"],
            "candidate_rows": candidates.fillna("").to_dict(orient="records"),
            "geometry_mm": geometry,
            "operation_nodes": ["Union", "Difference"],
            "leaf_nodes": ["SC_U01", "SC_U02", "SC_D01"],
        },
        "explainability": {
            "figure_claim": "先聯集下階與上階圓柱候選形成基體，再由基體減去貫穿孔候選，得到規範化符號樹所表示的階梯狀圓柱結果。",
            "caption_draft": "本圖由下而上呈現階梯狀圓柱的階層式 CSG 推論。下階圓柱與上階圓柱候選先經聯集形成基體，再由差集節點減去貫穿孔候選；最上方圖形為符號推論表示，不代表已輸出 CAD 實體檔。",
            "body_text_requirement": "正文須逐一對應三個 CandidateID、BooleanType 與規範化 JSON 階層，並保留符號推論的成果邊界。",
            "evidence_map": [
                {"figure_element": "SC_U01 lower-cylinder leaf", "evidence": "PrimitiveCandidates SC_U01, BooleanType Union", "evidence_type": "directly stated"},
                {"figure_element": "SC_U02 upper-cylinder leaf", "evidence": "PrimitiveCandidates SC_U02, BooleanType Union", "evidence_type": "directly stated"},
                {"figure_element": "SC_D01 through-hole leaf", "evidence": "PrimitiveCandidates SC_D01, BooleanType Difference", "evidence_type": "directly stated"},
                {"figure_element": "Union intermediate result", "evidence": "CSGTree base.op=Union with sorted children SC_U01, SC_U02", "evidence_type": "directly stated"},
                {"figure_element": "Difference root and final symbol", "evidence": "CSGTree root.op=Difference with subtractor SC_D01", "evidence_type": "directly stated"},
            ],
        },
        "format": {
            "figure_size_in": list(FIGSIZE_IN),
            "figure_width_cm": round(FIGSIZE_IN[0] * 2.54, 3),
            "dpi": DPI,
            "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font": "DFKai-SB 12 pt",
            "title_inside_figure": False,
            "colors": {"lower_union": LOWER_COLOR, "upper_union": UPPER_COLOR, "difference": SUBTRACT_COLOR},
            "occupancy": occupancy,
        },
        "source_sha256": {
            CANDIDATES.name: sha256(CANDIDATES),
            CSG_TREE.name: sha256(CSG_TREE),
            VALIDATION.name: sha256(VALIDATION),
        },
        "outputs": {
            png.name: sha256(png),
            svg.name: sha256(svg),
            str(gray.relative_to(output_dir)): sha256(gray),
        },
        "release_boundary": "Only Figure 4.3 is generated. No Chapter 4 body text or Word document is produced.",
    }
    qa_path = output_dir / f"{FIGURE_STEM}_QA.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "qa": str(qa_path), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate only verified Stepped Cylinder Figure 4.3.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
