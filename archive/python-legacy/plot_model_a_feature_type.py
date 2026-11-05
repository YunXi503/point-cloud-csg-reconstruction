from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "零件" / "Result_Model A.csv"
OUT_PATH = ROOT / "Model A Segmentation.png"

DISPLAY_COLORS = {
    "Plane_XZ": "#1f77b4",
    "Plane_YZ": "#2ca02c",
    "Plane_XY": "#ff7f0e",
    "Plane_oblique": "#9467bd",
    "Cylinder": "#d62728",
    "unclassified": "#7f7f7f",
}


def initial_display_label(feature_type: str) -> str:
    if feature_type.startswith("Cylinder"):
        return "Cylinder"
    if feature_type.startswith("Plane"):
        return feature_type
    return "unclassified"


def fit_circle(a, b):
    # Algebraic least-squares circle fit for a 2D cylinder cross-section.
    mat = np.column_stack([2.0 * a, 2.0 * b, np.ones(len(a))])
    rhs = (a * a) + (b * b)
    c1, c2, k = np.linalg.lstsq(mat, rhs, rcond=None)[0]
    r2 = (c1 * c1) + (c2 * c2) + k
    if r2 <= 0:
        return None
    return float(c1), float(c2), float(np.sqrt(r2))


def merge_similar_circles(circles, center_eps=2.0, radius_eps=2.0):
    merged = []
    for circle in circles:
        matched = None
        for item in merged:
            dc = np.hypot(circle["c1"] - item["c1"], circle["c2"] - item["c2"])
            dr = abs(circle["r"] - item["r"])
            if dc <= center_eps and dr <= radius_eps:
                matched = item
                break

        if matched is None:
            merged.append(circle.copy())
            continue

        total = matched["count"] + circle["count"]
        w0 = matched["count"] / total
        w1 = circle["count"] / total
        matched["c1"] = (matched["c1"] * w0) + (circle["c1"] * w1)
        matched["c2"] = (matched["c2"] * w0) + (circle["c2"] * w1)
        matched["r"] = (matched["r"] * w0) + (circle["r"] * w1)
        matched["min_axis"] = min(matched["min_axis"], circle["min_axis"])
        matched["max_axis"] = max(matched["max_axis"], circle["max_axis"])
        matched["count"] = total
    return merged


def reliable_cylinder_circles(df, feature_type, axis):
    source = df[df["FeatureType"].eq(feature_type)]
    circles = []
    for _, group in source.groupby("ClusterID"):
        if len(group) < 30:
            continue

        if axis == "X":
            a = group["Y"].to_numpy()
            b = group["Z"].to_numpy()
            min_axis = float(group["X"].min())
            max_axis = float(group["X"].max())
        elif axis == "Y":
            a = group["X"].to_numpy()
            b = group["Z"].to_numpy()
            min_axis = float(group["Y"].min())
            max_axis = float(group["Y"].max())
        else:
            raise ValueError(f"Unsupported cylinder axis: {axis}")

        fitted = fit_circle(a, b)
        if fitted is None:
            continue

        c1, c2, radius = fitted
        residual = np.abs(np.sqrt((a - c1) ** 2 + (b - c2) ** 2) - radius)
        if not (5.0 <= radius <= 80.0):
            continue
        if float(np.median(residual)) > 0.75:
            continue

        circles.append(
            {
                "c1": c1,
                "c2": c2,
                "r": radius,
                "min_axis": min_axis,
                "max_axis": max_axis,
                "count": int(len(group)),
            }
        )
    return merge_similar_circles(circles)


def refine_cylinder_display_labels(df):
    labels = df["FeatureType"].fillna("unclassified").apply(initial_display_label).copy()
    plane_or_unknown = labels.str.startswith("Plane") | labels.eq("unclassified")

    # Axis-Y cylinders: cross-section is XZ; the axis coordinate is Y.
    for feature_type in ("Cylinder_axisY_outer", "Cylinder_axisY_inner"):
        for circle in reliable_cylinder_circles(df, feature_type, axis="Y"):
            dx = df["X"] - circle["c1"]
            dz = df["Z"] - circle["c2"]
            radius_at_point = np.sqrt((dx * dx) + (dz * dz)).clip(lower=1e-9)
            radial_alignment = ((dx * df["NX"]) + (dz * df["NZ"])) / radius_at_point
            in_axis_span = df["Y"].between(circle["min_axis"] - 2.0, circle["max_axis"] + 2.0)
            on_radius = (radius_at_point - circle["r"]).abs() <= 1.5
            cylinder_like = df["NY"].abs().le(0.22) & radial_alignment.abs().ge(0.80)
            labels.loc[plane_or_unknown & in_axis_span & on_radius & cylinder_like] = "Cylinder"

    # Axis-X cylinders: cross-section is YZ; the axis coordinate is X.
    for circle in reliable_cylinder_circles(df, "Cylinder_axisX", axis="X"):
        dy = df["Y"] - circle["c1"]
        dz = df["Z"] - circle["c2"]
        radius_at_point = np.sqrt((dy * dy) + (dz * dz)).clip(lower=1e-9)
        radial_alignment = ((dy * df["NY"]) + (dz * df["NZ"])) / radius_at_point
        in_axis_span = df["X"].between(circle["min_axis"] - 2.0, circle["max_axis"] + 2.0)
        on_radius = (radius_at_point - circle["r"]).abs() <= 1.5
        cylinder_like = df["NX"].abs().le(0.22) & radial_alignment.abs().ge(0.80)
        labels.loc[plane_or_unknown & in_axis_span & on_radius & cylinder_like] = "Cylinder"

    return labels


def main():
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    df = pd.read_csv(CSV_PATH)
    required = {"X", "Y", "Z", "NX", "NY", "NZ", "ClusterID", "FeatureType"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["FeatureType"] = df["FeatureType"].fillna("unclassified")
    df["DisplayFeatureType"] = df["FeatureType"].apply(initial_display_label)
    df["Color"] = df["DisplayFeatureType"].map(DISPLAY_COLORS).fillna("#7f7f7f")

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

    ax.set_title("Model A Core Feature-Type Segmentation")
    ax.set_xlabel("X Axis (mm)")
    ax.set_ylabel("Y Axis (mm)")
    ax.set_zlabel("Z Axis (mm)")

    order = [
        "Plane_XZ",
        "Plane_YZ",
        "Plane_XY",
        "Plane_oblique",
        "Cylinder",
        "unclassified",
    ]
    counts = df["DisplayFeatureType"].value_counts().to_dict()
    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=DISPLAY_COLORS[name],
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
