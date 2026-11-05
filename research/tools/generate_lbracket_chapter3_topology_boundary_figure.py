from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image

from build_stepped_cylinder_independent_truth import build_edge_map, read_stl_triangles


DPI = 450
ORTHOGONAL_COLOR = "#3F6F93"
ENDCAP_COLOR = "#D27A1E"
ADJACENCY_COLOR = "#555555"
MODEL_COLOR = "#D9DEE2"
OUTLINE_COLOR = "#6A737B"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal_3d(ax: Any, xyz: np.ndarray) -> None:
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    center = (minimum + maximum) / 2.0
    radius = float(np.max(maximum - minimum) / 2.0) * 1.04
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1))


def triangle_cluster_map(truth: dict[str, Any]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for surface in truth["surfaces"]:
        for triangle_index in surface["triangle_indices"]:
            mapping[int(triangle_index)] = int(surface["cluster_id"])
    return mapping


def shared_boundaries(
    triangles: np.ndarray,
    truth: dict[str, Any],
    topology: pd.DataFrame,
) -> tuple[dict[tuple[int, int, str], list[tuple[np.ndarray, np.ndarray]]], list[dict[str, Any]]]:
    relation_type = {
        tuple(sorted((int(row.FromClusterID), int(row.ToClusterID)))): str(row.EdgeType)
        for row in topology.itertuples(index=False)
    }
    relation_values = {
        tuple(sorted((int(row.FromClusterID), int(row.ToClusterID)))): row
        for row in topology.itertuples(index=False)
    }
    mapping = triangle_cluster_map(truth)
    boundary_segments: dict[tuple[int, int, str], list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    for key, incident in build_edge_map(triangles).items():
        if len(incident) != 2 or incident[0] not in mapping or incident[1] not in mapping:
            continue
        first, second = mapping[incident[0]], mapping[incident[1]]
        if first == second:
            continue
        pair = tuple(sorted((first, second)))
        if pair not in relation_type:
            continue
        boundary_segments[(pair[0], pair[1], relation_type[pair])].append(
            (np.asarray(key[0], dtype=float), np.asarray(key[1], dtype=float))
        )

    evidence_rows: list[dict[str, Any]] = []
    for (first, second, edge_type), segments in sorted(boundary_segments.items()):
        row = relation_values[(first, second)]
        evidence_rows.append(
            {
                "FromClusterID": first,
                "ToClusterID": second,
                "EdgeType": edge_type,
                "MinDistance": float(row.MinDistance),
                "DirectionDot": float(row.DirectionDot),
                "SharedMeshEdgeCount": len(segments),
                "SharedBoundaryLength": float(sum(np.linalg.norm(end - start) for start, end in segments)),
                "MethodRuleStatus": str(row.RuleStatus),
                "IndependentBoundaryStatus": "PASS" if segments else "FAIL",
            }
        )
    expected = {
        (*sorted((int(row.FromClusterID), int(row.ToClusterID))), str(row.EdgeType))
        for row in topology.itertuples(index=False)
    }
    if set(boundary_segments) != expected:
        raise ValueError(f"方法拓樸與獨立網格邊界不一致：missing={sorted(expected-set(boundary_segments))}")
    return boundary_segments, evidence_rows


def draw_view(
    ax: Any,
    triangles: np.ndarray,
    boundaries: dict[tuple[int, int, str], list[tuple[np.ndarray, np.ndarray]]],
    elev: float,
    azim: float,
) -> None:
    collection = Poly3DCollection(
        triangles,
        facecolors=MODEL_COLOR,
        edgecolors="none",
        linewidths=0,
        alpha=0.60,
    )
    ax.add_collection3d(collection)
    styles = {
        "OrthogonalAdjacency": (ORTHOGONAL_COLOR, 1.55, "-", 30),
        "EndCap": (ENDCAP_COLOR, 2.35, (0, (3.0, 1.3)), 35),
        "Adjacency": (ADJACENCY_COLOR, 1.35, (0, (1.2, 1.2)), 25),
    }
    for (_, _, edge_type), segments in boundaries.items():
        color, width, linestyle, zorder = styles[edge_type]
        for start, end in segments:
            ax.plot(
                [start[0], end[0]], [start[1], end[1]], [start[2], end[2]],
                color=color, linewidth=width, linestyle=linestyle,
                solid_capstyle="round", alpha=0.98, zorder=zorder,
            )
    xyz = triangles.reshape(-1, 3)
    equal_3d(ax, xyz)
    ax.view_init(elev=elev, azim=azim)
    ax.set_proj_type("ortho")
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)


def write_evidence(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "SharedMeshEdgeCount", "SharedBoundaryLength", "MethodRuleStatus", "IndependentBoundaryStatus",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            formatted = dict(row)
            formatted["MinDistance"] = f"{float(row['MinDistance']):.9f}"
            formatted["DirectionDot"] = f"{float(row['DirectionDot']):.9f}"
            formatted["SharedBoundaryLength"] = f"{float(row['SharedBoundaryLength']):.9f}"
            writer.writerow(formatted)


def generate(data_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    topology_path = data_dir / "TopologyEdges_L_Bracket_chapter3_verified.csv"
    truth_path = data_dir / "GroundTruth_L_Bracket_independent.json"
    mesh_path = data_dir / "BlendEvaluatedMesh_L_Bracket.stl"
    validation_path = data_dir / "ValidationSummary_L_Bracket_chapter3.json"
    topology = pd.read_csv(topology_path)
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("overall") != "PASS" or validation.get("provenance_separation") != "PASS":
        raise ValueError("只有第三章方法與獨立真值皆通過時才能產生正式拓樸圖。")
    triangles = read_stl_triangles(mesh_path)
    boundaries, evidence_rows = shared_boundaries(triangles, truth, topology)

    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": 12,
            "svg.fonttype": "none",
            "svg.hashsalt": "l-bracket-chapter3-boundary-topology-v3-260722",
            "savefig.dpi": DPI,
            "savefig.facecolor": "white",
        }
    )
    figure = plt.figure(figsize=(8.2, 4.55), facecolor="white")
    grid = figure.add_gridspec(1, 2, width_ratios=(1.18, 1.0), wspace=-0.05)
    first = figure.add_subplot(grid[0, 0], projection="3d")
    second = figure.add_subplot(grid[0, 1], projection="3d")
    draw_view(first, triangles, boundaries, elev=25, azim=132)
    draw_view(second, triangles, boundaries, elev=21, azim=-48)

    counts = topology["EdgeType"].value_counts().to_dict()
    handles = [
        Line2D([0], [0], color=ORTHOGONAL_COLOR, lw=2.0, linestyle="-", label=rf"$\perp\;{int(counts.get('OrthogonalAdjacency', 0))}$"),
        Line2D([0], [0], color=ENDCAP_COLOR, lw=2.8, linestyle=(0, (3.0, 1.3)), label=rf"$\odot\;{int(counts.get('EndCap', 0))}$"),
        Line2D([0], [0], color=ADJACENCY_COLOR, lw=1.5, linestyle=(0, (1.2, 1.2)), label=rf"$-\;{int(counts.get('Adjacency', 0))}$"),
    ]
    figure.legend(
        handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=3,
        frameon=False, handlelength=2.4, handletextpad=0.55, columnspacing=2.0,
    )
    figure.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.12)

    base_name = "圖4.5_L_Bracket_語義拓樸_實體接觸邊界版"
    png_path = output_dir / f"{base_name}.png"
    svg_path = output_dir / f"{base_name}.svg"
    figure.savefig(png_path, dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.03)
    figure.savefig(
        svg_path, facecolor="white", bbox_inches="tight", pad_inches=0.03,
        metadata={"Date": "2026-07-22"},
    )
    plt.close(figure)

    evidence_path = output_dir / "圖4.5_L_Bracket_拓樸邊界證據.csv"
    write_evidence(evidence_path, evidence_rows)
    image = Image.open(png_path)
    dpi = image.info.get("dpi", (0, 0))
    manifest = {
        "schema_version": "1.0",
        "figure": "圖 4.5 L型板語義拓樸關係",
        "data_kind": "real verified experiment result",
        "method_topology_source": {"filename": topology_path.name, "sha256": sha256(topology_path)},
        "independent_boundary_source": {
            "truth": {"filename": truth_path.name, "sha256": sha256(truth_path)},
            "mesh": {"filename": mesh_path.name, "sha256": sha256(mesh_path)},
        },
        "validation_source": {"filename": validation_path.name, "sha256": sha256(validation_path)},
        "views": [
            {"symbol": "1", "elevation": 25, "azimuth": 132},
            {"symbol": "2", "elevation": 21, "azimuth": -48},
        ],
        "relationship_counts": {
            "Adjacency": int(counts.get("Adjacency", 0)),
            "OrthogonalAdjacency": int(counts.get("OrthogonalAdjacency", 0)),
            "EndCap": int(counts.get("EndCap", 0)),
        },
        "boundary_evidence_rows": len(evidence_rows),
        "png": {
            "filename": png_path.name,
            "sha256": sha256(png_path),
            "pixels": [int(image.width), int(image.height)],
            "dpi": [float(dpi[0]), float(dpi[1])],
        },
        "svg": {"filename": svg_path.name, "sha256": sha256(svg_path)},
        "evidence_csv": {"filename": evidence_path.name, "sha256": sha256(evidence_path)},
    }
    (output_dir / "圖4.5_L_Bracket_拓樸圖資料清單.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the method-consistent L-Bracket topology boundary figure.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    generate(arguments.data_dir.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
