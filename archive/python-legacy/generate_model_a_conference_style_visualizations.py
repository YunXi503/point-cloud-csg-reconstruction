from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "零件"
RESULT_PATH = PART_DIR / "Result_Model A.csv"
FACE_PATH = PART_DIR / "FaceSummary_Model A.csv"
TOPOLOGY_PATH = PART_DIR / "TopologyEdges_Model A.csv"

SEGMENTATION_PNG = ROOT / "Model A Conference Style Segmentation.png"
TOPOLOGY_PNG = ROOT / "Model A Conference Style Topology.png"
BOOLEAN_PNG = ROOT / "Model A Conference Style Boolean Roles.png"
THREE_PANEL_PNG = ROOT / "Model A Conference Style Complete Visualization.png"


VIEW_ELEV = 24
VIEW_AZIM = 132
CMAP_NAME = "nipy_spectral"


def load_data():
    df = pd.read_csv(RESULT_PATH)
    faces = pd.read_csv(FACE_PATH)
    edges = pd.read_csv(TOPOLOGY_PATH)
    return df, faces, edges


def style_3d_axis(ax, df):
    ax.set_xlabel("X (mm)", labelpad=8)
    ax.set_ylabel("Y (mm)", labelpad=8)
    ax.set_zlabel("Z (mm)", labelpad=8)
    ax.view_init(elev=VIEW_ELEV, azim=VIEW_AZIM)
    ax.grid(True, color="#c9c9c9", linewidth=0.7)
    ax.set_xlim(df["X"].min(), df["X"].max())
    ax.set_ylim(df["Y"].min(), df["Y"].max())
    ax.set_zlim(df["Z"].min(), df["Z"].max())
    try:
        ax.set_box_aspect(
            (
                df["X"].max() - df["X"].min(),
                df["Y"].max() - df["Y"].min(),
                df["Z"].max() - df["Z"].min(),
            )
        )
    except Exception:
        pass


def scatter_by_cluster(ax, df, alpha=0.95, size=3.0):
    valid = df[df["ClusterID"] >= 0]
    invalid = df[df["ClusterID"] < 0]
    norm = Normalize(vmin=0, vmax=max(1, int(valid["ClusterID"].max())))
    cmap = plt.get_cmap(CMAP_NAME)
    sc = ax.scatter(
        valid["X"],
        valid["Y"],
        valid["Z"],
        c=valid["ClusterID"],
        cmap=cmap,
        norm=norm,
        s=size,
        marker=".",
        linewidths=0,
        alpha=alpha,
        depthshade=False,
    )
    if len(invalid):
        ax.scatter(
            invalid["X"],
            invalid["Y"],
            invalid["Z"],
            c="#808080",
            s=size,
            marker=".",
            linewidths=0,
            alpha=0.75,
            depthshade=False,
        )
    return sc


def save_segmentation(df):
    fig = plt.figure(figsize=(9.2, 7.5), dpi=220)
    ax = fig.add_subplot(111, projection="3d")
    sc = scatter_by_cluster(ax, df, alpha=0.95, size=3.2)
    style_3d_axis(ax, df)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.76, pad=0.08)
    cbar.set_label("Feature ID", rotation=90, labelpad=12)
    cbar.set_ticks(np.arange(0, int(df[df["ClusterID"] >= 0]["ClusterID"].max()) + 1, 2))
    ax.set_title("Model A feature segmentation", pad=16)
    fig.tight_layout()
    fig.savefig(SEGMENTATION_PNG, bbox_inches="tight")
    plt.close(fig)


def cluster_centers(df):
    valid = df[df["ClusterID"] >= 0]
    centers = valid.groupby("ClusterID")[["X", "Y", "Z"]].mean()
    return {int(k): tuple(v) for k, v in centers.iterrows()}


def edge_style(edge_type):
    if edge_type == "OrthogonalAdjacency":
        return "#f47c20", 2.2
    if edge_type == "EndCap":
        return "#f47c20", 2.0
    if edge_type == "SideBoundary":
        return "#f47c20", 1.7
    if edge_type == "OrthogonalCylinderIntersection":
        return "#d627ff", 2.4
    if edge_type == "ObliqueAdjacency":
        return "#2ca02c", 1.8
    return "#707070", 1.3


def save_topology(df, faces, edges):
    fig = plt.figure(figsize=(9.2, 7.5), dpi=220)
    ax = fig.add_subplot(111, projection="3d")
    scatter_by_cluster(ax, df, alpha=0.12, size=2.4)
    centers = cluster_centers(df)
    cmap = plt.get_cmap(CMAP_NAME)
    max_id = max(centers)

    for _, edge in edges.iterrows():
        a = int(edge["FromClusterID"])
        b = int(edge["ToClusterID"])
        if a not in centers or b not in centers:
            continue
        color, width = edge_style(edge["EdgeType"])
        xa, ya, za = centers[a]
        xb, yb, zb = centers[b]
        ax.plot([xa, xb], [ya, yb], [za, zb], color=color, linewidth=width, alpha=0.88)

    for cid, (x, y, z) in centers.items():
        color = cmap(cid / max(1, max_id))
        ax.scatter([x], [y], [z], s=70, c=[color], edgecolors="black", linewidths=0.5, depthshade=False)
        ax.text(
            x,
            y,
            z,
            f" ID {cid} ",
            fontsize=8,
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="#808080", alpha=0.92),
        )

    style_3d_axis(ax, df)
    ax.set_title("Model A topology validation", pad=16)
    legend_items = [
        Line2D([0], [0], color="#f47c20", lw=2.2, label="Adjacency / EndCap / SideBoundary"),
        Line2D([0], [0], color="#d627ff", lw=2.2, label="Cylinder intersection"),
        Line2D([0], [0], color="#707070", lw=1.6, label="Parallel relation"),
    ]
    ax.legend(handles=legend_items, loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=8)
    fig.tight_layout()
    fig.savefig(TOPOLOGY_PNG, bbox_inches="tight")
    plt.close(fig)


def save_boolean_roles(df, faces):
    role_by_cluster = {
        int(row["ClusterID"]): row["QualityFlag"] if row["QualityFlag"] == "SmallOutputFace" else row["BooleanRole"]
        for _, row in faces.iterrows()
    }
    colors = {
        "UnionFace": "#1f77b4",
        "DifferenceFace": "#d62728",
        "SmallOutputFace": "#ffb35c",
        "unclassified": "#808080",
    }
    fig = plt.figure(figsize=(9.2, 7.5), dpi=220)
    ax = fig.add_subplot(111, projection="3d")
    for role in ["UnionFace", "DifferenceFace", "SmallOutputFace"]:
        ids = [cid for cid, r in role_by_cluster.items() if r == role]
        pts = df[df["ClusterID"].isin(ids)]
        ax.scatter(
            pts["X"],
            pts["Y"],
            pts["Z"],
            c=colors[role],
            s=3.2 if role != "DifferenceFace" else 5.2,
            marker=".",
            linewidths=0,
            alpha=0.95,
            depthshade=False,
            label=role,
        )
    invalid = df[df["ClusterID"] < 0]
    if len(invalid):
        ax.scatter(invalid["X"], invalid["Y"], invalid["Z"], c=colors["unclassified"], s=3.2, marker=".", alpha=0.75, label="unclassified")

    style_3d_axis(ax, df)
    ax.set_title("Model A primitive Boolean roles", pad=16)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=8)
    fig.tight_layout()
    fig.savefig(BOOLEAN_PNG, bbox_inches="tight")
    plt.close(fig)


def save_three_panel(df, faces, edges):
    fig = plt.figure(figsize=(14.5, 4.9), dpi=220)
    axes = [
        fig.add_subplot(131, projection="3d"),
        fig.add_subplot(132, projection="3d"),
        fig.add_subplot(133, projection="3d"),
    ]

    sc = scatter_by_cluster(axes[0], df, alpha=0.95, size=2.0)
    style_3d_axis(axes[0], df)
    axes[0].set_title("(a) Feature segmentation", y=-0.16, fontsize=11, fontweight="bold")

    scatter_by_cluster(axes[1], df, alpha=0.10, size=1.8)
    centers = cluster_centers(df)
    for _, edge in edges.iterrows():
        a = int(edge["FromClusterID"])
        b = int(edge["ToClusterID"])
        if a not in centers or b not in centers:
            continue
        color, width = edge_style(edge["EdgeType"])
        xa, ya, za = centers[a]
        xb, yb, zb = centers[b]
        axes[1].plot([xa, xb], [ya, yb], [za, zb], color=color, linewidth=width * 0.75, alpha=0.85)
    for cid, (x, y, z) in centers.items():
        axes[1].scatter([x], [y], [z], s=38, c="#2ca25f", edgecolors="black", linewidths=0.35, depthshade=False)
    style_3d_axis(axes[1], df)
    axes[1].set_title("(b) Topology graph", y=-0.16, fontsize=11, fontweight="bold")

    role_by_cluster = {
        int(row["ClusterID"]): row["QualityFlag"] if row["QualityFlag"] == "SmallOutputFace" else row["BooleanRole"]
        for _, row in faces.iterrows()
    }
    role_colors = {"UnionFace": "#1f77b4", "DifferenceFace": "#d62728", "SmallOutputFace": "#ffb35c"}
    for role, color in role_colors.items():
        ids = [cid for cid, r in role_by_cluster.items() if r == role]
        pts = df[df["ClusterID"].isin(ids)]
        axes[2].scatter(pts["X"], pts["Y"], pts["Z"], c=color, s=2.3, marker=".", linewidths=0, alpha=0.95, depthshade=False)
    invalid = df[df["ClusterID"] < 0]
    if len(invalid):
        axes[2].scatter(invalid["X"], invalid["Y"], invalid["Z"], c="#808080", s=2.3, marker=".", linewidths=0, alpha=0.7, depthshade=False)
    style_3d_axis(axes[2], df)
    axes[2].set_title("(c) Boolean role", y=-0.16, fontsize=11, fontweight="bold")

    for ax in axes:
        ax.tick_params(labelsize=7)
        ax.xaxis.label.set_size(8)
        ax.yaxis.label.set_size(8)
        ax.zaxis.label.set_size(8)

    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.15, top=0.96, wspace=0.03)
    fig.savefig(THREE_PANEL_PNG, bbox_inches="tight")
    plt.close(fig)


def main():
    df, faces, edges = load_data()
    save_segmentation(df)
    save_topology(df, faces, edges)
    save_boolean_roles(df, faces)
    save_three_panel(df, faces, edges)
    print(f"Segmentation: {SEGMENTATION_PNG}")
    print(f"Topology: {TOPOLOGY_PNG}")
    print(f"Boolean roles: {BOOLEAN_PNG}")
    print(f"Three-panel: {THREE_PANEL_PNG}")


if __name__ == "__main__":
    main()
