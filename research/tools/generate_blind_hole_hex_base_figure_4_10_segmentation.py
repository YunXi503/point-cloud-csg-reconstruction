"""圖 4.10 — 盲孔六角座驗證後幾何特徵分割結果。

與圖 4.1（階梯狀圓柱）／圖 4.4（L型板）／圖 4.7（模型A）同一圖族：以 ClusterID
著色的三維點雲散布圖，含座標軸、格線與分段色標。字型、配色對比最佳化與座標樣式
均沿用 generate_model_a_v3_figure_4_7_segmentation 之函式，以維持全章一致。

僅讀取已通過五層驗收的 v3 輸出；可重現。
"""

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

from generate_model_a_v3_figure_4_7_segmentation import (
    PALETTE_VIVID,
    assign_contrast_colors,
    configure_fonts,
    content_occupancy,
    delta_e76,
    face_gap_matrix,
)

ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260725" / "Blind_Hole_Hex_Base_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Blind_Hole_Hex_Base_260725"

RESULT = DATA_DIR / "Result_Blind_Hole_Hex_Base_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_Blind_Hole_Hex_Base_chapter3_verified.csv"
TOPOLOGY = DATA_DIR / "TopologyEdges_Blind_Hole_Hex_Base_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationAgainstIndependentTruth_Blind_Hole_Hex_Base.json"

FIGURE_STEM = "圖4.10_盲孔六角座_驗證後幾何特徵分割結果"
SALT = "blind-hole-hex-base-figure-4-10-260725"
DPI = 450
FIGSIZE_IN = (5.70, 4.35)
VIEW_ELEV = 45
VIEW_AZIM = 135
POINT_MARKER = "."
POINT_SIZE_PT2 = 12.0
RESIDUAL_COLOR = "#AEB4BA"

EXPECTED_FACES = 12
EXPECTED_TOPOLOGY = 22


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_and_validate():
    points = pd.read_csv(RESULT, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    required = {"X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"}
    if not required.issubset(points.columns):
        raise ValueError(f"Result is missing columns: {sorted(required - set(points.columns))}")
    if validation.get("overall") != "PASS":
        raise ValueError("盲孔六角座驗收結果不是 PASS。")
    if validation.get("method_source_separation", {}).get("status") != "PASS":
        raise ValueError("推論來源獨立性不是 PASS。")
    if any(value != "PASS" for value in validation["five_layer_validation"].values()):
        raise ValueError("五層驗收中至少一層不是 PASS。")

    counts = validation["counts"]
    if len(points) != counts["total_points"] or len(points) != 10000:
        raise ValueError("點數不是 10000。")
    accepted = sorted(int(v) for v in points.loc[points["ClusterID"] >= 0, "ClusterID"].unique())
    if accepted != list(range(EXPECTED_FACES)):
        raise ValueError(f"未預期的 ClusterID 集合：{accepted}")
    if int((points["ClusterID"] == -1).sum()) != counts["residual_points"]:
        raise ValueError("殘留點數與驗收摘要不一致。")
    if len(faces) != counts["accepted_faces"] or len(faces) != EXPECTED_FACES:
        raise ValueError(f"語義特徵面數不是 {EXPECTED_FACES}。")
    if len(topology) != counts["topology_edges"] or len(topology) != EXPECTED_TOPOLOGY:
        raise ValueError(f"拓樸關係數不是 {EXPECTED_TOPOLOGY}。")
    if set(topology["EdgeType"]) != {"Adjacency", "OrthogonalAdjacency", "EndCap"}:
        raise ValueError("盲孔六角座應同時具備三種拓樸關係型別。")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("至少一條拓樸關係未通過規則。")

    observed = points.loc[points["ClusterID"] >= 0].groupby("ClusterID").size().sort_index()
    declared = faces.set_index("ClusterID")["PointCount"].astype(int).sort_index()
    if not observed.equals(declared):
        raise ValueError("Result 點數與 FaceSummary 不一致。")
    return points, faces, topology, validation, accepted


def set_axis_style(ax, points, times):
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
        zoom=1.03,
    )
    ax.set_xlabel("X (mm)", fontproperties=times, labelpad=5)
    ax.set_ylabel("Y (mm)", fontproperties=times, labelpad=5)
    ax.set_zlabel("Z (mm)", fontproperties=times, labelpad=4)
    for name in ("x", "y", "z"):
        ax.tick_params(axis=name, which="major", labelsize=12, pad=1)
    ax.grid(True, color="#C8CDD2", linewidth=0.50, alpha=0.75)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.975, 0.975, 0.975, 1.0))
        axis.pane.set_edgecolor("#AEB5BC")
        for label in axis.get_ticklabels():
            label.set_fontproperties(times)


def generate(
    output_dir: Path,
    elev: int | None = None,
    azim: int | None = None,
    stem: str | None = None,
    cull_back_faces: bool = True,
) -> dict:
    global VIEW_ELEV, VIEW_AZIM, FIGURE_STEM
    if elev is not None:
        VIEW_ELEV = elev
    if azim is not None:
        VIEW_AZIM = azim
    if stem is not None:
        FIGURE_STEM = stem
    times = configure_fonts(SALT)
    points, faces, topology, validation, ids = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    id_to_idx = {cid: index for index, cid in enumerate(ids)}
    contact_pairs = [
        (id_to_idx[int(row.FromClusterID)], id_to_idx[int(row.ToClusterID)])
        for row in topology.itertuples(index=False)
    ]
    orthogonal_pairs = [
        (id_to_idx[int(row.FromClusterID)], id_to_idx[int(row.ToClusterID)])
        for row in topology.itertuples(index=False)
        if str(row.EdgeType) == "OrthogonalAdjacency"
    ]
    gap = face_gap_matrix(points, ids, VIEW_ELEV, VIEW_AZIM)
    colors, metrics = assign_contrast_colors(
        gap, len(ids), contact_pairs, palette=PALETTE_VIVID, orthogonal_edges=orthogonal_pairs
    )
    # 手動拉開 ClusterID 9 與 11 的顏色
    colors[id_to_idx[9]] = "#1236A6"  # 深藍色
    colors[id_to_idx[4]] = "#7B2CBF"  # 4 改成紫色
    colors[id_to_idx[11]] = "#43B649"  # 11 改成綠色（請換成你原本 4 的綠色碼）
    all_pairs = [(i, j) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    contact_delta_e = [delta_e76(colors[i], colors[j]) for i, j in contact_pairs]

    cmap = ListedColormap(colors, name="blind_hole_hex_base_clusters_v1")
    norm = BoundaryNorm(np.arange(-0.5, len(ids) + 0.5, 1.0), cmap.N)

    accepted = points[points["ClusterID"] >= 0].copy()
    accepted["ColorIdx"] = accepted["ClusterID"].astype(int).map(id_to_idx)
    residual = points[points["ClusterID"] == -1]

    # 背面剔除：本範例為實心六角塊，若將全部取樣點一併繪出，背面點會穿透前景而
    # 使外形與孔洞難以辨識。此處僅在「顯示」階段保留法向量朝向視點的點；不修改
    # 任何資料，各面之點數、色彩與 ClusterID 歸屬均與驗證輸出一致。
    if cull_back_faces:
        elevation = np.radians(VIEW_ELEV)
        azimuth = np.radians(VIEW_AZIM)
        view = np.asarray(
            [
                np.cos(elevation) * np.cos(azimuth),
                np.cos(elevation) * np.sin(azimuth),
                np.sin(elevation),
            ]
        )
        facing = accepted[["NX", "NY", "NZ"]].to_numpy(float) @ view > 0.0
        accepted = accepted[facing]
        if len(residual):
            residual = residual[residual[["NX", "NY", "NZ"]].to_numpy(float) @ view > 0.0]

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.005, 0.06, 0.80, 0.92], projection="3d")
    if len(residual):
        ax.scatter(
            residual["X"], residual["Y"], residual["Z"], c=RESIDUAL_COLOR,
            s=POINT_SIZE_PT2 * 0.8, marker=POINT_MARKER, linewidths=0, alpha=0.9,
            depthshade=False,
        )
    ax.scatter(
        accepted["X"], accepted["Y"], accepted["Z"], c=accepted["ColorIdx"], cmap=cmap,
        norm=norm, s=POINT_SIZE_PT2, marker=POINT_MARKER, linewidths=0, alpha=1.0,
        depthshade=False, rasterized=False,
    )
    set_axis_style(ax, points, times)

    cax = fig.add_axes([0.855, 0.185, 0.026, 0.63])
    cbar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=cmap), cax=cax,
        boundaries=np.arange(-0.5, len(ids) + 0.5, 1.0),
        ticks=np.arange(len(ids)), spacing="uniform",
    )
    cbar.ax.set_yticklabels([str(value) for value in ids])
    cbar.set_label("ClusterID", fontproperties=times, rotation=90, labelpad=7)
    cbar.ax.tick_params(labelsize=11, width=0.8, length=3)
    for label in cbar.ax.get_yticklabels():
        label.set_fontproperties(times)
    cbar.outline.set_linewidth(0.8)

    png = output_dir / f"{FIGURE_STEM}.png"
    svg = output_dir / f"{FIGURE_STEM}.svg"
    metadata = {
        "Title": "Blind-Hole Hex Base verified geometric feature segmentation",
        "Author": "Chapter 4 verified-figure pipeline",
        "Subject": "ClusterID from method-only v3 output",
        "Software": Path(__file__).name,
    }
    fig.savefig(png, dpi=DPI, metadata=metadata)
    fig.savefig(
        svg, format="svg",
        metadata={
            "Title": metadata["Title"],
            "Description": metadata["Subject"],
            "Creator": Path(__file__).name,
            "Date": "2026-07-25",
            "Keywords": ["Blind-Hole Hex Base", "ClusterID", "geometric feature segmentation"],
        },
    )
    plt.close(fig)

    gray = qa_dir / f"{FIGURE_STEM}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    report = {
        "figure": "圖 4.10 盲孔六角座驗證後幾何特徵分割結果",
        "data_sources": {
            path.name: sha256(path) for path in (RESULT, FACES, TOPOLOGY, VALIDATION)
        },
        "counts": {
            "points": int(len(points)),
            "accepted_faces": int(len(faces)),
            "residual_points": int(len(residual)),
            "topology_edges": int(len(topology)),
        },
        "cluster_ids": ids,
        "colors": {str(cid): colors[index] for index, cid in enumerate(ids)},
        "color_contrast": {
            "min_contact_delta_e": float(min(contact_delta_e)),
            "min_all_pairs_delta_e": float(
                min(delta_e76(colors[i], colors[j]) for i, j in all_pairs)
            ),
            "mean_all_pairs_delta_e": float(
                np.mean([delta_e76(colors[i], colors[j]) for i, j in all_pairs])
            ),
        },
        "view": {
            "elev": VIEW_ELEV, "azim": VIEW_AZIM, "projection": "ortho",
            "back_face_culling": bool(cull_back_faces),
            "drawn_points": int(len(accepted) + len(residual)),
        },
        "render": {
            "dpi": DPI,
            "figsize_in": list(FIGSIZE_IN),
            "english_numbers_font": "Times New Roman 12 pt",
            "title_inside_figure": False,
        },
        "occupancy": content_occupancy(png),
        "outputs": {png.name: sha256(png), svg.name: sha256(svg), gray.name: sha256(gray)},
        "validation_overall": validation["overall"],
    }
    (qa_dir / f"{FIGURE_STEM}_QA.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Figure 4.10 for Blind-Hole Hex Base.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--elev", type=int, default=None)
    parser.add_argument("--azim", type=int, default=None)
    parser.add_argument("--stem", type=str, default=None)
    parser.add_argument("--no-cull", action="store_true")
    arguments = parser.parse_args()
    report = generate(
        arguments.output_dir.resolve(), arguments.elev, arguments.azim, arguments.stem,
        not arguments.no_cull,
    )
    print(json.dumps(report["color_contrast"], ensure_ascii=False))
    print(report["outputs"])


if __name__ == "__main__":
    main()
