from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


DISTANCE_THRESHOLD_MM = 2.0
NORMAL_THRESHOLD = 0.93
FIT_RESIDUAL_THRESHOLD_MM = 1.5
ORTHOGONAL_DOT_THRESHOLD = 0.2
ENDCAP_DISTANCE_THRESHOLD_MM = 5.0
ENDCAP_DOT_THRESHOLD = 0.95


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            formatted: dict[str, Any] = {}
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, (float, np.floating)):
                    formatted[field] = "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
                else:
                    formatted[field] = value
            writer.writerow(formatted)


def write_result_preserving_values(source: Path, target: Path, cluster_ids: np.ndarray) -> None:
    with source.open("r", encoding="utf-8-sig", newline="") as input_stream:
        reader = csv.DictReader(input_stream)
        fields = list(reader.fieldnames or [])
        if "ClusterID" not in fields:
            raise ValueError("原始 Result 缺少 ClusterID。")
        rows = list(reader)
    if len(rows) != len(cluster_ids):
        raise ValueError("原始 Result 列數與推論標籤數不一致。")
    with target.open("w", encoding="utf-8", newline="") as output_stream:
        writer = csv.DictWriter(output_stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row, cluster_id in zip(rows, cluster_ids):
            row["ClusterID"] = str(int(cluster_id))
            writer.writerow(row)


def canonical_direction(vector: np.ndarray) -> np.ndarray:
    direction = np.asarray(vector, dtype=float)
    direction /= max(float(np.linalg.norm(direction)), 1e-12)
    dominant = int(np.argmax(np.abs(direction)))
    if direction[dominant] < 0:
        direction = -direction
    return direction


def radial_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    candidates = np.eye(3)
    seed = candidates[int(np.argmin(np.abs(candidates @ axis)))]
    first = np.cross(axis, seed)
    first /= max(float(np.linalg.norm(first)), 1e-12)
    second = np.cross(axis, first)
    second /= max(float(np.linalg.norm(second)), 1e-12)
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
        jacobian = np.column_stack((-delta_x / distance, -delta_y / distance, -np.ones(len(values))))
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
    normal /= max(float(np.linalg.norm(normal)), 1e-12)
    residual = np.abs((points - center) @ normal)
    alignment = np.abs(normals @ normal)
    return {
        "geometry": "plane",
        "center": center,
        "normal": normal,
        "axis": np.full(3, math.nan),
        "radius": math.nan,
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
        "normal": np.full(3, math.nan),
        "axis": axis,
        "radius": radius,
        "axis_min": float(axis_values.min()),
        "axis_max": float(axis_values.max()),
        "residual": np.abs(signed_residual),
        "alignment": alignment,
        "iterations": iterations,
    }


def model_passes(model: dict[str, Any]) -> bool:
    return (
        float(np.max(model["residual"])) <= FIT_RESIDUAL_THRESHOLD_MM
        and float(np.min(model["alignment"])) >= NORMAL_THRESHOLD
    )


def fit_single_surface(points: np.ndarray, normals: np.ndarray) -> dict[str, Any] | None:
    if len(points) >= 3:
        plane = fit_plane(points, normals)
        if model_passes(plane):
            return plane
    if len(points) >= 6:
        cylinder = fit_cylinder(points, normals)
        if model_passes(cylinder):
            return cylinder
    return None


def point_model_score(
    point: np.ndarray,
    normal: np.ndarray,
    model: dict[str, Any],
    support_points: np.ndarray,
) -> tuple[float, float] | None:
    support_min = support_points.min(axis=0) - DISTANCE_THRESHOLD_MM
    support_max = support_points.max(axis=0) + DISTANCE_THRESHOLD_MM
    if model["geometry"] == "plane":
        fitted_normal = np.asarray(model["normal"])
        residual = abs(float((point - np.asarray(model["center"])) @ fitted_normal))
        alignment = abs(float(normal @ fitted_normal))
        dominant = int(np.argmax(np.abs(fitted_normal)))
        support_axes = [value for value in range(3) if value != dominant]
        support_pass = bool(
            np.all(point[support_axes] >= support_min[support_axes])
            and np.all(point[support_axes] <= support_max[support_axes])
        )
    else:
        axis = np.asarray(model["axis"])
        delta = point - np.asarray(model["center"])
        radial = delta - axis * float(delta @ axis)
        radial_length = float(np.linalg.norm(radial))
        radial_unit = radial / max(radial_length, 1e-12)
        residual = abs(radial_length - float(model["radius"]))
        alignment = abs(float(normal @ radial_unit))
        axis_value = float(point @ axis)
        support_pass = (
            float(model["axis_min"]) - DISTANCE_THRESHOLD_MM
            <= axis_value
            <= float(model["axis_max"]) + DISTANCE_THRESHOLD_MM
        )
    if residual > FIT_RESIDUAL_THRESHOLD_MM or alignment < NORMAL_THRESHOLD or not support_pass:
        return None
    return residual + (1.0 - alignment), residual


def infer_surfaces(
    points: np.ndarray,
    normals: np.ndarray,
    original_clusters: np.ndarray,
) -> tuple[list[dict[str, Any]], np.ndarray, list[dict[str, Any]]]:
    seed_models: dict[int, dict[str, Any]] = {}
    seed_indices: dict[int, list[int]] = {}
    rejected_indices: list[int] = []
    initial_audit: list[dict[str, Any]] = []

    for cluster_id in sorted(set(int(value) for value in original_clusters)):
        indices = np.flatnonzero(original_clusters == cluster_id)
        model = fit_single_surface(points[indices], normals[indices])
        initial_audit.append(
            {
                "OriginalClusterID": cluster_id,
                "OriginalPointCount": len(indices),
                "SeedAccepted": model is not None,
                "SeedGeometry": model["geometry"] if model is not None else "mixed_or_unresolved",
            }
        )
        if model is None:
            rejected_indices.extend(int(value) for value in indices)
        else:
            seed_models[cluster_id] = model
            seed_indices[cluster_id] = [int(value) for value in indices]

    if not seed_models:
        raise ValueError("沒有任何原始群集可通過第三章曲面驗收。")

    for point_index in sorted(rejected_indices):
        candidates: list[tuple[float, float, int]] = []
        for cluster_id in sorted(seed_models):
            indices = np.asarray(seed_indices[cluster_id], dtype=int)
            score = point_model_score(
                points[point_index], normals[point_index], seed_models[cluster_id], points[indices]
            )
            if score is not None:
                candidates.append((score[0], score[1], cluster_id))
        if candidates:
            seed_indices[min(candidates)[2]].append(point_index)

    surface_records: list[dict[str, Any]] = []
    new_clusters = np.full(len(points), -1, dtype=int)
    for cluster_id in sorted(seed_indices):
        indices = np.asarray(sorted(seed_indices[cluster_id]), dtype=int)
        model = fit_single_surface(points[indices], normals[indices])
        if model is None:
            raise ValueError(f"重新歸屬後 Cluster {cluster_id} 無法通過單一曲面驗收。")
        new_clusters[indices] = cluster_id
        surface_records.append({"cluster_id": cluster_id, "indices": indices, "model": model})

    return surface_records, new_clusters, initial_audit


def cylinder_surface_sense(model: dict[str, Any], points: np.ndarray, normals: np.ndarray) -> float:
    axis = np.asarray(model["axis"])
    delta = points - np.asarray(model["center"])
    radial = delta - np.outer(delta @ axis, axis)
    radial_unit = radial / np.maximum(np.linalg.norm(radial, axis=1)[:, None], 1e-12)
    return float(np.median(np.sum(normals * radial_unit, axis=1)))


FEATURE_NAMES = {
    "through_hole_side": "Cylinder_axisZ_inner (貫穿孔)",
    "lower_outer_side": "Cylinder_axisZ_outer (下階外圓柱)",
    "bottom_annulus": "Plane_Horizontal (底面環)",
    "shoulder_annulus": "Plane_Horizontal (階梯肩面)",
    "top_annulus": "Plane_Horizontal (頂面環)",
    "upper_outer_side": "Cylinder_axisZ_outer (上階外圓柱)",
}


def assign_semantic_roles(surface_records: list[dict[str, Any]], points: np.ndarray, normals: np.ndarray) -> None:
    planes = [value for value in surface_records if value["model"]["geometry"] == "plane"]
    cylinders = [value for value in surface_records if value["model"]["geometry"] == "cylinder"]
    if len(planes) != 3 or len(cylinders) != 3:
        raise ValueError(f"階梯狀圓柱應由三個平面與三個圓柱面構成，實際為 {len(planes)} 與 {len(cylinders)}。")

    common_axis = canonical_direction(np.mean([np.asarray(value["model"]["axis"]) for value in cylinders], axis=0))
    ordered_planes = sorted(planes, key=lambda value: float(np.asarray(value["model"]["center"]) @ common_axis))
    for surface, role in zip(ordered_planes, ["bottom_annulus", "shoulder_annulus", "top_annulus"]):
        surface["semantic_role"] = role

    inner: list[dict[str, Any]] = []
    outer: list[dict[str, Any]] = []
    for surface in cylinders:
        indices = surface["indices"]
        sense = cylinder_surface_sense(surface["model"], points[indices], normals[indices])
        surface["surface_sense"] = sense
        (inner if sense < 0 else outer).append(surface)
    if len(inner) != 1 or len(outer) != 2:
        raise ValueError("圓柱內外方向無法由法向量徑向符號唯一判定。")
    inner[0]["semantic_role"] = "through_hole_side"
    for surface, role in zip(
        sorted(outer, key=lambda value: float(np.asarray(value["model"]["center"]) @ common_axis)),
        ["lower_outer_side", "upper_outer_side"],
    ):
        surface["semantic_role"] = role


def min_distance(first: np.ndarray, second: np.ndarray) -> float:
    if len(first) > len(second):
        first, second = second, first
    return float(np.min(cKDTree(second).query(first, k=1)[0]))


def build_topology(surface_records: list[dict[str, Any]], points: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position, first in enumerate(surface_records):
        for second in surface_records[position + 1 :]:
            first_points = points[first["indices"]]
            second_points = points[second["indices"]]
            distance = min_distance(first_points, second_points)
            first_geometry = first["model"]["geometry"]
            second_geometry = second["model"]["geometry"]
            edge_type: str | None = None
            direction_dot = math.nan
            direction_rule = ""
            if {first_geometry, second_geometry} == {"plane", "cylinder"}:
                plane = first if first_geometry == "plane" else second
                cylinder = first if first_geometry == "cylinder" else second
                direction_dot = abs(
                    float(np.asarray(plane["model"]["normal"]) @ np.asarray(cylinder["model"]["axis"]))
                )
                if distance <= ENDCAP_DISTANCE_THRESHOLD_MM and direction_dot > ENDCAP_DOT_THRESHOLD:
                    edge_type = "EndCap"
                    direction_rule = "finite-range contact; |axis·normal|>0.95"
                elif distance <= DISTANCE_THRESHOLD_MM:
                    edge_type = "Adjacency"
                    direction_rule = "finite-range contact"
            elif first_geometry == second_geometry == "plane":
                direction_dot = abs(
                    float(np.asarray(first["model"]["normal"]) @ np.asarray(second["model"]["normal"]))
                )
                if distance <= DISTANCE_THRESHOLD_MM:
                    if direction_dot < ORTHOGONAL_DOT_THRESHOLD:
                        edge_type = "OrthogonalAdjacency"
                        direction_rule = "finite-range contact; |normal·normal|<0.2"
                    else:
                        edge_type = "Adjacency"
                        direction_rule = "finite-range contact"
            elif distance <= DISTANCE_THRESHOLD_MM:
                edge_type = "Adjacency"
                direction_rule = "finite-range contact"

            if edge_type is not None:
                first_id = min(int(first["cluster_id"]), int(second["cluster_id"]))
                second_id = max(int(first["cluster_id"]), int(second["cluster_id"]))
                rows.append(
                    {
                        "FromClusterID": first_id,
                        "ToClusterID": second_id,
                        "EdgeType": edge_type,
                        "MinDistance": distance,
                        "DirectionDot": direction_dot,
                        "DistanceThreshold": ENDCAP_DISTANCE_THRESHOLD_MM if edge_type == "EndCap" else DISTANCE_THRESHOLD_MM,
                        "DirectionThreshold": (
                            ENDCAP_DOT_THRESHOLD
                            if edge_type == "EndCap"
                            else ORTHOGONAL_DOT_THRESHOLD if edge_type == "OrthogonalAdjacency" else math.nan
                        ),
                        "RuleStatus": "PASS",
                        "InferenceRule": direction_rule,
                    }
                )
    return sorted(rows, key=lambda value: (value["FromClusterID"], value["ToClusterID"], value["EdgeType"]))


def build_candidates(
    surface_records: list[dict[str, Any]], topology_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_cluster = {int(value["cluster_id"]): value for value in surface_records}
    cylinders = [value for value in surface_records if value["model"]["geometry"] == "cylinder"]
    endcaps: dict[int, list[int]] = defaultdict(list)
    for edge in topology_rows:
        if edge["EdgeType"] != "EndCap":
            continue
        first_id, second_id = int(edge["FromClusterID"]), int(edge["ToClusterID"])
        if by_cluster[first_id]["model"]["geometry"] == "cylinder":
            endcaps[first_id].append(second_id)
        elif by_cluster[second_id]["model"]["geometry"] == "cylinder":
            endcaps[second_id].append(first_id)

    specifications = {
        "lower_outer_side": ("SC_U01", "CylinderLower", "Union"),
        "upper_outer_side": ("SC_U02", "CylinderUpper", "Union"),
        "through_hole_side": ("SC_D01", "ThroughHole", "Difference"),
    }
    rows: list[dict[str, Any]] = []
    for surface in cylinders:
        role = str(surface["semantic_role"])
        candidate_id, primitive_type, boolean_type = specifications[role]
        cylinder_id = int(surface["cluster_id"])
        cap_ids = sorted(endcaps.get(cylinder_id, []))
        if len(cap_ids) != 2:
            raise ValueError(f"{role} 未由兩個 EndCap 關係封閉：{cap_ids}")
        axis = np.asarray(surface["model"]["axis"])
        cap_coordinates = sorted(
            float(np.asarray(by_cluster[cap_id]["model"]["center"]) @ axis) for cap_id in cap_ids
        )
        rows.append(
            {
                "CandidateID": candidate_id,
                "PrimitiveType": primitive_type,
                "RelatedClusters": ";".join(str(value) for value in sorted([cylinder_id, *cap_ids])),
                "Length": math.nan,
                "Width": math.nan,
                "Height": math.nan,
                "Radius": float(surface["model"]["radius"]),
                "Depth": cap_coordinates[1] - cap_coordinates[0],
                "BooleanType": boolean_type,
                "InferenceRule": "cylinder side + two EndCap relations + radial normal sense",
                "RuleStatus": "PASS",
            }
        )
    return sorted(rows, key=lambda value: value["CandidateID"])


def canonical_csg_tree(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    union = sorted(value["CandidateID"] for value in candidates if value["BooleanType"] == "Union")
    difference = sorted(value["CandidateID"] for value in candidates if value["BooleanType"] == "Difference")
    return {
        "op": "Difference",
        "base": {"op": "Union", "children": [{"candidate": value} for value in union]},
        "subtractors": [{"candidate": value} for value in difference],
    }


def build_outputs(source: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source)
    required = ["X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"]
    missing = [value for value in required if value not in frame.columns]
    if missing or len(frame) != 10000:
        raise ValueError(f"階梯狀圓柱輸入不符合第三章資料結構：missing={missing}, rows={len(frame)}")

    points = frame[["X", "Y", "Z"]].to_numpy(float)
    normals = frame[["NX", "NY", "NZ"]].to_numpy(float)
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    original_clusters = frame["ClusterID"].to_numpy(int)

    surfaces, new_clusters, initial_audit = infer_surfaces(points, normals, original_clusters)
    assign_semantic_roles(surfaces, points, normals)
    if int(np.sum(new_clusters >= 0)) + int(np.sum(new_clusters < 0)) != len(frame):
        raise ValueError("點數守恆失敗。")

    result_path = output_dir / "Result_Stepped_Cylinder_chapter3_verified.csv"
    write_result_preserving_values(source, result_path, new_clusters)

    face_rows: list[dict[str, Any]] = []
    for surface in sorted(surfaces, key=lambda value: int(value["cluster_id"])):
        indices = surface["indices"]
        model = surface["model"]
        center = np.asarray(model["center"])
        normal = np.asarray(model["normal"])
        axis = np.asarray(model["axis"])
        cluster_points = points[indices]
        face_rows.append(
            {
                "ClusterID": int(surface["cluster_id"]),
                "FeatureType": FEATURE_NAMES[str(surface["semantic_role"])],
                "SemanticRole": str(surface["semantic_role"]),
                "PointCount": len(indices),
                "FittedPatchCount": 1,
                "CenterX": center[0], "CenterY": center[1], "CenterZ": center[2],
                "NX": normal[0], "NY": normal[1], "NZ": normal[2],
                "AxisX": axis[0], "AxisY": axis[1], "AxisZ": axis[2],
                "MinX": cluster_points[:, 0].min(), "MaxX": cluster_points[:, 0].max(),
                "MinY": cluster_points[:, 1].min(), "MaxY": cluster_points[:, 1].max(),
                "MinZ": cluster_points[:, 2].min(), "MaxZ": cluster_points[:, 2].max(),
                "Radius": float(model["radius"]),
                "AxisMin": float(model["axis_min"]), "AxisMax": float(model["axis_max"]),
                "SurfaceSense": float(surface.get("surface_sense", math.nan)),
                "FitResidualMax": float(np.max(model["residual"])),
                "FitResidualMedian": float(np.median(model["residual"])),
                "NormalConsistencyMin": float(np.min(model["alignment"])),
                "ValidationStatus": "PASS",
            }
        )
    face_path = output_dir / "FaceSummary_Stepped_Cylinder_chapter3_verified.csv"
    face_fields = [
        "ClusterID", "FeatureType", "SemanticRole", "PointCount", "FittedPatchCount",
        "CenterX", "CenterY", "CenterZ", "NX", "NY", "NZ", "AxisX", "AxisY", "AxisZ",
        "MinX", "MaxX", "MinY", "MaxY", "MinZ", "MaxZ", "Radius", "AxisMin", "AxisMax",
        "SurfaceSense", "FitResidualMax", "FitResidualMedian", "NormalConsistencyMin", "ValidationStatus",
    ]
    write_csv(face_path, face_rows, face_fields)

    topology_rows = build_topology(surfaces, points)
    topology_path = output_dir / "TopologyEdges_Stepped_Cylinder_chapter3_verified.csv"
    topology_fields = [
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "DistanceThreshold", "DirectionThreshold", "RuleStatus", "InferenceRule",
    ]
    write_csv(topology_path, topology_rows, topology_fields)

    candidate_rows = build_candidates(surfaces, topology_rows)
    candidate_path = output_dir / "PrimitiveCandidates_Stepped_Cylinder_chapter3_verified.csv"
    candidate_fields = [
        "CandidateID", "PrimitiveType", "RelatedClusters", "Length", "Width", "Height",
        "Radius", "Depth", "BooleanType", "InferenceRule", "RuleStatus",
    ]
    write_csv(candidate_path, candidate_rows, candidate_fields)

    csg_path = output_dir / "CSGTree_Stepped_Cylinder_chapter3_verified.json"
    write_json(
        csg_path,
        {
            "case": "Stepped Cylinder",
            "source": candidate_path.name,
            "canonicalization": "Union children sorted by CandidateID; Difference subtractors sorted by CandidateID",
            "tree": canonical_csg_tree(candidate_rows),
        },
    )

    trace_rows: list[dict[str, Any]] = []
    for original_cluster in sorted(set(int(value) for value in original_clusters)):
        original_mask = original_clusters == original_cluster
        for verified_cluster in sorted(set(int(value) for value in new_clusters[original_mask])):
            trace_rows.append(
                {
                    "OriginalClusterID": original_cluster,
                    "VerifiedClusterID": verified_cluster,
                    "PointCount": int(np.sum(original_mask & (new_clusters == verified_cluster))),
                    "Action": (
                        "保留"
                        if original_cluster == verified_cluster
                        else "列為殘留" if verified_cluster < 0 else "依第三章規則重新歸屬"
                    ),
                    "Reason": (
                        "原群集通過單一平面或圓柱面型驗收"
                        if original_cluster == verified_cluster
                        else "原群集未通過單一曲面驗收；依1.5 mm殘差、0.93法向量一致性與有限範圍選擇最佳曲面"
                    ),
                }
            )
    trace_path = output_dir / "CorrectionTrace_Stepped_Cylinder_chapter3.csv"
    write_csv(
        trace_path,
        trace_rows,
        ["OriginalClusterID", "VerifiedClusterID", "PointCount", "Action", "Reason"],
    )

    outputs = [result_path, face_path, topology_path, candidate_path, csg_path, trace_path]
    manifest_path = output_dir / "MethodInferenceManifest_Stepped_Cylinder_chapter3.json"
    write_json(
        manifest_path,
        {
            "schema_version": "3.0",
            "case": "Stepped Cylinder",
            "method_basis": "Chapter 3 formulas (3-3) through (3-7)",
            "inputs_read": {"result": {"filename": source.name, "sha256": sha256(source)}},
            "forbidden_inputs_read": [],
            "truth_or_mesh_used_for_inference": False,
            "parameters": {
                "DistanceThreshold": DISTANCE_THRESHOLD_MM,
                "NormalThreshold": NORMAL_THRESHOLD,
                "FitResidualThreshold": FIT_RESIDUAL_THRESHOLD_MM,
                "TopologyEpsilon": DISTANCE_THRESHOLD_MM,
                "OrthogonalDotThreshold": ORTHOGONAL_DOT_THRESHOLD,
                "EndCapDistanceThreshold": ENDCAP_DISTANCE_THRESHOLD_MM,
                "EndCapDotThreshold": ENDCAP_DOT_THRESHOLD,
            },
            "inference_rules": {
                "seed_acceptance": "an original cluster must pass exactly one accepted plane/cylinder fit; plane is tested before cylinder",
                "reassignment": "best finite-support surface satisfying residual <= 1.5 mm and normal agreement >= 0.93",
                "semantics": "plane axial order; cylinder radial-normal sense; outer-cylinder axial order",
                "topology": "finite sampled support distance plus the Chapter 3 direction predicates",
                "candidates": "one cylindrical side plus exactly two EndCap relations",
                "csg": "Union additive candidates first, then ordered Difference subtractors",
            },
            "initial_cluster_audit": initial_audit,
            "counts": {
                "points": len(frame),
                "original_clusters": len(set(original_clusters.tolist())),
                "accepted_faces": len(surfaces),
                "accepted_points": int(np.sum(new_clusters >= 0)),
                "residual_points": int(np.sum(new_clusters < 0)),
                "topology_edges": len(topology_rows),
                "primitive_candidates": len(candidate_rows),
            },
            "program": {"filename": Path(__file__).name, "sha256": sha256(Path(__file__))},
            "outputs": {path.name: sha256(path) for path in outputs},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer Stepped Cylinder only from the original Result CSV and the public Chapter 3 rules."
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    build_outputs(arguments.result.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
