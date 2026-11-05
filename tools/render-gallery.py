"""Render portfolio previews directly from the recorded reference point tables."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"stepped-cylinder": "Stepped Cylinder", "l-bracket": "L-Bracket",
         "model-a": "Model A", "blind-hole-hex-base": "Blind-Hole Hex Base"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw(axis, frame, title):
    points = frame[["X", "Y", "Z"]].to_numpy(float)
    labels = frame["ClusterID"].to_numpy(int)
    palette = plt.get_cmap("tab20")
    colors = np.array([palette(int(label) % 20) if label >= 0 else (0.48, 0.48, 0.48, 0.85) for label in labels])
    axis.scatter(*points.T, c=colors, s=1.8, linewidths=0, depthshade=False, rasterized=True)
    center = (points.max(axis=0) + points.min(axis=0)) / 2
    radius = float(np.ptp(points, axis=0).max()) * 0.55
    for setter, value in zip([axis.set_xlim, axis.set_ylim, axis.set_zlim], center):
        setter(value - radius, value + radius)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=25, azim=-57)
    axis.set_title(title, fontsize=12, pad=2)
    axis.set_xlabel("X", fontsize=8, labelpad=0)
    axis.set_ylabel("Y", fontsize=8, labelpad=0)
    axis.set_zlabel("Z", fontsize=8, labelpad=0)
    axis.tick_params(labelsize=7, pad=0)
    for coordinate in [axis.xaxis, axis.yaxis, axis.zaxis]:
        coordinate.pane.fill = False
    axis.grid(alpha=0.18)


def main():
    cases = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
    output = ROOT / "assets"
    output.mkdir(exist_ok=True)
    overview = plt.figure(figsize=(10, 8), facecolor="white")
    records = []
    for position, case in enumerate(cases, 1):
        expected = next(item for item in case["output_checks"] if item["filename"].startswith("Result_"))
        source = ROOT / case["reference_directory"] / expected["filename"]
        if sha256(source) != expected["recorded_sha256"]:
            raise ValueError("Reference hash differs: " + str(source))
        frame = pd.read_csv(source)
        draw(overview.add_subplot(2, 2, position, projection="3d"), frame, NAMES[case["id"]])
        figure = plt.figure(figsize=(5.2, 4.2), facecolor="white")
        draw(figure.add_subplot(111, projection="3d"), frame, NAMES[case["id"]])
        target = output / (case["id"] + ".png")
        figure.savefig(target, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        records.append({"case": case["id"], "source": source.relative_to(ROOT).as_posix(),
                        "source_sha256": sha256(source), "point_rows": len(frame),
                        "unassigned_rows": int((frame["ClusterID"] < 0).sum()),
                        "output": target.relative_to(ROOT).as_posix(), "output_sha256": sha256(target)})
    overview.subplots_adjust(top=0.92, bottom=0.06, hspace=0.2, wspace=0.06)
    overview.suptitle("Geometric feature segmentation from point normals", fontsize=15, y=0.98)
    overview.text(0.5, 0.015, "Recorded reference data · Colors: ClusterID · Grey: unassigned points · All rows shown", ha="center", fontsize=9, color="#555555")
    overview.savefig(output / "overview.png", dpi=160, facecolor="white")
    plt.close(overview)
    manifest = {"purpose": "Portfolio preview, not a replacement for confirmed thesis figures",
                "method": "All source rows shown without smoothing, geometry reconstruction, filtering or point subsampling",
                "cases": records, "overview_sha256": sha256(output / "overview.png")}
    (output / "data-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"images": len(records) + 1, "source_rows": [item["point_rows"] for item in records]}, indent=2))


if __name__ == "__main__":
    main()
