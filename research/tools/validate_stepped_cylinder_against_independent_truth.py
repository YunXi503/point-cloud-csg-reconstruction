from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


POINT_COUNT = 10000
DISTANCE_THRESHOLD_MM = 2.0
NORMAL_THRESHOLD = 0.93
FIT_RESIDUAL_THRESHOLD_MM = 1.5
ENDCAP_DOT_THRESHOLD = 0.95
ORTHOGONAL_DOT_THRESHOLD = 0.2
NUMERIC_OUTPUT_TOLERANCE_MM = 1e-6
SERIALIZATION_EQUIVALENCE_TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def radial_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    candidates = np.eye(3)
    seed = candidates[int(np.argmin(np.abs(candidates @ axis)))]
    first = np.cross(axis, seed)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    second /= np.linalg.norm(second)
    return first, second


def surface_metrics(
    points: np.ndarray, normals: np.ndarray, surface: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if surface["geometry"] == "plane":
        plane_normal = np.asarray(surface["normal"], dtype=float)
        residual = np.abs(points @ plane_normal - float(surface["plane_offset_mm"]))
        alignment = np.abs(normals @ plane_normal)
        inside = np.ones(len(points), dtype=bool)
        return residual, alignment, inside

    axis = np.asarray(surface["axis"], dtype=float)
    line_point = np.asarray(surface["axis_line_midpoint"], dtype=float)
    delta = points - line_point
    radial = delta - np.outer(delta @ axis, axis)
    radial_length = np.linalg.norm(radial, axis=1)
    radial_unit = radial / np.maximum(radial_length[:, None], 1e-12)
    residual = np.abs(radial_length - float(surface["radius_mm"]))
    alignment = np.abs(np.sum(normals * radial_unit, axis=1))
    axis_values = points @ axis
    inside = (
        (axis_values >= float(surface["axis_min_mm"]) - DISTANCE_THRESHOLD_MM)
        & (axis_values <= float(surface["axis_max_mm"]) + DISTANCE_THRESHOLD_MM)
    )
    return residual, alignment, inside


def classify_points(
    points: np.ndarray, normals: np.ndarray, surfaces: list[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scores = np.full((len(points), len(surfaces)), np.inf, dtype=float)
    residuals = np.full_like(scores, np.inf)
    alignments = np.zeros_like(scores)
    for surface_index, surface in enumerate(surfaces):
        residual, alignment, inside = surface_metrics(points, normals, surface)
        accepted = (
            (residual <= FIT_RESIDUAL_THRESHOLD_MM)
            & (alignment >= NORMAL_THRESHOLD)
            & inside
        )
        score = residual / FIT_RESIDUAL_THRESHOLD_MM
        score += (1.0 - alignment) / max(1.0 - NORMAL_THRESHOLD, 1e-12)
        scores[accepted, surface_index] = score[accepted]
        residuals[:, surface_index] = residual
        alignments[:, surface_index] = alignment
    best = np.argmin(scores, axis=1)
    valid = np.isfinite(scores[np.arange(len(points)), best])
    labels = np.full(len(points), -1, dtype=int)
    labels[valid] = best[valid]
    chosen_residual = np.full(len(points), math.inf, dtype=float)
    chosen_alignment = np.zeros(len(points), dtype=float)
    chosen_residual[valid] = residuals[np.arange(len(points))[valid], best[valid]]
    chosen_alignment[valid] = alignments[np.arange(len(points))[valid], best[valid]]
    return labels, chosen_residual, chosen_alignment


def fit_plane_nls(points: np.ndarray, normals: np.ndarray) -> dict[str, Any]:
    center = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1]
    if float(normal @ normals.mean(axis=0)) < 0.0:
        normal = -normal
    normal /= np.linalg.norm(normal)
    residual = np.abs((points - center) @ normal)
    alignment = np.abs(normals @ normal)
    return {
        "geometry": "plane",
        "center": center,
        "normal": normal,
        "residual": residual,
        "alignment": alignment,
        "rmse_mm": float(np.sqrt(np.mean(residual * residual))),
    }


def algebraic_circle_fit(values: np.ndarray) -> tuple[float, float, float]:
    x, y = values[:, 0], values[:, 1]
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(values))))
    rhs = x * x + y * y
    center_x, center_y, constant = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    radius = math.sqrt(max(float(constant + center_x * center_x + center_y * center_y), 0.0))
    return float(center_x), float(center_y), radius


def geometric_circle_fit(values: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    center_x, center_y, radius = algebraic_circle_fit(values)
    for _ in range(100):
        delta_x = values[:, 0] - center_x
        delta_y = values[:, 1] - center_y
        distance = np.maximum(np.hypot(delta_x, delta_y), 1e-12)
        residual = distance - radius
        jacobian = np.column_stack((-delta_x / distance, -delta_y / distance, -np.ones(len(values))))
        step = np.linalg.lstsq(jacobian, -residual, rcond=None)[0]
        center_x += float(step[0])
        center_y += float(step[1])
        radius += float(step[2])
        if float(np.linalg.norm(step)) <= 1e-13:
            break
    residual = np.hypot(values[:, 0] - center_x, values[:, 1] - center_y) - radius
    return center_x, center_y, radius, residual


def fit_cylinder_nls(
    points: np.ndarray, normals: np.ndarray, truth_surface: dict[str, Any]
) -> dict[str, Any]:
    axis = np.asarray(truth_surface["axis"], dtype=float)
    first, second = radial_basis(axis)
    values = np.column_stack((points @ first, points @ second))
    center_first, center_second, radius, signed_residual = geometric_circle_fit(values)
    axis_values = points @ axis
    center = first * center_first + second * center_second + axis * float(axis_values.mean())
    radial = points - center
    radial -= np.outer(radial @ axis, axis)
    radial_length = np.linalg.norm(radial, axis=1)
    radial_unit = radial / np.maximum(radial_length[:, None], 1e-12)
    alignment = np.abs(np.sum(normals * radial_unit, axis=1))
    residual = np.abs(signed_residual)
    return {
        "geometry": "cylinder",
        "center": center,
        "axis": axis,
        "radius_mm": radius,
        "axis_min_mm": float(axis_values.min()),
        "axis_max_mm": float(axis_values.max()),
        "residual": residual,
        "alignment": alignment,
        "rmse_mm": float(np.sqrt(np.mean(signed_residual * signed_residual))),
    }


def reported_cylinder_rmse(
    points: np.ndarray, face_row: pd.Series, truth_surface: dict[str, Any]
) -> float:
    axis = np.asarray(
        [float(face_row["AxisX"]), float(face_row["AxisY"]), float(face_row["AxisZ"])],
        dtype=float,
    )
    if np.linalg.norm(axis) <= 1e-12:
        axis = np.asarray(truth_surface["axis"], dtype=float)
    axis /= np.linalg.norm(axis)
    center = np.asarray(
        [float(face_row["CenterX"]), float(face_row["CenterY"]), float(face_row["CenterZ"])],
        dtype=float,
    )
    delta = points - center
    radial = delta - np.outer(delta @ axis, axis)
    signed_residual = np.linalg.norm(radial, axis=1) - float(face_row["Radius"])
    return float(np.sqrt(np.mean(signed_residual * signed_residual)))


def parse_related_clusters(value: Any) -> list[int]:
    return sorted(int(part.strip()) for part in str(value).split(";") if part.strip())


def normalized_tree(node: dict[str, Any], candidate_map: dict[str, str]) -> dict[str, Any]:
    if "candidate" in node:
        candidate = str(node["candidate"])
        return {"candidate": candidate_map.get(candidate, candidate)}
    operation = node.get("op")
    if operation == "Union":
        children = [normalized_tree(child, candidate_map) for child in node.get("children", [])]
        children.sort(key=lambda child: json.dumps(child, sort_keys=True))
        return {"op": "Union", "children": children}
    if operation == "Difference":
        base = normalized_tree(node["base"], candidate_map)
        raw_subtractors = node.get("subtractors")
        if raw_subtractors is None:
            raw_subtractors = [node["subtract"]]
        subtractors = [normalized_tree(child, candidate_map) for child in raw_subtractors]
        subtractors.sort(key=lambda child: json.dumps(child, sort_keys=True))
        return {"op": "Difference", "base": base, "subtractors": subtractors}
    raise ValueError(f"未知 CSG 節點：{node}")


def validate(arguments: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    truth = load_json(arguments.truth)
    surfaces = truth["surfaces"]
    truth_index_to_id = {index: surface["surface_id"] for index, surface in enumerate(surfaces)}
    truth_by_id = {surface["surface_id"]: surface for surface in surfaces}

    point_cloud = pd.read_csv(arguments.point_cloud)
    original_result = pd.read_csv(arguments.original_result)
    verified_result = pd.read_csv(arguments.verified_result)
    coordinate_columns = ["X", "Y", "Z", "NX", "NY", "NZ"]
    for name, data in (
        ("point cloud", point_cloud),
        ("original Result", original_result),
        ("verified Result", verified_result),
    ):
        missing = set(coordinate_columns) - set(data.columns)
        if missing:
            raise ValueError(f"{name} 缺少欄位：{sorted(missing)}")
    if "ClusterID" not in verified_result.columns:
        raise ValueError("驗證版 Result 缺少 ClusterID。")

    points = verified_result[["X", "Y", "Z"]].to_numpy(dtype=float)
    normals = verified_result[["NX", "NY", "NZ"]].to_numpy(dtype=float)
    cluster_ids = verified_result["ClusterID"].to_numpy(dtype=int)
    labels, truth_residual, truth_alignment = classify_points(points, normals, surfaces)

    point_vs_verified_max_difference = float(
        np.max(
            np.abs(
                point_cloud[coordinate_columns].to_numpy(dtype=float)
                - verified_result[coordinate_columns].to_numpy(dtype=float)
            )
        )
    )
    original_result_vs_verified_max_difference = float(
        np.max(
            np.abs(
                original_result[coordinate_columns].to_numpy(dtype=float)
                - verified_result[coordinate_columns].to_numpy(dtype=float)
            )
        )
    )

    face_summary = pd.read_csv(arguments.face_summary)
    face_by_cluster = {int(row["ClusterID"]): row for _, row in face_summary.iterrows()}
    valid_cluster_values = sorted(int(value) for value in set(cluster_ids) if int(value) >= 0)
    cluster_to_truth: dict[int, str] = {}
    surface_mapping_rows: list[dict[str, Any]] = []
    independent_fits: dict[str, dict[str, Any]] = {}
    segmentation_checks: list[bool] = []
    geometry_checks: list[bool] = []

    for cluster_id in valid_cluster_values:
        mask = cluster_ids == cluster_id
        cluster_labels = labels[mask]
        accepted_labels = cluster_labels[cluster_labels >= 0]
        if len(accepted_labels):
            values, counts = np.unique(accepted_labels, return_counts=True)
            dominant_index = int(values[int(np.argmax(counts))])
            dominant_count = int(counts.max())
            truth_id = truth_index_to_id[dominant_index]
        else:
            dominant_index, dominant_count, truth_id = -1, 0, "UNMATCHED"
        unmatched_count = int(np.sum(cluster_labels < 0))
        minority_count = int(len(cluster_labels) - dominant_count - unmatched_count)
        cluster_to_truth[cluster_id] = truth_id
        truth_surface = truth_by_id.get(truth_id)
        face_row = face_by_cluster.get(cluster_id)

        single_surface = truth_surface is not None and minority_count == 0 and unmatched_count == 0
        segmentation_checks.append(single_surface)
        geometry_status = False
        reported_feature_type = "MISSING"
        fit_radius = math.nan
        fit_center = np.full(3, math.nan, dtype=float)
        reported_radius = math.nan
        radius_difference = math.nan
        stl_truth_radius = math.nan
        independent_radius_error_from_stl = math.nan
        reported_radius_error_from_stl = math.nan
        optimal_rmse = math.nan
        reported_rmse = math.nan
        fit_residual_max = math.inf
        normal_consistency_min = 0.0
        semantic_match = False
        mesh_component_match = False
        point_count_match = False
        axis_or_normal_match = False
        numeric_fit_match = False

        if single_surface and truth_surface is not None:
            cluster_points, cluster_normals = points[mask], normals[mask]
            if truth_surface["geometry"] == "plane":
                fit = fit_plane_nls(cluster_points, cluster_normals)
            else:
                fit = fit_cylinder_nls(cluster_points, cluster_normals, truth_surface)
            independent_fits[truth_id] = fit
            fit_center = np.asarray(fit["center"], dtype=float)
            fit_residual_max = float(np.max(fit["residual"]))
            normal_consistency_min = float(np.min(fit["alignment"]))
            optimal_rmse = float(fit["rmse_mm"])

            if face_row is not None:
                reported_feature_type = str(face_row["FeatureType"])
                semantic_match = reported_feature_type == str(truth_surface["feature_type"])
                point_count_match = int(face_row["PointCount"]) == int(mask.sum())
                mesh_component_match = int(face_row.get("MeshConnectedComponents", 1)) == int(
                    truth_surface["mesh_connected_components"]
                )
                if truth_surface["geometry"] == "plane":
                    reported_normal = np.asarray(
                        [float(face_row["NX"]), float(face_row["NY"]), float(face_row["NZ"])],
                        dtype=float,
                    )
                    reported_normal /= max(float(np.linalg.norm(reported_normal)), 1e-12)
                    axis_or_normal_match = abs(
                        float(reported_normal @ np.asarray(truth_surface["normal"], dtype=float))
                    ) >= NORMAL_THRESHOLD
                    reported_center = np.asarray(
                        [float(face_row["CenterX"]), float(face_row["CenterY"]), float(face_row["CenterZ"])],
                        dtype=float,
                    )
                    offset_error = abs(
                        float(reported_center @ np.asarray(truth_surface["normal"], dtype=float))
                        - float(truth_surface["plane_offset_mm"])
                    )
                    numeric_fit_match = offset_error <= NUMERIC_OUTPUT_TOLERANCE_MM
                    reported_rmse = float(face_row.get("FitResidualMedian", 0.0))
                else:
                    fit_radius = float(fit["radius_mm"])
                    stl_truth_radius = float(truth_surface["radius_mm"])
                    reported_radius = float(face_row["Radius"])
                    radius_difference = abs(reported_radius - fit_radius)
                    independent_radius_error_from_stl = abs(fit_radius - stl_truth_radius)
                    reported_radius_error_from_stl = abs(reported_radius - stl_truth_radius)
                    reported_axis = np.asarray(
                        [float(face_row["AxisX"]), float(face_row["AxisY"]), float(face_row["AxisZ"])],
                        dtype=float,
                    )
                    reported_axis /= max(float(np.linalg.norm(reported_axis)), 1e-12)
                    axis_or_normal_match = abs(
                        float(reported_axis @ np.asarray(truth_surface["axis"], dtype=float))
                    ) >= ENDCAP_DOT_THRESHOLD
                    reported_rmse = reported_cylinder_rmse(cluster_points, face_row, truth_surface)
                    numeric_fit_match = (
                        radius_difference <= NUMERIC_OUTPUT_TOLERANCE_MM
                        and reported_rmse <= optimal_rmse + NUMERIC_OUTPUT_TOLERANCE_MM
                    )

                geometry_status = all(
                    (
                        semantic_match,
                        point_count_match,
                        mesh_component_match,
                        axis_or_normal_match,
                        numeric_fit_match,
                        fit_residual_max <= FIT_RESIDUAL_THRESHOLD_MM,
                        normal_consistency_min >= NORMAL_THRESHOLD,
                    )
                )
        geometry_checks.append(geometry_status)
        surface_mapping_rows.append(
            {
                "ClusterID": cluster_id,
                "TruthSurfaceID": truth_id,
                "SemanticRole": truth_surface["semantic_role"] if truth_surface else "UNMATCHED",
                "Geometry": truth_surface["geometry"] if truth_surface else "UNMATCHED",
                "PointCount": int(mask.sum()),
                "DominantTruthPointCount": dominant_count,
                "MinorityTruthPointCount": minority_count,
                "UnmatchedPointCount": unmatched_count,
                "TruthSurfaceConnectedComponents": truth_surface["mesh_connected_components"] if truth_surface else "",
                "IndependentFitResidualMaxMM": fit_residual_max,
                "IndependentNormalConsistencyMin": normal_consistency_min,
                "IndependentFitRadiusMM": fit_radius,
                "IndependentFitCenterX": float(fit_center[0]),
                "IndependentFitCenterY": float(fit_center[1]),
                "IndependentFitCenterZ": float(fit_center[2]),
                "ReportedRadiusMM": reported_radius,
                "RadiusDifferenceFromIndependentFitMM": radius_difference,
                "STLTruthRadiusMM": stl_truth_radius,
                "IndependentFitRadiusErrorFromSTLTruthMM": independent_radius_error_from_stl,
                "ReportedRadiusErrorFromSTLTruthMM": reported_radius_error_from_stl,
                "IndependentFitRMSEMM": optimal_rmse,
                "ReportedModelRMSEMM": reported_rmse,
                "ReportedFeatureType": reported_feature_type,
                "SemanticMatch": semantic_match,
                "PointCountMatch": point_count_match,
                "AxisOrNormalMatch": axis_or_normal_match,
                "NumericFitMatch": numeric_fit_match,
                "SegmentationStatus": "PASS" if single_surface else "FAIL",
                "GeometrySemanticsStatus": "PASS" if geometry_status else "FAIL",
            }
        )

    residual_count = int(np.sum(cluster_ids < 0))
    unmatched_valid_count = int(np.sum((cluster_ids >= 0) & (labels < 0)))
    represented_truth = [value for value in cluster_to_truth.values() if value != "UNMATCHED"]
    one_to_one = len(represented_truth) == len(set(represented_truth)) == len(surfaces)
    traceability_ok = len(verified_result) == POINT_COUNT and int(np.sum(cluster_ids >= 0)) + residual_count == POINT_COUNT
    input_unchanged = (
        original_result_vs_verified_max_difference == 0.0
        and point_vs_verified_max_difference <= SERIALIZATION_EQUIVALENCE_TOLERANCE
    )
    segmentation_pass = all(segmentation_checks) and one_to_one and traceability_ok and input_unchanged and unmatched_valid_count == 0
    geometry_pass = all(geometry_checks) and len(face_summary) == len(surfaces)

    truth_topology = {
        (edge["from_surface_id"], edge["to_surface_id"], edge["edge_type"])
        for edge in truth["topology_edges"]
    }
    topology_frame = pd.read_csv(arguments.topology)
    observed_topology: set[tuple[str, str, str]] = set()
    topology_unmapped_rows: list[int] = []
    allowed_types = {"Adjacency", "OrthogonalAdjacency", "EndCap"}
    topology_types_ok = True
    for row_index, row in topology_frame.iterrows():
        first_cluster, second_cluster = int(row["FromClusterID"]), int(row["ToClusterID"])
        first_truth, second_truth = cluster_to_truth.get(first_cluster), cluster_to_truth.get(second_cluster)
        edge_type = str(row["EdgeType"])
        topology_types_ok = topology_types_ok and edge_type in allowed_types
        if not first_truth or not second_truth or first_truth == "UNMATCHED" or second_truth == "UNMATCHED":
            topology_unmapped_rows.append(int(row_index))
            continue
        first_truth, second_truth = sorted((first_truth, second_truth))
        observed_topology.add((first_truth, second_truth, edge_type))
    missing_topology = sorted(truth_topology - observed_topology)
    extra_topology = sorted(observed_topology - truth_topology)
    topology_pass = (
        not missing_topology
        and not extra_topology
        and not topology_unmapped_rows
        and topology_types_ok
        and len(topology_frame) == len(truth_topology)
    )

    truth_candidates = truth["primitive_candidates"]
    candidate_frame = pd.read_csv(arguments.candidates)
    candidate_mapping_rows: list[dict[str, Any]] = []
    output_candidate_to_truth: dict[str, str] = {}
    candidate_checks: list[bool] = []
    for _, row in candidate_frame.iterrows():
        output_candidate_id = str(row["CandidateID"])
        related_clusters = parse_related_clusters(row["RelatedClusters"])
        related_truth = sorted(cluster_to_truth.get(cluster_id, "UNMATCHED") for cluster_id in related_clusters)
        matches = [
            candidate
            for candidate in truth_candidates
            if sorted(candidate["related_surface_ids"]) == related_truth
        ]
        truth_candidate = matches[0] if len(matches) == 1 else None
        if truth_candidate:
            truth_candidate_id = truth_candidate["candidate_id"]
            output_candidate_to_truth[output_candidate_id] = truth_candidate_id
            side_truth = truth_candidate["side_surface_id"]
            expected_radius = float(independent_fits[side_truth]["radius_mm"])
            stl_truth_radius = float(truth_candidate["radius_mm"])
            observed_radius = float(row["Radius"])
            radius_difference = abs(observed_radius - expected_radius)
            independent_radius_error_from_stl = abs(expected_radius - stl_truth_radius)
            reported_radius_error_from_stl = abs(observed_radius - stl_truth_radius)
            depth_difference = abs(float(row["Depth"]) - float(truth_candidate["depth_mm"]))
            type_match = str(row["PrimitiveType"]) == str(truth_candidate["primitive_type"])
            boolean_match = str(row["BooleanType"]) == str(truth_candidate["boolean_type"])
            dimension_match = (
                radius_difference <= NUMERIC_OUTPUT_TOLERANCE_MM
                and depth_difference <= float(truth_candidate["depth_comparison_tolerance_mm"])
            )
            status = type_match and boolean_match and dimension_match
        else:
            truth_candidate_id = "UNMATCHED"
            expected_radius = math.nan
            stl_truth_radius = math.nan
            observed_radius = float(row["Radius"])
            radius_difference = math.nan
            independent_radius_error_from_stl = math.nan
            reported_radius_error_from_stl = math.nan
            depth_difference = math.nan
            type_match = False
            boolean_match = False
            dimension_match = False
            status = False
        candidate_checks.append(status)
        candidate_mapping_rows.append(
            {
                "OutputCandidateID": output_candidate_id,
                "TruthCandidateID": truth_candidate_id,
                "RelatedTruthSurfaceIDs": ";".join(related_truth),
                "PrimitiveTypeMatch": type_match,
                "BooleanTypeMatch": boolean_match,
                "IndependentFitRadiusMM": expected_radius,
                "STLTruthRadiusMM": stl_truth_radius,
                "ReportedRadiusMM": observed_radius,
                "RadiusDifferenceFromIndependentFitMM": radius_difference,
                "IndependentFitRadiusErrorFromSTLTruthMM": independent_radius_error_from_stl,
                "ReportedRadiusErrorFromSTLTruthMM": reported_radius_error_from_stl,
                "DepthDifferenceFromSTLTruthMM": depth_difference,
                "DimensionMatch": dimension_match,
                "ValidationStatus": "PASS" if status else "FAIL",
            }
        )
    candidate_pass = (
        all(candidate_checks)
        and len(candidate_frame) == len(truth_candidates)
        and len(output_candidate_to_truth) == len(truth_candidates)
    )

    output_tree_payload = load_json(arguments.csg)
    output_tree = output_tree_payload.get("tree", output_tree_payload)
    normalized_output_tree = normalized_tree(output_tree, output_candidate_to_truth)
    normalized_truth_tree = normalized_tree(truth["canonical_csg_tree"], {})
    csg_pass = normalized_output_tree == normalized_truth_tree

    five_layer = {
        "segmentation": "PASS" if segmentation_pass else "FAIL",
        "geometry_semantics": "PASS" if geometry_pass else "FAIL",
        "topology": "PASS" if topology_pass else "FAIL",
        "primitive_candidates": "PASS" if candidate_pass else "FAIL",
        "csg_symbolic_tree": "PASS" if csg_pass else "FAIL",
    }
    overall = "PASS" if all(value == "PASS" for value in five_layer.values()) else "FAIL"
    summary = {
        "schema_version": "1.0",
        "case": "Stepped Cylinder",
        "display_name": "階梯狀圓柱",
        "validation_target": "existing verified outputs compared against an STL-only independent truth",
        "parameters": {
            "point_count": POINT_COUNT,
            "distance_threshold_mm": DISTANCE_THRESHOLD_MM,
            "normal_threshold": NORMAL_THRESHOLD,
            "fit_residual_threshold_mm": FIT_RESIDUAL_THRESHOLD_MM,
            "endcap_dot_threshold": ENDCAP_DOT_THRESHOLD,
            "orthogonal_dot_threshold": ORTHOGONAL_DOT_THRESHOLD,
            "numeric_output_tolerance_mm": NUMERIC_OUTPUT_TOLERANCE_MM,
        },
        "counts": {
            "total_points": int(len(verified_result)),
            "valid_points": int(np.sum(cluster_ids >= 0)),
            "residual_points": residual_count,
            "valid_clusters": len(valid_cluster_values),
            "truth_surfaces": len(surfaces),
            "truth_topology_edges": len(truth_topology),
            "observed_topology_edges": len(topology_frame),
            "truth_candidates": len(truth_candidates),
            "observed_candidates": len(candidate_frame),
        },
        "input_integrity": {
            "original_result_vs_verified_coordinate_normal_max_difference": original_result_vs_verified_max_difference,
            "point_cloud_vs_verified_coordinate_normal_max_difference": point_vs_verified_max_difference,
            "serialization_equivalence_tolerance": SERIALIZATION_EQUIVALENCE_TOLERANCE,
            "pass": input_unchanged,
        },
        "segmentation_details": {
            "one_cluster_per_truth_surface": one_to_one,
            "unmatched_valid_point_count": unmatched_valid_count,
            "all_truth_surfaces_mesh_connected_components": [
                {"surface_id": surface["surface_id"], "count": surface["mesh_connected_components"]}
                for surface in surfaces
            ],
        },
        "geometry_semantics_details": {
            "criterion": "independent plane PCA or geometric nonlinear least-squares circle fit; reported cylinder parameters must agree with that optimum",
            "fit_residual_limit_mm": FIT_RESIDUAL_THRESHOLD_MM,
            "failed_clusters": [
                int(row["ClusterID"])
                for row in surface_mapping_rows
                if row["GeometrySemanticsStatus"] == "FAIL"
            ],
        },
        "topology_details": {
            "truth_source": "all shared STL mesh edges between independently segmented surfaces",
            "missing_edges": missing_topology,
            "extra_edges": extra_topology,
            "unmapped_output_rows": topology_unmapped_rows,
            "allowed_edge_types_only": topology_types_ok,
        },
        "primitive_candidate_details": {
            "failed_output_candidate_ids": [
                row["OutputCandidateID"]
                for row in candidate_mapping_rows
                if row["ValidationStatus"] == "FAIL"
            ]
        },
        "csg_details": {
            "normalized_truth_tree": normalized_truth_tree,
            "normalized_output_tree": normalized_output_tree,
            "scope": "symbolic CSG inference only",
        },
        "five_layer_validation": five_layer,
        "overall": overall,
        "claim_control": (
            "Stepped Cylinder may be reported as independently validated only if overall is PASS. "
            "This result does not validate L-Bracket, Model A, real scans, or CAD solid export."
        ),
    }

    input_files = {
        "truth": arguments.truth,
        "point_cloud": arguments.point_cloud,
        "original_result": arguments.original_result,
        "verified_result": arguments.verified_result,
        "face_summary": arguments.face_summary,
        "topology": arguments.topology,
        "candidates": arguments.candidates,
        "csg": arguments.csg,
    }
    manifest = {
        "schema_version": "1.0",
        "case": "Stepped Cylinder",
        "inputs": {
            name: {"filename": path.name, "sha256": sha256(path)}
            for name, path in input_files.items()
        },
        "programs": {
            "truth_builder": {
                "filename": arguments.truth_builder.name,
                "sha256": sha256(arguments.truth_builder),
                "permitted_runtime_input": "Stepped Cylinder.stl only",
            },
            "validator": {"filename": Path(__file__).name, "sha256": sha256(Path(__file__))},
        },
        "forbidden_truth_builder_inputs": [
            "point cloud",
            "Result",
            "FaceSummary",
            "TopologyEdges",
            "PrimitiveCandidates",
            "prior GroundTruth",
        ],
    }
    return summary, surface_mapping_rows, candidate_mapping_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Stepped Cylinder outputs against an STL-only truth.")
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--truth-builder", required=True, type=Path)
    parser.add_argument("--point-cloud", required=True, type=Path)
    parser.add_argument("--original-result", required=True, type=Path)
    parser.add_argument("--verified-result", required=True, type=Path)
    parser.add_argument("--face-summary", required=True, type=Path)
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--csg", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    for attribute in (
        "truth",
        "truth_builder",
        "point_cloud",
        "original_result",
        "verified_result",
        "face_summary",
        "topology",
        "candidates",
        "csg",
        "output_dir",
    ):
        setattr(arguments, attribute, getattr(arguments, attribute).resolve())

    summary, surface_rows, candidate_rows, manifest = validate(arguments)
    output_dir: Path = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "ValidationAgainstIndependentTruth_Stepped_Cylinder.json", summary)
    write_json(output_dir / "IndependentTruthBuildManifest.json", manifest)
    write_csv(
        output_dir / "SurfaceMapping_Stepped_Cylinder.csv",
        [
            "ClusterID",
            "TruthSurfaceID",
            "SemanticRole",
            "Geometry",
            "PointCount",
            "DominantTruthPointCount",
            "MinorityTruthPointCount",
            "UnmatchedPointCount",
            "TruthSurfaceConnectedComponents",
            "IndependentFitResidualMaxMM",
            "IndependentNormalConsistencyMin",
            "IndependentFitRadiusMM",
            "IndependentFitCenterX",
            "IndependentFitCenterY",
            "IndependentFitCenterZ",
            "ReportedRadiusMM",
            "RadiusDifferenceFromIndependentFitMM",
            "STLTruthRadiusMM",
            "IndependentFitRadiusErrorFromSTLTruthMM",
            "ReportedRadiusErrorFromSTLTruthMM",
            "IndependentFitRMSEMM",
            "ReportedModelRMSEMM",
            "ReportedFeatureType",
            "SemanticMatch",
            "PointCountMatch",
            "AxisOrNormalMatch",
            "NumericFitMatch",
            "SegmentationStatus",
            "GeometrySemanticsStatus",
        ],
        surface_rows,
    )
    write_csv(
        output_dir / "CandidateMapping_Stepped_Cylinder.csv",
        [
            "OutputCandidateID",
            "TruthCandidateID",
            "RelatedTruthSurfaceIDs",
            "PrimitiveTypeMatch",
            "BooleanTypeMatch",
            "IndependentFitRadiusMM",
            "STLTruthRadiusMM",
            "ReportedRadiusMM",
            "RadiusDifferenceFromIndependentFitMM",
            "IndependentFitRadiusErrorFromSTLTruthMM",
            "ReportedRadiusErrorFromSTLTruthMM",
            "DepthDifferenceFromSTLTruthMM",
            "DimensionMatch",
            "ValidationStatus",
        ],
        candidate_rows,
    )


if __name__ == "__main__":
    main()
