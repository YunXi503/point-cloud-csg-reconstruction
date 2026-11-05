from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "零件" / "Result_Model A.csv"
OUT_PATH = ROOT / "Model A Segmentation.png"

SEMANTIC_COLORS = {
    "Plane": "#1f77b4",
    "Cylinder": "#d62728",
    "unclassified": "#7f7f7f",
}


def semantic_group(feature_type: str) -> str:
    if feature_type.startswith("Plane"):
        return "Plane"
    if feature_type.startswith("Cylinder"):
        return "Cylinder"
    return "unclassified"


def main():
    df = pd.read_csv(CSV_PATH)
    required = {"X", "Y", "Z", "FeatureType"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["FeatureType"] = df["FeatureType"].fillna("unclassified")
    df["SemanticGroup"] = df["FeatureType"].apply(semantic_group)
    df["Color"] = df["SemanticGroup"].map(SEMANTIC_COLORS).fillna("#7f7f7f")

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

    ax.set_title("Model A Plane/Cylinder Segmentation")
    ax.set_xlabel("X Axis (mm)")
    ax.set_ylabel("Y Axis (mm)")
    ax.set_zlabel("Z Axis (mm)")

    order = [
        "Plane",
        "Cylinder",
        "unclassified",
    ]
    counts = df["SemanticGroup"].value_counts().to_dict()
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=SEMANTIC_COLORS[name],
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
