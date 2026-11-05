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
from PIL import Image, ImageOps


ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260722" / "Stepped_Cylinder_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Stepped_Cylinder_v3逐張審查_260722"

FACES = DATA_DIR / "FaceSummary_Stepped_Cylinder_chapter3_verified.csv"
TOPOLOGY = DATA_DIR / "TopologyEdges_Stepped_Cylinder_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationSummary_Stepped_Cylinder_chapter3.json"

FIGURE_STEM = "圖4.2b_階梯狀圓柱_拓樸關係空間與剖面視覺化_v5"
DPI = 450
FIGSIZE_IN = (5.70, 4.55)

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

# Five low-saturation, print-safe semantic colors.
OUTER_SURFACE_COLOR = "#6B9996"
INNER_SURFACE_COLOR = "#8B7FA2"
PLANE_SURFACE_COLOR = "#D4C39B"
ADJACENCY_COLOR = "#C66A1B"
ORTHOGONAL_COLOR = "#2F6F9D"
OUTLINE_COLOR = "#394149"
CUT_FILL_COLOR = "#EEF0F1"

VIEW_ELEV = 24
VIEW_AZIM = -45
CUT_START_DEG = 0.0
CUT_END_DEG = 270.0


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
            "svg.hashsalt": "stepped-cylinder-v5-figure-4-2b-260722",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    return times, kai


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, dict, list[dict], dict]:
    faces = pd.read_csv(FACES, encoding="utf-8-sig").sort_values("ClusterID").reset_index(drop=True)
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig").sort_values(["FromClusterID", "ToClusterID"]).reset_index(drop=True)
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    if validation.get("overall") != "PASS" or validation["five_layer_validation"].get("topology") != "PASS":
        raise ValueError("Stepped Cylinder topology validation is not PASS.")
    if len(faces) != 6 or sorted(faces["ClusterID"].astype(int).tolist()) != list(range(6)):
        raise ValueError("Expected exactly six verified semantic feature faces, IDs 0 through 5.")
    if len(topology) != 6 or set(topology["EdgeType"]) != {"EndCap"} or set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("Expected six verified EndCap rows.")

    face_lookup = faces.set_index("ClusterID")
    relations: list[dict] = []
    for row in topology.itertuples(index=False):
        first = int(row.FromClusterID)
        second = int(row.ToClusterID)
        first_face = face_lookup.loc[first]
        second_face = face_lookup.loc[second]
        first_is_cylinder = str(first_face.FeatureType).startswith("Cylinder_")
        second_is_cylinder = str(second_face.FeatureType).startswith("Cylinder_")
        if first_is_cylinder == second_is_cylinder:
            raise ValueError(f"EndCap pair {(first, second)} must connect one cylinder and one plane.")
        cylinder_id, plane_id = (first, second) if first_is_cylinder else (second, first)
        cylinder = face_lookup.loc[cylinder_id]
        plane = face_lookup.loc[plane_id]
        direction_dot = abs(float(row.DirectionDot))
        axis_plane_dot = abs(float(cylinder.AxisZ) * float(plane.NZ))
        if direction_dot < 0.95 or axis_plane_dot < 0.95:
            raise ValueError(f"Pair {(first, second)} does not satisfy the verified orthogonal-contact direction condition.")
        relations.append(
            {
                "pair": [first, second],
                "cylinder_id": cylinder_id,
                "plane_id": plane_id,
                "radius_mm": float(cylinder.Radius),
                "z_mm": float(plane.CenterZ),
                "min_distance_mm": float(row.MinDistance),
                "direction_dot": direction_dot,
                "axis_plane_normal_dot": axis_plane_dot,
                "base_adjacency": True,
                "geometric_orthogonal_contact": True,
                "stored_most_specific_edge_type": "EndCap",
            }
        )

    actual_pairs = {tuple(item["pair"]) for item in relations}
    expected_pairs = {(0, 2), (0, 4), (1, 2), (1, 3), (3, 5), (4, 5)}
    if actual_pairs != expected_pairs:
        raise ValueError(f"Unexpected topology pairs: {sorted(actual_pairs)}")

    geometry = {
        "inner_radius": float(face_lookup.loc[0].Radius),
        "lower_outer_radius": float(face_lookup.loc[1].Radius),
        "upper_outer_radius": float(face_lookup.loc[5].Radius),
        "bottom_z": float(face_lookup.loc[2].CenterZ),
        "shoulder_z": float(face_lookup.loc[3].CenterZ),
        "top_z": float(face_lookup.loc[4].CenterZ),
    }
    return faces, topology, validation, relations, geometry


def plot_cylinder(ax, radius: float, z0: float, z1: float, color: str, alpha: float) -> None:
    theta = np.deg2rad(np.linspace(CUT_START_DEG, CUT_END_DEG, 181))
    z_values = np.linspace(z0, z1, 60)
    theta_grid, z_grid = np.meshgrid(theta, z_values)
    x_grid = radius * np.cos(theta_grid)
    y_grid = radius * np.sin(theta_grid)
    ax.plot_surface(
        x_grid,
        y_grid,
        z_grid,
        color=color,
        alpha=alpha,
        linewidth=0,
        antialiased=True,
        shade=False,
    )


def plot_annulus(ax, inner_radius: float, outer_radius: float, z_value: float, color: str, alpha: float) -> None:
    theta = np.deg2rad(np.linspace(CUT_START_DEG, CUT_END_DEG, 181))
    radius = np.linspace(inner_radius, outer_radius, 25)
    theta_grid, radius_grid = np.meshgrid(theta, radius)
    x_grid = radius_grid * np.cos(theta_grid)
    y_grid = radius_grid * np.sin(theta_grid)
    z_grid = np.full_like(x_grid, z_value)
    ax.plot_surface(
        x_grid,
        y_grid,
        z_grid,
        color=color,
        alpha=alpha,
        linewidth=0,
        antialiased=True,
        shade=False,
    )


def plot_relation_ring(ax, radius: float, z_value: float) -> None:
    theta_solid = np.deg2rad(np.linspace(CUT_START_DEG, CUT_END_DEG, 361))
    theta_cut = np.deg2rad(np.linspace(CUT_END_DEG, 360.0, 121))
    for theta, linestyle, linewidth, alpha in (
        (theta_solid, "-", 2.2, 1.0),
        (theta_cut, (0, (3.0, 2.4)), 1.6, 0.88),
    ):
        x = radius * np.cos(theta)
        y = radius * np.sin(theta)
        z = np.full_like(theta, z_value)
        ax.plot(x, y, z, color="white", linewidth=linewidth + 1.8, linestyle=linestyle, alpha=0.96)
        ax.plot(x, y, z, color=ADJACENCY_COLOR, linewidth=linewidth, linestyle=linestyle, alpha=alpha)


def draw_right_angle(ax, x: float, z: float, sx: float, sz: float, scale: float = 2.6) -> None:
    origin_x = x + sx * 1.2
    origin_z = z + sz * 3.4
    ax.plot(
        [origin_x, origin_x + sx * scale],
        [origin_z, origin_z],
        color=ORTHOGONAL_COLOR,
        linewidth=1.6,
        solid_capstyle="round",
        zorder=8,
    )
    ax.plot(
        [origin_x, origin_x],
        [origin_z, origin_z + sz * scale],
        color=ORTHOGONAL_COLOR,
        linewidth=1.6,
        solid_capstyle="round",
        zorder=8,
    )


def draw_face_id(ax, x: float, z: float, face_id: int, times: fm.FontProperties) -> None:
    ax.text(
        x,
        z,
        str(face_id),
        ha="center",
        va="center",
        fontproperties=times,
        color=OUTLINE_COLOR,
        bbox={"boxstyle": "circle,pad=0.20", "facecolor": "white", "edgecolor": OUTLINE_COLOR, "linewidth": 0.8},
        zorder=10,
    )


def draw_legend(fig, kai: fm.FontProperties) -> None:
    ax = fig.add_axes([0.045, 0.015, 0.91, 0.075])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.plot([0.01, 0.09], [0.52, 0.52], color=ADJACENCY_COLOR, linewidth=2.2)
    ax.text(0.105, 0.52, "相鄰邊界 6", ha="left", va="center", fontproperties=kai, color=OUTLINE_COLOR)

    ax.plot([0.42, 0.47], [0.44, 0.44], color=ORTHOGONAL_COLOR, linewidth=1.7, solid_capstyle="round")
    ax.plot([0.445, 0.445], [0.44, 0.73], color=ORTHOGONAL_COLOR, linewidth=1.7, solid_capstyle="round")
    ax.text(0.49, 0.52, "正交接觸 6", ha="left", va="center", fontproperties=kai, color=OUTLINE_COLOR)

    ax.scatter([0.77], [0.52], s=92, facecolor="white", edgecolor=ADJACENCY_COLOR, linewidth=1.6)
    ax.scatter([0.77], [0.52], s=9, color=ADJACENCY_COLOR)
    ax.text(0.80, 0.52, "端面關係 6", ha="left", va="center", fontproperties=kai, color=OUTLINE_COLOR)


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
    faces, topology, validation, relations, geometry = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    r0 = geometry["inner_radius"]
    r1 = geometry["lower_outer_radius"]
    r5 = geometry["upper_outer_radius"]
    z0 = geometry["bottom_z"]
    z1 = geometry["shoulder_z"]
    z2 = geometry["top_z"]

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)

    # Left: fitted geometry cutaway with six verified shared boundaries.
    ax3d = fig.add_axes([0.005, 0.105, 0.635, 0.825], projection="3d")
    plot_cylinder(ax3d, r1, z0, z1, OUTER_SURFACE_COLOR, 0.42)
    plot_cylinder(ax3d, r5, z1, z2, OUTER_SURFACE_COLOR, 0.42)
    plot_cylinder(ax3d, r0, z0, z2, INNER_SURFACE_COLOR, 0.34)
    plot_annulus(ax3d, r0, r1, z0, PLANE_SURFACE_COLOR, 0.50)
    plot_annulus(ax3d, r5, r1, z1, PLANE_SURFACE_COLOR, 0.56)
    plot_annulus(ax3d, r0, r5, z2, PLANE_SURFACE_COLOR, 0.60)

    for relation in relations:
        plot_relation_ring(ax3d, relation["radius_mm"], relation["z_mm"])

    ax3d.view_init(elev=VIEW_ELEV, azim=VIEW_AZIM)
    ax3d.set_proj_type("ortho")
    ax3d.set_xlim(-r1 * 1.03, r1 * 1.03)
    ax3d.set_ylim(-r1 * 1.03, r1 * 1.03)
    ax3d.set_zlim(z0 - 2.0, z2 + 2.0)
    ax3d.set_box_aspect((2 * r1, 2 * r1, z2 - z0), zoom=1.11)
    ax3d.axis("off")
    fig.text(0.315, 0.947, "立體位置", ha="center", va="center", fontproperties=kai, color=OUTLINE_COLOR)

    # Right: axial half-section makes all six face contacts directly visible.
    ax2d = fig.add_axes([0.645, 0.115, 0.345, 0.80])
    profile = np.array([[r0, z0], [r1, z0], [r1, z1], [r5, z1], [r5, z2], [r0, z2]])
    ax2d.fill(profile[:, 0], profile[:, 1], color=CUT_FILL_COLOR, zorder=1)

    # Plane faces.
    ax2d.plot([r0, r1], [z0, z0], color=PLANE_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)
    ax2d.plot([r5, r1], [z1, z1], color=PLANE_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)
    ax2d.plot([r0, r5], [z2, z2], color=PLANE_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)
    # Cylinder faces.
    ax2d.plot([r0, r0], [z0, z2], color=INNER_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)
    ax2d.plot([r1, r1], [z0, z1], color=OUTER_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)
    ax2d.plot([r5, r5], [z1, z2], color=OUTER_SURFACE_COLOR, linewidth=3.2, solid_capstyle="round", zorder=4)

    corners = [
        (r0, z0, +1, +1),
        (r1, z0, -1, +1),
        (r1, z1, -1, -1),
        # The shoulder/upper-cylinder orthogonal marker is placed on the ID 3 side.
        (r5, z1, +1, +1),
        (r5, z2, -1, -1),
        (r0, z2, +1, -1),
    ]
    for x, z, sx, sz in corners:
        ax2d.scatter([x], [z], s=66, facecolor="white", edgecolor=ADJACENCY_COLOR, linewidth=1.6, zorder=7)
        ax2d.scatter([x], [z], s=8, color=ADJACENCY_COLOR, zorder=8)
        draw_right_angle(ax2d, x, z, sx, sz)

    # Six concise face IDs connect this panel directly to Figure 4.2(a).
    draw_face_id(ax2d, r0 - 5.8, (z0 + z2) / 2, 0, times)
    draw_face_id(ax2d, r1 + 5.5, (z0 + z1) / 2, 1, times)
    draw_face_id(ax2d, r5 + 5.5, (z1 + z2) / 2, 5, times)
    draw_face_id(ax2d, (r0 + r1) / 2, z0 - 8.8, 2, times)
    draw_face_id(ax2d, (r5 + r1) / 2 + 0.7, z1 + 9.0, 3, times)
    draw_face_id(ax2d, (r0 + r5) / 2, z2 + 8.8, 4, times)

    ax2d.set_xlim(r0 - 10.5, r1 + 10.5)
    ax2d.set_ylim(z0 - 13.0, z2 + 13.0)
    ax2d.set_aspect("equal", adjustable="box")
    ax2d.axis("off")
    fig.text(0.815, 0.947, "軸向剖面", ha="center", va="center", fontproperties=kai, color=OUTLINE_COLOR)

    draw_legend(fig, kai)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    fig.savefig(
        png,
        dpi=DPI,
        metadata={
            "Title": "Stepped Cylinder topology spatial and axial-section visualization",
            "Author": "Chapter 4 verified-figure pipeline",
            "Subject": "Six adjacent, geometrically orthogonal, EndCap face pairs",
            "Software": "generate_stepped_cylinder_v3_figure_4_2b_topology_spatial.py",
        },
    )
    fig.savefig(
        svg,
        format="svg",
        metadata={
            "Title": "Stepped Cylinder topology spatial and axial-section visualization",
            "Description": "Cutaway fitted geometry and axial half-section for six verified face pairs",
            "Creator": "generate_stepped_cylinder_v3_figure_4_2b_topology_spatial.py",
            "Date": "2026-07-22",
            "Keywords": ["Stepped Cylinder", "adjacency", "orthogonal contact", "EndCap", "semantic topology"],
        },
    )
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))
    occupancy = content_occupancy(png)
    if occupancy["width_fraction"] < 0.83 or occupancy["height_fraction"] < 0.82:
        raise ValueError(f"Excessive white space: {occupancy}")
    left, top, right, bottom = occupancy["bbox"]
    if left < 18 or top < 18 or right > occupancy["pixel_width"] - 19 or bottom > occupancy["pixel_height"] - 19:
        raise ValueError(f"Figure content reaches crop safety margin: {occupancy}")

    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.2(b) 階梯狀圓柱拓樸關係空間與剖面視覺化",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "design_review": {
            "selected_type": "fitted-geometry cutaway plus axial half-section",
            "reading_logic": "left panel locates six shared circular boundaries in 3D; right panel exposes all six face contacts without occlusion",
            "rejected_alternatives": {
                "point_cloud_plus_rings": "geometrically correct but does not show which two faces meet or why the contact is orthogonal",
                "node_link_graph": "shows database connectivity but disconnects the relations from their physical boundary locations",
            },
            "reviewer_improvements": [
                "replace point-cloud clutter with verified fitted surfaces",
                "add an axial half-section so all six contacts are visible at once",
                "encode base adjacency, geometric orthogonality, and stored EndCap separately",
                "move all face-ID circles away from boundary lines and place the shoulder orthogonal marker beside ID 3",
            ],
        },
        "method_alignment": {
            "chapter_3_sections": ["3.6 語義拓樸：語義特徵面建構", "3.7 語義拓樸：拓樸關係建構"],
            "base_adjacency_encoding": "orange shared boundary ring in 3D and shared corner in section",
            "geometric_orthogonal_contact_encoding": "blue right-angle marker at every section contact",
            "stored_edge_type_encoding": "orange circle-with-center-dot at every section contact",
            "edge_type_rule": "one most-specific EndCap database row per unordered pair; no duplicate Adjacency or OrthogonalAdjacency row",
            "does_not_encode": ["candidate primitive", "BooleanType", "CSG"],
            "validation_overall": validation["overall"],
            "topology_validation": validation["five_layer_validation"]["topology"],
        },
        "data": {
            "semantic_feature_faces": 6,
            "base_adjacent_pairs": 6,
            "geometric_orthogonal_contacts": 6,
            "stored_endcap_rows": 6,
            "generic_adjacency_rows": 0,
            "orthogonal_adjacency_rows": 0,
            "database_pairs": [item["pair"] for item in relations],
            "relation_mapping": relations,
            "fitted_geometry_mm": geometry,
        },
        "explainability": {
            "figure_claim": "六條橙色共同邊界對應六組相鄰面對；軸向剖面的六個藍色直角記號表示幾何正交接觸，六個橙色圓圈中央加點表示資料庫均以 EndCap 儲存。",
            "caption_draft": "本圖以驗證後曲面參數建立階梯狀圓柱立體剖切視圖與軸向剖面。左側橙色圓環顯示六組相鄰面的共同邊界；右側藍色直角與橙色端面符號分別表示幾何正交接觸及資料庫所記錄的端面關係。",
            "body_text_requirement": "正文須區分相鄰面對、幾何正交接觸與資料庫最具體 EdgeType，並說明面 ID 0 至 5 與圖 4.2(a) 相同。",
            "evidence_map": [
                {"figure_element": "three fitted cylindrical surfaces", "evidence": "FaceSummary IDs 0, 1, 5", "evidence_type": "directly stated"},
                {"figure_element": "three horizontal annular faces", "evidence": "FaceSummary IDs 2, 3, 4", "evidence_type": "directly stated"},
                {"figure_element": "six shared circular boundaries", "evidence": "six TopologyEdges unordered pairs", "evidence_type": "directly stated"},
                {"figure_element": "six right-angle markers", "evidence": "DirectionDot and axis-plane-normal dot are at least 0.95", "evidence_type": "directly calculated from verified data"},
                {"figure_element": "six circle-with-center-dot markers", "evidence": "all six stored EdgeType values are EndCap", "evidence_type": "directly stated"},
            ],
        },
        "format": {
            "figure_size_in": list(FIGSIZE_IN),
            "figure_width_cm": round(FIGSIZE_IN[0] * 2.54, 3),
            "dpi": DPI,
            "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font": "DFKai-SB 12 pt",
            "title_inside_figure": False,
            "panel_labels": ["立體位置", "軸向剖面"],
            "view_elevation_deg": VIEW_ELEV,
            "view_azimuth_deg": VIEW_AZIM,
            "cutaway_retained_angle_deg": CUT_END_DEG - CUT_START_DEG,
            "occupancy": occupancy,
        },
        "source_sha256": {
            FACES.name: sha256(FACES),
            TOPOLOGY.name: sha256(TOPOLOGY),
            VALIDATION.name: sha256(VALIDATION),
        },
        "outputs": {
            png.name: sha256(png),
            svg.name: sha256(svg),
            str(gray.relative_to(output_dir)): sha256(gray),
        },
        "release_boundary": "Only redesigned Figure 4.2(b) is generated. Figure 4.3 remains blocked until user confirmation.",
    }
    qa_path = output_dir / f"{FIGURE_STEM}_QA.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg), "qa": str(qa_path), "summary": qa}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate only redesigned Stepped Cylinder Figure 4.2(b).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
