"""Figure 4.7 - Model A verified geometric feature segmentation.

Same figure family as SC 4.1 / L 4.4: a 3D scatter of the verified point cloud
coloured by ClusterID, with axes/grid/colorbar and full QA. Model A specifics:
  * ClusterID is NON-CONTIGUOUS: {0..10, 13, 14} = 13 accepted faces, with 0
    residual points on the 260724 clean-mesh data (the residual-point legend is
    drawn only when residual points exist).
  * Colours are chosen to maximise CIE-1976 Delta-E between topologically related
    faces (26 relations, three types). Colour encodes ClusterID ONLY; the figure
    does not visualise topology, semantics or CSG.
Deterministic / reproducible. Reads only verified v3 outputs.
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
from matplotlib.lines import Line2D
from PIL import Image, ImageOps

ROOT = Path(r"C:\Users\Admin\Desktop\云析論文")
DATA_DIR = ROOT / "碩士論文" / "第四章驗證結果_260724" / "Model_A_chapter3_verified_v3"
DEFAULT_OUTPUT_DIR = ROOT / "碩士論文" / "figures" / "第四章_Model_A_v3逐張審查_260724"

RESULT = DATA_DIR / "Result_Model_A_chapter3_verified.csv"
FACES = DATA_DIR / "FaceSummary_Model_A_chapter3_verified.csv"
TOPOLOGY = DATA_DIR / "TopologyEdges_Model_A_chapter3_verified.csv"
VALIDATION = DATA_DIR / "ValidationAgainstIndependentTruth_Model_A.json"

FIGURE_STEM = "圖4.7_ModelA_驗證後幾何特徵分割結果_v2"
DPI = 450
FIGSIZE_IN = (5.70, 4.35)
VIEW_ELEV = 20
VIEW_AZIM = 140  # matches Model A 圖4.9 view "E" and the user's reference point cloud
POINT_MARKER = "."
POINT_SIZE_PT2 = 5.0
POINT_ALPHA = 1.0
RESIDUAL_COLOR = "#AEB4BA"
# Colour contrast is optimised over ALL face pairs, weighted by spatial proximity:
# the closer two faces are (smaller inter-face gap in mm), the higher the colour
# contrast demanded. GAP_ALPHA converts mm of gap into Delta-E "credit" so that
# near faces bind the objective. Floors are hard minimums verified after solving.
GAP_ALPHA = 1.1
MIN_CONTACT_DELTA_E_FLOOR = 50.0   # topology-contact face pairs (gap < 2 mm)
MIN_ORTHOGONAL_DELTA_E_FLOOR = 60.0  # orthogonally adjacent faces: pushed further
# apart than the generic 50 contact floor so plates meeting at right angles clearly
# stagger in colour. The optimiser additionally rewards HUE separation for these
# pairs (see assign_contrast_colors), which avoids two same-hue neighbours (e.g.
# teal vs green) that read as similar even at high ΔE. This gate is the sanity
# floor; the objective pushes the actual minimum as high as each palette allows.
MIN_ALLPAIRS_DELTA_E_FLOOR = 25.0  # every face pair (safety net; 13 categorical
# colours cannot all exceed ~28-30, but far pairs sit in different image regions)

TIMES_PATH = Path(r"C:\Windows\Fonts\times.ttf")
KAI_PATH = Path(r"C:\Windows\Fonts\kaiu.ttf")

# Two candidate pools; the optimiser picks 13 with best proximity-weighted
# contrast. Both are white-background safe (near-white tints removed) and gamut-
# filling so the ΔE floors can be met. "vivid" is the bright neon rainbow;
# "jewel" is a deeper, more subdued jewel/earth character requested as an
# alternative — a larger pool (20) gives the optimiser room to still clear the
# floors despite the lower saturation.
PALETTE_VIVID = [
    "#E6194B", "#3CB44B", "#4363D8", "#F58231", "#911EB4", "#42D4F4",
    "#F032E6", "#BFEF45", "#469990", "#9A6324", "#800000", "#808000",
    "#000075", "#A9A9A9", "#111111", "#E8A200",
]
# "配色B": the "vivid" pool with every hue rotated 180° (complementary) and
# lightness scaled to 0.90. Rotating a fixed angle preserves the pairwise Lab
# distances that let the pool clear both ΔE floors, while giving a distinctly
# different look (reds↔cyans, greens↔magentas, blues↔oranges) that is slightly
# deeper than the neon original. Derived once from PALETTE_VIVID and frozen here
# as static hex for reproducibility.
PALETTE_JEWEL = [
    "#17CFA2", "#A23694", "#D3AF2C", "#1598F4", "#3BA21B", "#F24A25",
    "#17EE22", "#6029ED", "#8A3F47", "#20528B", "#007373", "#000073",
    "#696900", "#989898", "#0F0F0F", "#003FD1",
]

# name -> (candidate pool, figure stem, svg hash salt)
PALETTES = {
    "vivid": (PALETTE_VIVID, "圖4.7_ModelA_驗證後幾何特徵分割結果_v2", "model-a-v3-figure-4-7-260723"),
    "jewel": (PALETTE_JEWEL, "圖4.7_ModelA_驗證後幾何特徵分割結果_v2配色B", "model-a-figure-4-7-260724-jewel"),
}
PALETTE_CANDIDATES = PALETTE_VIVID  # default binding (overridden per --palette)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_fonts(salt: str = "model-a-v3-figure-4-7-260723") -> fm.FontProperties:
    if not TIMES_PATH.exists() or not KAI_PATH.exists():
        raise FileNotFoundError("Times New Roman or DFKai-SB font file is missing.")
    fm.fontManager.addfont(str(TIMES_PATH))
    fm.fontManager.addfont(str(KAI_PATH))
    times = fm.FontProperties(family="Times New Roman", size=12)
    fm.FontProperties(family="DFKai-SB", size=12)
    plt.rcParams.update({
        "font.family": times.get_name(), "font.size": 12, "axes.labelsize": 12,
        "xtick.labelsize": 12, "ytick.labelsize": 12, "axes.unicode_minus": False,
        "svg.fonttype": "none", "svg.hashsalt": salt,
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })
    return times


def hex_to_lab(color: str) -> np.ndarray:
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=float) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = np.array([
        0.4124564 * linear[0] + 0.3575761 * linear[1] + 0.1804375 * linear[2],
        0.2126729 * linear[0] + 0.7151522 * linear[1] + 0.0721750 * linear[2],
        0.0193339 * linear[0] + 0.1191920 * linear[1] + 0.9503041 * linear[2],
    ])
    ratio = xyz / np.array([0.95047, 1.0, 1.08883])
    d = 6 / 29
    t = np.where(ratio > d ** 3, np.cbrt(ratio), ratio / (3 * d ** 2) + 4 / 29)
    return np.array([116 * t[1] - 16, 500 * (t[0] - t[1]), 200 * (t[1] - t[2])])


def delta_e76(a: str, b: str) -> float:
    return float(np.linalg.norm(hex_to_lab(a) - hex_to_lab(b)))


def _project(xyz, elev, azim):
    """Orthographic screen coords (u, v) for the given matplotlib view."""
    az, el = np.radians(azim), np.radians(elev)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    u = -np.sin(az) * x + np.cos(az) * y
    v = -np.cos(az) * np.sin(el) * x - np.sin(az) * np.sin(el) * y + np.cos(el) * z
    return np.column_stack([u, v])


def _min_gap(a, b):
    return float(np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1).min()))


def face_gap_matrix(points, ids, elev, azim, max_pts=160, seed=7):
    """Face-pair proximity = min(3D gap, 2D projected gap) in mm; symmetric.

    Using the projected gap as well means faces that are far apart in 3D but
    OVERLAP in the rendered view (e.g. the two ring end faces 1 & 2, or the web
    front/rear faces) are also treated as near, so they receive high contrast."""
    rng = np.random.default_rng(seed)
    sub3d, sub2d = {}, {}
    for cid in ids:
        arr = points.loc[points["ClusterID"] == cid, ["X", "Y", "Z"]].to_numpy()
        if len(arr) > max_pts:
            arr = arr[rng.choice(len(arr), max_pts, replace=False)]
        sub3d[cid] = arr
        sub2d[cid] = _project(arr, elev, azim)
    n = len(ids)
    gap = np.zeros((n, n))
    for a in range(n):
        for b in range(a + 1, n):
            g = min(_min_gap(sub3d[ids[a]], sub3d[ids[b]]),
                    _min_gap(sub2d[ids[a]], sub2d[ids[b]]))
            gap[a, b] = gap[b, a] = g
    return gap


def assign_contrast_colors(gap, n_faces, contact_edges, seed=42, iters=150000, palette=None,
                           orthogonal_edges=None):
    """Assign n_faces distinct palette colours; contrast is optimised over ALL
    face pairs, weighted by spatial proximity (closer faces demand more contrast).

    Objective (maximise, lexicographic):
      1. min over ORTHOGONAL pairs of (DeltaE + hue term) -> orthogonally adjacent
         faces (plates meeting at right angles) are pushed apart in BOTH lightness
         and hue, so same-hue neighbours (e.g. teal vs green) are avoided
      2. min over pairs of (DeltaE + GAP_ALPHA * gap)  -> colour, proximity-weighted
      3. min over CONTACT pairs of |Delta L*|          -> greyscale contrast at the
         real face boundaries, so those edges survive black-and-white printing
      4. min over pairs of DeltaE                       -> global colour distinctness
      5. mean DeltaE                                    -> overall spread
    Returns (colors, (min_ortho, min_weighted, min_contact_dL, min_raw_de, mean_de))."""
    palette = PALETTE_CANDIDATES if palette is None else palette
    labs = np.vstack([hex_to_lab(c) for c in palette])
    lightness = labs[:, 0]
    # hue angle (deg) in the a*-b* plane; used to reward different hue families for
    # orthogonally adjacent faces (high DeltaE via lightness alone is not enough).
    hue = np.degrees(np.arctan2(labs[:, 2], labs[:, 1]))
    dist = np.linalg.norm(labs[:, None, :] - labs[None, :, :], axis=2)
    m = len(palette)
    pairs = [(i, j) for i in range(n_faces) for j in range(i + 1, n_faces)]
    pi = np.array([i for i, j in pairs])
    pj = np.array([j for i, j in pairs])
    gaps = np.array([gap[i, j] for i, j in pairs])
    ci = np.array([a for a, b in contact_edges]) if contact_edges else np.array([], dtype=int)
    cj = np.array([b for a, b in contact_edges]) if contact_edges else np.array([], dtype=int)
    oi = np.array([a for a, b in orthogonal_edges]) if orthogonal_edges else np.array([], dtype=int)
    oj = np.array([b for a, b in orthogonal_edges]) if orthogonal_edges else np.array([], dtype=int)

    def score(a):
        aa = np.asarray(a)
        de = dist[aa[pi], aa[pj]]
        cdl = np.abs(lightness[aa[ci]] - lightness[aa[cj]]) if len(ci) else np.array([np.inf])
        if len(oi):
            hue_diff = np.abs(hue[aa[oi]] - hue[aa[oj]])
            hue_diff = np.minimum(hue_diff, 360.0 - hue_diff)  # circular, 0..180
            ortho = dist[aa[oi], aa[oj]] + 0.5 * hue_diff      # reward ΔE and hue split
            ortho_min = float(ortho.min())
        else:
            ortho_min = np.inf
        return (ortho_min, float((de + GAP_ALPHA * gaps).min()), float(cdl.min()),
                float(de.min()), float(de.mean()))

    rng = np.random.default_rng(seed)
    best = list(rng.permutation(m)[:n_faces])
    best_score = score(best)
    for _ in range(iters):
        cand = list(rng.permutation(m)[:n_faces])
        s = score(cand)
        if s > best_score:
            best, best_score = cand, s

    improved = True
    while improved:
        improved = False
        unused = [c for c in range(m) if c not in set(best)]
        for i in range(n_faces):
            for j in range(i + 1, n_faces):
                cand = best.copy(); cand[i], cand[j] = cand[j], cand[i]
                s = score(cand)
                if s > best_score:
                    best, best_score, improved = cand, s, True
            for u in unused:
                cand = best.copy(); cand[i] = u
                s = score(cand)
                if s > best_score:
                    best, best_score, improved = cand, s, True
    return [palette[i] for i in best], best_score


def load_and_validate():
    points = pd.read_csv(RESULT, encoding="utf-8-sig")
    faces = pd.read_csv(FACES, encoding="utf-8-sig")
    topology = pd.read_csv(TOPOLOGY, encoding="utf-8-sig")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))

    required = {"X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"}
    if not required.issubset(points.columns):
        raise ValueError(f"Result is missing columns: {sorted(required - set(points.columns))}")
    if validation.get("overall") != "PASS":
        raise ValueError("Model A v3 validation is not PASS.")
    if validation.get("method_source_separation", {}).get("status") != "PASS":
        raise ValueError("Method source separation is not PASS.")
    if any(v != "PASS" for v in validation["five_layer_validation"].values()):
        raise ValueError("At least one validation layer is not PASS.")

    counts = validation["counts"]
    if len(points) != counts["total_points"] or len(points) != 10000:
        raise ValueError("Point count is not 10000.")
    accepted_ids = sorted(int(v) for v in points.loc[points["ClusterID"] >= 0, "ClusterID"].unique())
    expected_ids = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14]
    if accepted_ids != expected_ids:
        raise ValueError(f"Unexpected accepted ClusterID set: {accepted_ids}")
    if int((points["ClusterID"] == -1).sum()) != counts["residual_points"]:
        raise ValueError("Residual-point count does not match validation summary.")
    if len(faces) != counts["accepted_faces"] or len(faces) != 13:
        raise ValueError("Face count is not 13.")
    if len(topology) != counts["topology_edges"] or len(topology) != 26:
        raise ValueError("Topology relation count is not 26.")
    if set(topology["EdgeType"]) != {"Adjacency", "OrthogonalAdjacency", "EndCap"}:
        raise ValueError("Unexpected topology relation types for Model A.")
    if set(topology["RuleStatus"]) != {"PASS"}:
        raise ValueError("At least one topology relation did not pass its rule.")
    pairs = [tuple(sorted((int(r.FromClusterID), int(r.ToClusterID)))) for r in topology.itertuples(index=False)]
    if len(set(pairs)) != 26 or any(a == b for a, b in pairs):
        raise ValueError("Topology relations must be 26 unique unordered face pairs.")

    observed = points.loc[points["ClusterID"] >= 0].groupby("ClusterID").size().sort_index()
    declared = faces.set_index("ClusterID")["PointCount"].astype(int).sort_index()
    if not observed.equals(declared):
        raise ValueError("Result point counts do not match FaceSummary.")
    return points, faces, topology, validation, expected_ids


def set_axis_style(ax, points, times):
    ax.view_init(elev=VIEW_ELEV, azim=VIEW_AZIM)
    ax.set_proj_type("ortho")
    ax.set_xlim(float(points["X"].min()), float(points["X"].max()))
    ax.set_ylim(float(points["Y"].min()), float(points["Y"].max()))
    ax.set_zlim(float(points["Z"].min()), float(points["Z"].max()))
    ax.set_box_aspect((
        float(points["X"].max() - points["X"].min()),
        float(points["Y"].max() - points["Y"].min()),
        float(points["Z"].max() - points["Z"].min()),
    ), zoom=1.03)
    ax.set_xlabel("X (mm)", fontproperties=times, labelpad=5)
    ax.set_ylabel("Y (mm)", fontproperties=times, labelpad=5)
    ax.set_zlabel("Z (mm)", fontproperties=times, labelpad=4)
    for a in ("x", "y", "z"):
        ax.tick_params(axis=a, which="major", labelsize=12, pad=1)
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
        left, right, top, bottom = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        return {"pixel_width": image.width, "pixel_height": image.height,
                "bbox": [left, top, right, bottom],
                "width_fraction": (right - left + 1) / image.width,
                "height_fraction": (bottom - top + 1) / image.height,
                "dpi": list(image.info.get("dpi", ()))}


def generate(output_dir: Path, palette_name: str = "vivid",
             elev: int | None = None, azim: int | None = None,
             fixed_colors: dict | None = None) -> dict:
    global VIEW_ELEV, VIEW_AZIM
    if elev is not None:
        VIEW_ELEV = elev
    if azim is not None:
        VIEW_AZIM = azim
    palette, figure_stem, salt = PALETTES[palette_name]
    times = configure_fonts(salt)
    points, faces, topology, validation, ids = load_and_validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "qa"; qa_dir.mkdir(parents=True, exist_ok=True)

    id_to_idx = {cid: i for i, cid in enumerate(ids)}
    contact_pairs = [(id_to_idx[int(r.FromClusterID)], id_to_idx[int(r.ToClusterID)])
                     for r in topology.itertuples(index=False)]
    orthogonal_pairs = [(id_to_idx[int(r.FromClusterID)], id_to_idx[int(r.ToClusterID)])
                        for r in topology.itertuples(index=False)
                        if str(r.EdgeType) == "OrthogonalAdjacency"]
    contact_set = {tuple(sorted(p)) for p in contact_pairs}
    gap = face_gap_matrix(points, ids, VIEW_ELEV, VIEW_AZIM)
    all_pairs = [(i, j) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    if fixed_colors is not None:
        # Pin colours to a previously-confirmed assignment: change ONLY the view,
        # keep the approved cluster colours. ΔE floors are angle-independent, so a
        # confirmed assignment that already cleared them still clears them here.
        missing = [cid for cid in ids if str(cid) not in fixed_colors]
        if missing:
            raise ValueError(f"--pin-colors mapping is missing ClusterIDs: {missing}")
        colors = [fixed_colors[str(cid)] for cid in ids]
        min_contact_dL = min(abs(hex_to_lab(colors[i])[0] - hex_to_lab(colors[j])[0])
                             for i, j in contact_pairs)
        mean_de = float(np.mean([delta_e76(colors[i], colors[j]) for i, j in all_pairs]))
    else:
        colors, (min_ortho, min_weighted, min_contact_dL, min_allpairs_de, mean_de) = \
            assign_contrast_colors(gap, len(ids), contact_pairs, palette=palette,
                                   orthogonal_edges=orthogonal_pairs)

    def de(i, j):
        return delta_e76(colors[i], colors[j])
    contact_de = [de(i, j) for i, j in contact_pairs]
    ortho_de = [de(i, j) for i, j in orthogonal_pairs]
    allpairs_de = [de(i, j) for i, j in all_pairs]
    if min(contact_de) < MIN_CONTACT_DELTA_E_FLOOR:
        raise ValueError(f"Contact-face contrast {min(contact_de):.1f} below floor {MIN_CONTACT_DELTA_E_FLOOR}.")
    if min(allpairs_de) < MIN_ALLPAIRS_DELTA_E_FLOOR:
        raise ValueError(f"All-pairs contrast {min(allpairs_de):.1f} below floor {MIN_ALLPAIRS_DELTA_E_FLOOR}.")
    if ortho_de and min(ortho_de) < MIN_ORTHOGONAL_DELTA_E_FLOOR:
        raise ValueError(f"Orthogonal-face contrast {min(ortho_de):.1f} below floor {MIN_ORTHOGONAL_DELTA_E_FLOOR}.")

    adjacent_contrast = [
        {"from_cluster_id": int(r.FromClusterID), "to_cluster_id": int(r.ToClusterID),
         "edge_type": str(r.EdgeType),
         "gap_mm": round(float(gap[id_to_idx[int(r.FromClusterID)], id_to_idx[int(r.ToClusterID)]]), 3),
         "delta_e76": round(de(id_to_idx[int(r.FromClusterID)], id_to_idx[int(r.ToClusterID)]), 3)}
        for r in topology.itertuples(index=False)]
    # closest non-contact face pairs (e.g. the two ring end faces 1 & 2) get reported too
    noncontact = sorted(
        ((round(float(gap[i, j]), 3), round(de(i, j), 3), ids[i], ids[j])
         for i, j in all_pairs if tuple(sorted((i, j))) not in contact_set),
        key=lambda t: t[0])
    closest_noncontact = [
        {"from_cluster_id": a, "to_cluster_id": b, "gap_mm": g, "delta_e76": d}
        for g, d, a, b in noncontact[:8]]

    cmap = ListedColormap(colors, name="model_a_clusters_v1")
    norm = BoundaryNorm(np.arange(-0.5, len(ids) + 0.5, 1.0), cmap.N)

    acc = points[points["ClusterID"] >= 0].copy()
    acc["ColorIdx"] = acc["ClusterID"].astype(int).map(id_to_idx)
    res = points[points["ClusterID"] == -1]

    fig = plt.figure(figsize=FIGSIZE_IN, dpi=DPI)
    ax = fig.add_axes([0.005, 0.06, 0.80, 0.92], projection="3d")
    if len(res):
        ax.scatter(res["X"], res["Y"], res["Z"], c=RESIDUAL_COLOR, s=POINT_SIZE_PT2 * 0.8,
                   marker=POINT_MARKER, linewidths=0, alpha=0.9, depthshade=False)
    ax.scatter(acc["X"], acc["Y"], acc["Z"], c=acc["ColorIdx"], cmap=cmap, norm=norm,
               s=POINT_SIZE_PT2, marker=POINT_MARKER, linewidths=0, alpha=POINT_ALPHA,
               depthshade=False, rasterized=False)
    set_axis_style(ax, points, times)

    # segmented colorbar, ticks relabelled with the actual (non-contiguous) ClusterIDs
    cax = fig.add_axes([0.855, 0.185, 0.026, 0.63])
    cbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=cax,
                        boundaries=np.arange(-0.5, len(ids) + 0.5, 1.0),
                        ticks=np.arange(len(ids)), spacing="uniform")
    cbar.ax.set_yticklabels([str(c) for c in ids])
    cbar.set_label("ClusterID", fontproperties=times, rotation=90, labelpad=7)
    cbar.ax.tick_params(labelsize=11, width=0.8, length=3)
    for label in cbar.ax.get_yticklabels():
        label.set_fontproperties(times)
    cbar.outline.set_linewidth(0.8)

    # residual proxy note under the colorbar
    if len(res):
        proxy = Line2D([0], [0], marker="o", linestyle="none", markersize=5,
                       markerfacecolor=RESIDUAL_COLOR, markeredgecolor="none")
        leg = fig.legend([proxy], [f"殘留點（{len(res)} 點）"], loc="lower right",
                         bbox_to_anchor=(0.985, 0.055), frameon=False,
                         prop=fm.FontProperties(family="DFKai-SB", size=10), handletextpad=0.4)
        leg.set_zorder(5)

    png = output_dir / f"{figure_stem}.png"
    svg = output_dir / f"{figure_stem}.svg"
    png_meta = {"Title": "Model A verified geometric feature segmentation",
                "Author": "Chapter 4 verified-figure pipeline",
                "Subject": "ClusterID (non-contiguous) from method-only v3 output",
                "Software": "generate_model_a_v3_figure_4_7_segmentation.py"}
    svg_meta = {"Title": "Model A verified geometric feature segmentation",
                "Description": "ClusterID (non-contiguous) from method-only v3 output",
                "Creator": "generate_model_a_v3_figure_4_7_segmentation.py",
                "Date": "2026-07-23",
                "Keywords": ["Model A", "ClusterID", "geometric feature segmentation"]}
    fig.savefig(png, dpi=DPI, metadata=png_meta)
    fig.savefig(svg, format="svg", metadata=svg_meta)
    plt.close(fig)

    gray = qa_dir / f"{figure_stem}_灰階檢查.png"
    with Image.open(png) as image:
        ImageOps.grayscale(image.convert("RGB")).save(gray, dpi=(DPI, DPI))

    dejavu = svg.read_text(encoding="utf-8").count("DejaVu Sans")
    if dejavu != 0:
        raise ValueError(f"DejaVu fallback in SVG: {dejavu} occurrences.")

    occ = content_occupancy(png)
    if occ["width_fraction"] < 0.78 or occ["height_fraction"] < 0.78:
        raise ValueError(f"Excessive white space: {occ}")

    qa = {
        "schema_version": "1.0",
        "figure": "圖 4.7 Model A 驗證後幾何特徵分割結果",
        "status": "PASS_AWAITING_USER_CONFIRMATION",
        "note_prioritised_department_format_pdf": "已優先對照系上格式PDF（圖無標題、英數 Times New Roman、中文 DFKai-SB）",
        "required_caption_note_zh": (
            "圖中 ClusterID 為驗證後接受之語義特徵面的原始分群編號。Model A 初始特徵辨識共 15 群，"
            "僅 13 群通過驗收成為獨立語義特徵面；其餘編號（11、12）未能單獨形成穩定面型，"
            "於修正階段併入相鄰圓柱面而未列入，故所示 ClusterID 為非連續的 "
            "0、1、2、3、4、5、6、7、8、9、10、13、14。此編號與 FaceSummary、TopologyEdges 及圖 4.8 一致。"),
        "cluster_id_is_non_contiguous": True,
        "text_must_mention_non_contiguous_cluster_id": True,
        "method_alignment": {
            "chapter_3_sections": ["3.4 特徵分割", "3.5 平面與圓柱特徵辨識"],
            "visual_encoding": "color represents ClusterID only",
            "topology_use_boundary": "verified topology used only to assign contrasting colors to related faces",
            "does_not_encode": ["semantic component", "topology relation type", "BooleanType", "CSG"],
            "validation_overall": validation["overall"],
            "method_source_separation": validation["method_source_separation"]["status"],
            "five_layer_validation": validation["five_layer_validation"],
        },
        "data": {
            "points": int(len(points)),
            "accepted_points": int((points["ClusterID"] >= 0).sum()),
            "residual_points": int((points["ClusterID"] == -1).sum()),
            "accepted_cluster_ids": ids,
            "faces": int(len(faces)),
            "topology_relations_used_for_color_qa": int(len(topology)),
            "topology_type_counts": {t: int((topology["EdgeType"] == t).sum())
                                     for t in ["Adjacency", "OrthogonalAdjacency", "EndCap"]},
        },
        "format": {
            "figure_size_in": list(FIGSIZE_IN), "figure_width_cm": round(FIGSIZE_IN[0] * 2.54, 3),
            "dpi": DPI, "english_numbers_font": "Times New Roman 12 pt",
            "chinese_font_if_used": "DFKai-SB", "title_inside_figure": False,
            "view_elevation_deg": VIEW_ELEV, "view_azimuth_deg": VIEW_AZIM,
            "point_marker": POINT_MARKER, "point_size_pt2": POINT_SIZE_PT2,
            "palette_name": palette_name,
            "color_source": "pinned_from_confirmed" if fixed_colors is not None else "optimized",
            "cluster_colors_by_id": {str(cid): colors[i] for i, cid in enumerate(ids)},
            "residual_color": RESIDUAL_COLOR,
            "color_contrast_metric": "CIE 1976 Delta E",
            "color_contrast_objective": "over ALL face pairs, proximity-weighted (closer faces -> higher required contrast)",
            "gap_alpha_mm_to_delta_e": GAP_ALPHA,
            "orthogonal_pair_floor_delta_e76": MIN_ORTHOGONAL_DELTA_E_FLOOR,
            "orthogonal_pair_min_delta_e76": round(min(ortho_de), 3) if ortho_de else None,
            "contact_pair_floor_delta_e76": MIN_CONTACT_DELTA_E_FLOOR,
            "contact_pair_min_delta_e76": round(min(contact_de), 3),
            "contact_pair_min_lightness_diff_for_bw": round(float(min_contact_dL), 3),
            "all_pair_floor_delta_e76": MIN_ALLPAIRS_DELTA_E_FLOOR,
            "all_pair_min_delta_e76": round(min(allpairs_de), 3),
            "all_pair_mean_delta_e76": round(mean_de, 3),
            "topology_contact_contrast": adjacent_contrast,
            "closest_noncontact_pairs": closest_noncontact,
            "svg_dejavu_occurrences": dejavu, "occupancy": occ,
        },
        "source_sha256": {p.name: sha256(p) for p in (RESULT, FACES, TOPOLOGY, VALIDATION)},
        "outputs": {png.name: sha256(png), svg.name: sha256(svg),
                    str(gray.relative_to(output_dir)): sha256(gray)},
        "release_boundary": "Only Figure 4.7 is generated; later Model A figures remain blocked until user confirmation.",
    }
    (output_dir / f"{figure_stem}_QA.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"png": str(png), "svg": str(svg),
            "contact_min_delta_e": round(min(contact_de), 2),
            "all_pair_min_delta_e": round(min(allpairs_de), 2),
            "mean_delta_e": round(mean_de, 2),
            "closest_noncontact_pairs": closest_noncontact[:4]}


def main():
    parser = argparse.ArgumentParser(description="Generate only the Model A v3 Figure 4.7 segmentation image.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--palette", choices=sorted(PALETTES), default="vivid",
                        help="配色方案：vivid（鮮豔，預設，= v2）或 jewel（沉穩寶石，另存配色B）")
    parser.add_argument("--elev", type=int, default=None, help="View elevation override (default 20)")
    parser.add_argument("--azim", type=int, default=None, help="View azimuth override (default 140)")
    parser.add_argument("--pin-colors", type=Path, default=None,
                        help="Path to a confirmed QA JSON; pin cluster colours to its "
                             "format.cluster_colors_by_id (change only the view, not the palette).")
    args = parser.parse_args()
    fixed_colors = None
    if args.pin_colors is not None:
        pinned_qa = json.loads(args.pin_colors.read_text(encoding="utf-8"))
        fixed_colors = pinned_qa["format"]["cluster_colors_by_id"]
    print(json.dumps(generate(args.output_dir.resolve(), args.palette, args.elev, args.azim, fixed_colors),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
