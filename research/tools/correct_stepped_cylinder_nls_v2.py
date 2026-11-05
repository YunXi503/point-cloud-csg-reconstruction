from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FIT_RESIDUAL_THRESHOLD_MM = 1.5
NORMAL_THRESHOLD = 0.93


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_direction(vector: np.ndarray) -> np.ndarray:
    direction = np.asarray(vector, dtype=float)
    direction /= np.linalg.norm(direction)
    dominant = int(np.argmax(np.abs(direction)))
    if direction[dominant] < 0:
        direction = -direction
    return direction


def radial_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seed = np.eye(3)[int(np.argmin(np.abs(np.eye(3) @ axis)))]
    first = np.cross(axis, seed)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    second /= np.linalg.norm(second)
    return first, second


def initial_circle(values: np.ndarray) -> tuple[float, float, float]:
    x, y = values[:, 0], values[:, 1]
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(values))))
    rhs = x * x + y * y
    center_x, center_y, constant = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    radius = math.sqrt(max(float(constant + center_x * center_x + center_y * center_y), 0.0))
    return float(center_x), float(center_y), radius


def nonlinear_circle(values: np.ndarray) -> tuple[float, float, float, np.ndarray, int]:
    center_x, center_y, radius = initial_circle(values)
    iterations = 0
    for iterations in range(1, 101):
        delta_x = values[:, 0] - center_x
        delta_y = values[:, 1] - center_y
        distance = np.maximum(np.hypot(delta_x, delta_y), 1e-12)
        signed_residual = distance - radius
        jacobian = np.column_stack(
            (-delta_x / distance, -delta_y / distance, -np.ones(len(values)))
        )
        step = np.linalg.lstsq(jacobian, -signed_residual, rcond=None)[0]
        center_x += float(step[0])
        center_y += float(step[1])
        radius += float(step[2])
        if float(np.linalg.norm(step)) <= 1e-13:
            break
    signed_residual = np.hypot(values[:, 0] - center_x, values[:, 1] - center_y) - radius
    return center_x, center_y, radius, signed_residual, iterations


def fit_plane(points: np.ndarray, normals: np.ndarray) -> dict[str, Any]:
    center = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1]
    if float(normal @ normals.mean(axis=0)) < 0:
        normal = -normal
    normal /= np.linalg.norm(normal)
    residual = np.abs((points - center) @ normal)
    alignment = np.abs(normals @ normal)
    return {
        "geometry": "plane",
        "center": center,
        "normal": normal,
        "axis": np.zeros(3),
        "radius": 0.0,
        "axis_min": math.nan,
        "axis_max": math.nan,
        "residual": residual,
        "alignment": alignment,
        "iterations": 1,
    }


def fit_cylinder(points: np.ndarray, normals: np.ndarray) -> dict[str, Any]:
    _, _, vh = np.linalg.svd(normals, full_matrices=False)
    axis = canonical_direction(vh[-1])
    first, second = radial_basis(axis)
    projected = np.column_stack((points @ first, points @ second))
    center_first, center_second, radius, signed_residual, iterations = nonlinear_circle(projected)
    axis_values = points @ axis
    center = first * center_first + second * center_second + axis * float(axis_values.mean())
    delta = points - center
    radial = delta - np.outer(delta @ axis, axis)
    radial_length = np.linalg.norm(radial, axis=1)
    radial_unit = radial / np.maximum(radial_length[:, None], 1e-12)
    alignment = np.abs(np.sum(normals * radial_unit, axis=1))
    return {
        "geometry": "cylinder",
        "center": center,
        "normal": np.zeros(3),
        "axis": axis,
        "radius": radius,
        "axis_min": float(axis_values.min()),
        "axis_max": float(axis_values.max()),
        "residual": np.abs(signed_residual),
        "alignment": alignment,
        "iterations": iterations,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_related_clusters(value: Any) -> list[int]:
    return sorted(int(part.strip()) for part in str(value).split(";") if part.strip())


def build_outputs(arguments: argparse.Namespace) -> None:
    output_dir: Path = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    result = pd.read_csv(arguments.result)
    face_template = pd.read_csv(arguments.face_template)
    candidate_template = pd.read_csv(arguments.candidate_template)
    truth = json.loads(arguments.truth.read_text(encoding="utf-8"))
    mapping = pd.read_csv(arguments.surface_mapping)
    cluster_to_truth = {
        int(row["ClusterID"]): str(row["TruthSurfaceID"]) for _, row in mapping.iterrows()
    }
    truth_surfaces = {surface["surface_id"]: surface for surface in truth["surfaces"]}
    truth_candidates = truth["primitive_candidates"]
    points_all = result[["X", "Y", "Z"]].to_numpy(dtype=float)
    normals_all = result[["NX", "NY", "NZ"]].to_numpy(dtype=float)
    clusters_all = result["ClusterID"].to_numpy(dtype=int)

    face_rows: list[dict[str, Any]] = []
    fitted: dict[int, dict[str, Any]] = {}
    correction_rows: list[dict[str, Any]] = []
    template_by_cluster = {
        int(row["ClusterID"]): row for _, row in face_template.iterrows()
    }

    for cluster_id in sorted(template_by_cluster):
        template = template_by_cluster[cluster_id]
        mask = clusters_all == cluster_id
        points, normals = points_all[mask], normals_all[mask]
        if not len(points):
            raise ValueError(f"Cluster {cluster_id} 沒有點。")
        geometry = "cylinder" if str(template["FeatureType"]).startswith("Cylinder") else "plane"
        model = fit_cylinder(points, normals) if geometry == "cylinder" else fit_plane(points, normals)
        fitted[cluster_id] = model
        truth_id = cluster_to_truth[cluster_id]
        truth_surface = truth_surfaces[truth_id]
        old_radius = float(template["Radius"]) if geometry == "cylinder" else math.nan
        new_radius = float(model["radius"]) if geometry == "cylinder" else math.nan
        center = model["center"]
        normal = model["normal"]
        axis = model["axis"]
        residual = model["residual"]
        alignment = model["alignment"]
        validation_status = (
            arguments.status
            if float(np.max(residual)) <= FIT_RESIDUAL_THRESHOLD_MM
            and float(np.min(alignment)) >= NORMAL_THRESHOLD
            else "FAIL"
        )
        face_rows.append(
            {
                "ClusterID": cluster_id,
                "FeatureType": str(template["FeatureType"]),
                "PointCount": int(mask.sum()),
                "CenterX": center[0],
                "CenterY": center[1],
                "CenterZ": center[2],
                "NX": normal[0],
                "NY": normal[1],
                "NZ": normal[2],
                "AxisX": axis[0],
                "AxisY": axis[1],
                "AxisZ": axis[2],
                "MinX": float(points[:, 0].min()),
                "MaxX": float(points[:, 0].max()),
                "MinY": float(points[:, 1].min()),
                "MaxY": float(points[:, 1].max()),
                "MinZ": float(points[:, 2].min()),
                "MaxZ": float(points[:, 2].max()),
                "Radius": model["radius"],
                "AxisMin": model["axis_min"],
                "AxisMax": model["axis_max"],
                "FitResidualMax": float(np.max(residual)),
                "FitResidualMedian": float(np.median(residual)),
                "NormalConsistencyMin": float(np.min(alignment)),
                "MeshTriangleCount": int(truth_surface["triangle_count"]),
                "MeshConnectedComponents": int(truth_surface["mesh_connected_components"]),
                "ValidationStatus": validation_status,
            }
        )
        correction_rows.append(
            {
                "EntityType": "Face",
                "EntityID": cluster_id,
                "TruthID": truth_id,
                "Action": "GeometricNLSRefit" if geometry == "cylinder" else "PCARefit",
                "OldValue": old_radius,
                "NewValue": new_radius,
                "AbsoluteChange": abs(new_radius - old_radius) if geometry == "cylinder" else 0.0,
                "Reason": (
                    "依第三章改用幾何非線性最小平方法重估圓柱中心與半徑"
                    if geometry == "cylinder"
                    else "依第三章以PCA／最小平方法重估平面"
                ),
                "PointAssignmentChanged": False,
                "ValidationStatus": validation_status,
            }
        )

    face_output = output_dir / "FaceSummary_Stepped_Cylinder_verified_v2.csv"
    pd.DataFrame(face_rows).to_csv(
        face_output, index=False, encoding="utf-8", float_format="%.9f", lineterminator="\n"
    )

    candidate_rows: list[dict[str, Any]] = []
    for _, template in candidate_template.iterrows():
        candidate_id = str(template["CandidateID"])
        related_clusters = parse_related_clusters(template["RelatedClusters"])
        cylinder_clusters = [
            cluster_id for cluster_id in related_clusters if fitted[cluster_id]["geometry"] == "cylinder"
        ]
        plane_clusters = [
            cluster_id for cluster_id in related_clusters if fitted[cluster_id]["geometry"] == "plane"
        ]
        if len(cylinder_clusters) != 1 or len(plane_clusters) != 2:
            raise ValueError(f"{candidate_id} 未包含一個圓柱側面與兩個端面。")
        cylinder_cluster = cylinder_clusters[0]
        axis = fitted[cylinder_cluster]["axis"]
        plane_positions = sorted(float(fitted[cluster_id]["center"] @ axis) for cluster_id in plane_clusters)
        radius = float(fitted[cylinder_cluster]["radius"])
        depth = plane_positions[1] - plane_positions[0]
        related_truth = sorted(cluster_to_truth[cluster_id] for cluster_id in related_clusters)
        matches = [
            candidate
            for candidate in truth_candidates
            if sorted(candidate["related_surface_ids"]) == related_truth
        ]
        if len(matches) != 1:
            raise ValueError(f"{candidate_id} 無法一對一對應 STL-only 候選真值。")
        truth_candidate = matches[0]
        parameter_error = max(
            abs(radius - float(truth_candidate["radius_mm"])),
            abs(depth - float(truth_candidate["depth_mm"])),
        )
        candidate_rows.append(
            {
                "CandidateID": candidate_id,
                "PrimitiveType": str(template["PrimitiveType"]),
                "RelatedClusters": ";".join(str(value) for value in related_clusters),
                "Length": template.get("Length", math.nan),
                "Width": template.get("Width", math.nan),
                "Height": template.get("Height", math.nan),
                "Radius": radius,
                "Depth": depth,
                "BooleanType": str(template["BooleanType"]),
                "ParameterErrorMax": parameter_error,
                "ValidationStatus": arguments.status,
            }
        )
        correction_rows.append(
            {
                "EntityType": "Candidate",
                "EntityID": candidate_id,
                "TruthID": truth_candidate["candidate_id"],
                "Action": "PropagateCorrectedRadius",
                "OldValue": float(template["Radius"]),
                "NewValue": radius,
                "AbsoluteChange": abs(radius - float(template["Radius"])),
                "Reason": "候選半徑改由修正後圓柱語義特徵面取得；深度由兩端面沿軸向距離計算",
                "PointAssignmentChanged": False,
                "ValidationStatus": arguments.status,
            }
        )

    candidate_output = output_dir / "PrimitiveCandidates_Stepped_Cylinder_verified_v2.csv"
    pd.DataFrame(candidate_rows).to_csv(
        candidate_output, index=False, encoding="utf-8", float_format="%.9f", lineterminator="\n"
    )
    trace_output = output_dir / "CorrectionTrace_Stepped_Cylinder_v2.csv"
    pd.DataFrame(correction_rows).to_csv(
        trace_output, index=False, encoding="utf-8", float_format="%.9f", lineterminator="\n"
    )

    result_output = output_dir / "Result_Stepped_Cylinder_verified_v2.csv"
    topology_output = output_dir / "TopologyEdges_Stepped_Cylinder_verified_v2.csv"
    csg_output = output_dir / "CSGTree_Stepped_Cylinder_verified_v2.json"
    shutil.copyfile(arguments.result, result_output)
    shutil.copyfile(arguments.topology, topology_output)
    shutil.copyfile(arguments.csg, csg_output)

    outputs = [result_output, face_output, topology_output, candidate_output, csg_output, trace_output]
    manifest = {
        "schema_version": "1.0",
        "case": "Stepped Cylinder",
        "version": "verified_v2",
        "status_written": arguments.status,
        "method": {
            "plane": "PCA / least squares",
            "cylinder_axis_initialization": "smallest right singular vector of the cluster normal matrix",
            "cylinder_radius_center": "algebraic circle initialization followed by Gauss-Newton geometric nonlinear least squares",
            "fit_residual_threshold_mm": FIT_RESIDUAL_THRESHOLD_MM,
            "normal_threshold": NORMAL_THRESHOLD,
        },
        "inputs": {
            name: {"filename": path.name, "sha256": sha256(path)}
            for name, path in {
                "result": arguments.result,
                "face_template": arguments.face_template,
                "topology": arguments.topology,
                "candidate_template": arguments.candidate_template,
                "csg": arguments.csg,
                "truth": arguments.truth,
                "surface_mapping": arguments.surface_mapping,
            }.items()
        },
        "program": {"filename": Path(__file__).name, "sha256": sha256(Path(__file__))},
        "outputs": {path.name: sha256(path) for path in outputs},
        "invariants": {
            "point_coordinates_normals_and_cluster_ids_changed": False,
            "topology_changed": False,
            "csg_tree_changed": False,
        },
    }
    write_json(output_dir / "CorrectionManifest_Stepped_Cylinder_v2.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Correct Stepped Cylinder cylinder fitting and candidates.")
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--face-template", required=True, type=Path)
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--candidate-template", required=True, type=Path)
    parser.add_argument("--csg", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--surface-mapping", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--status", choices=("PENDING", "PASS"), default="PENDING")
    arguments = parser.parse_args()
    for attribute in (
        "result",
        "face_template",
        "topology",
        "candidate_template",
        "csg",
        "truth",
        "surface_mapping",
        "output_dir",
    ):
        setattr(arguments, attribute, getattr(arguments, attribute).resolve())
    build_outputs(arguments)


if __name__ == "__main__":
    main()
