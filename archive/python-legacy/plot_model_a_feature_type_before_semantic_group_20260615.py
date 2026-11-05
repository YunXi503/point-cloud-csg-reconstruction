from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "零件" / "Result_Model A.csv"
OUT_PATH = ROOT / "Model A Segmentation.png"

FEATURE_COLORS = {
    "Plane_XZ": "#1f77b4",
    "Plane_YZ": "#2ca02c",
    "Plane_XY": "#ff7f0e",
    "Plane_oblique": "#9467bd",
    "Cylinder_axisY_outer": "#d62728",
    "Cylinder_axisY_inner": "#17becf",
    "Cylinder_axisX": "#8c564b",
    "unclassified": "#7f7f7f",
}


def main():
    df = pd.read_csv(CSV_PATH)
    required = {"X", "Y", "Z", "ClusterID", "FeatureType"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["FeatureType"] = df["FeatureType"].fillna("unclassified")
    df["Color"] = df["FeatureType"].map(FEATURE_COLORS).fillna("#bcbd22")

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(
        df["X"],
        df["Y"],
        df["Z"],
        c=df["Color"],
        s=2.5,
        alpha=0.95,
        linewidths=0,
    )

    x_range = df["X"].max() - df["X"].min()
    y_range = df["Y"].max() - df["Y"].min()
    z_range = df["Z"].max() - df["Z"].min()
    ax.set_box_aspect([x_range, y_range, z_range])
    ax.view_init(elev=35, azim=135)

    ax.set_title("Model A Feature-Type Segmentation")
    ax.set_xlabel("X Axis (mm)")
    ax.set_ylabel("Y Axis (mm)")
    ax.set_zlabel("Z Axis (mm)")

    order = [
        "Plane_XZ",
        "Plane_YZ",
        "Plane_XY",
        "Plane_oblique",
        "Cylinder_axisY_outer",
        "Cylinder_axisY_inner",
        "Cylinder_axisX",
        "unclassified",
    ]
    counts = df["FeatureType"].value_counts().to_dict()
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=FEATURE_COLORS[name],
            markersize=7,
            label=f"{name} ({counts.get(name, 0)})",
        )
        for name in order
        if name in counts
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)

    plt.tight_layout()
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
