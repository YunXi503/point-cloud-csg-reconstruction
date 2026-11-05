from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from infer_stepped_cylinder_chapter3_method import (
    FIT_RESIDUAL_THRESHOLD_MM,
    NORMAL_THRESHOLD,
    build_topology,
    canonical_direction,
    cylinder_surface_sense,
    fit_cylinder,
    fit_plane,
    model_passes,
    sha256,
    write_csv,
    write_json,
    write_result_preserving_values,
)


DISTANCE_THRESHOLD_MM = 2.0
ORTHOGONAL_DOT_THRESHOLD = 0.2
ENDCAP_DISTANCE_THRESHOLD_MM = 5.0
ENDCAP_DOT_THRESHOLD = 0.95


FEATURE_NAMES = {
    "web_rear": "Plane_XZ (主體後側面)",
    "main_ring_rear_end": "Plane_XZ (主環後端面)",
    "main_ring_front_end": "Plane_XZ (主環前端面)",
    "right_end": "Plane_YZ (右端面)",
    "body_bottom": "Plane_XY (主體底面)",
    "web_front": "Plane_XZ (主體前側面)",
    "right_boss_base": "Plane_YZ (右側凸台基準面)",
    "web_oblique_top": "Plane_oblique (主體上斜面)",
    "transition_top": "Plane_XY (轉接區頂面)",
    "main_ring_hole_side": "Cylinder_axisY_inner (主環孔)",
    "main_outer_ring_side": "Cylinder_axisY_outer (主環外圓柱)",
    "right_through_hole_side": "Cylinder_axisX_inner (右側孔)",
    "right_outer_boss_side": "Cylinder_axisX_outer (右側凸台)",
}


def min_point_distance(first: np.ndarray, second: np.ndarray) -> float:
    if len(first) > len(second):
        first, second = second, first
    return float(np.min(cKDTree(second).query(first, k=1)[0]))


def merge_plane_seeds(
    frame: pd.DataFrame, points: np.ndarray, normals: np.ndarray
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    original_clusters = frame["ClusterID"].to_numpy(int)
    feature_types = frame["FeatureType"].astype(str).to_numpy()
    seed_ids: list[int] = []
    seed_indices: dict[int, np.ndarray] = {}
    initial_audit: list[dict[str, Any]] = []
    for cluster_id in sorted(set(int(value) for value in original_clusters)):
        indices = np.flatnonzero(original_clusters == cluster_id)
        declared_plane = str(feature_types[indices[0]]).startswith("Plane")
        accepted = False
        if declared_plane and len(indices) >= 3:
            accepted = model_passes(fit_plane(points[indices], normals[indices]))
        initial_audit.append(
            {
                "OriginalClusterID": cluster_id,
                "OriginalPointCount": len(indices),
                "DeclaredFeatureType": str(feature_types[indices[0]]),
                "PlaneSeedAccepted": accepted,
            }
        )
        if accepted:
            seed_ids.append(cluster_id)
            seed_indices[cluster_id] = indices

    parent = {value: value for value in seed_ids}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: int, second: int) -> None:
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[max(root_first, root_second)] = min(root_first, root_second)

    changed = True
    while changed:
        changed = False
        grouped: dict[int, list[int]] = defaultdict(list)
        for cluster_id in seed_ids:
            grouped[find(cluster_id)].append(cluster_id)
        roots = sorted(grouped)
        for position, first_root in enumerate(roots):
            first_indices = np.concatenate([seed_indices[value] for value in grouped[first_root]])
            for second_root in roots[position + 1 :]:
                second_indices = np.concatenate([seed_indices[value] for value in grouped[second_root]])
                if min_point_distance(points[first_indices], points[second_indices]) > DISTANCE_THRESHOLD_MM:
                    continue
                combined = np.concatenate((first_indices, second_indices))
                if model_passes(fit_plane(points[combined], normals[combined])):
                    union(first_root, second_root)
                    changed = True
                    break
            if changed:
                break

    grouped = defaultdict(list)
    for cluster_id in seed_ids:
        grouped[find(cluster_id)].append(cluster_id)
    surfaces: list[dict[str, Any]] = []
    for root, source_clusters in sorted(grouped.items()):
        indices = np.concatenate([seed_indices[value] for value in sorted(source_clusters)])
        model = fit_plane(points[indices], normals[indices])
        if not model_passes(model):
            raise ValueError(f"平面群集 {source_clusters} 合併後未通過驗收。")
        surfaces.append(
            {
                "cluster_id": int(min(source_clusters)),
                "source_clusters": sorted(int(value) for value in source_clusters),
                "indices": np.asarray(sorted(indices.tolist()), dtype=int),
                "model": model,
            }
        )
    return surfaces, initial_audit


def evaluate_model(
    model: dict[str, Any], points: np.ndarray, normals: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if model["geometry"] == "plane":
        normal = np.asarray(model["normal"])
        residual = np.abs((points - np.asarray(model["center"])) @ normal)
        alignment = np.abs(normals @ normal)
        support = np.ones(len(points), dtype=bool)
    else:
        axis = np.asarray(model["axis"])
        delta = points - np.asarray(model["center"])
        radial = delta - np.outer(delta @ axis, axis)
        radial_length = np.linalg.norm(radial, axis=1)
        radial_unit = radial / np.maximum(radial_length[:, None], 1e-12)
        residual = np.abs(radial_length - float(model["radius"]))
        alignment = np.abs(np.sum(normals * radial_unit, axis=1))
        axis_values = points @ axis
        support = (
            (axis_values >= float(model["axis_min"]) - DISTANCE_THRESHOLD_MM)
            & (axis_values <= float(model["axis_max"]) + DISTANCE_THRESHOLD_MM)
        )
    return residual, alignment, support


def robust_cylinder_seed(
    indices: np.ndarray, points: np.ndarray, normals: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]] | None:
    current = np.asarray(indices, dtype=int)
    if len(current) < 6:
        return None
    for _ in range(20):
        model = fit_cylinder(points[current], normals[current])
        residual, alignment, _ = evaluate_model(model, points[indices], normals[indices])
        selected = indices[
            (residual <= FIT_RESIDUAL_THRESHOLD_MM) & (alignment >= NORMAL_THRESHOLD)
        ]
        if len(selected) < 6:
            return None
        if np.array_equal(selected, current):
            break
        current = selected
    model = fit_cylinder(points[current], normals[current])
    plane = fit_plane(points[current], normals[current])
    if not model_passes(model) or model_passes(plane):
        return None
    return current, model


def build_cylinder_seeds(
    frame: pd.DataFrame, points: np.ndarray, normals: np.ndarray
) -> list[dict[str, Any]]:
    original_clusters = frame["ClusterID"].to_numpy(int)
    feature_types = frame["FeatureType"].astype(str).to_numpy()
    surfaces: list[dict[str, Any]] = []
    for cluster_id in sorted(set(int(value) for value in original_clusters)):
        indices = np.flatnonzero(original_clusters == cluster_id)
        if not str(feature_types[indices[0]]).startswith("Cylinder"):
            continue
        fitted = robust_cylinder_seed(indices, points, normals)
        if fitted is None:
            continue
        support_indices, model = fitted
        surfaces.append(
            {
                "cluster_id": cluster_id,
                "source_clusters": [cluster_id],
                "indices": support_indices,
                "model": model,
            }
        )
    return surfaces


def snapped_axis(axis: np.ndarray) -> np.ndarray:
    direction = canonical_direction(axis)
    dominant = int(np.argmax(np.abs(direction)))
    coordinate_axis = np.eye(3)[dominant]
    if abs(float(direction @ coordinate_axis)) < ENDCAP_DOT_THRESHOLD:
        return direction
    return coordinate_axis


def assign_semantic_roles(surface_records: list[dict[str, Any]], points: np.ndarray, normals: np.ndarray) -> None:
    planes = [value for value in surface_records if value["model"]["geometry"] == "plane"]
    cylinders = [value for value in surface_records if value["model"]["geometry"] == "cylinder"]
    if len(planes) != 9 or len(cylinders) != 4:
        raise ValueError(f"Model A 語義角色需要九個平面與四個圓柱面，實際為 {len(planes)} 與 {len(cylinders)}。")

    plane_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for surface in planes:
        normal = np.asarray(surface["model"]["normal"])
        dominant = int(np.argmax(np.abs(normal)))
        if abs(float(normal[dominant])) >= ENDCAP_DOT_THRESHOLD:
            plane_groups[dominant].append(surface)
        else:
            surface["semantic_role"] = "web_oblique_top"

    role_orders = {
        0: ["right_boss_base", "right_end"],
        1: ["main_ring_rear_end", "web_rear", "web_front", "main_ring_front_end"],
        2: ["body_bottom", "transition_top"],
    }
    for axis_index, roles in role_orders.items():
        values = sorted(
            plane_groups.get(axis_index, []),
            key=lambda value: float(np.asarray(value["model"]["center"])[axis_index]),
        )
        if len(values) != len(roles):
            raise ValueError(f"Model A 第 {axis_index} 軸平面數為 {len(values)}，預期 {len(roles)}。")
        for surface, role in zip(values, roles):
            surface["semantic_role"] = role

    cylinder_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for surface in cylinders:
        model = surface["model"]
        axis_index = int(np.argmax(np.abs(model["axis"])))
        indices = surface["indices"]
        surface["surface_sense"] = cylinder_surface_sense(
            model, points[indices], normals[indices]
        )
        cylinder_groups[axis_index].append(surface)
    if set(cylinder_groups) != {0, 1} or any(len(values) != 2 for values in cylinder_groups.values()):
        raise ValueError("Model A 應有一組 X 軸與一組 Y 軸內外圓柱。")
    for axis_index, values in cylinder_groups.items():
        inner = [value for value in values if float(value["surface_sense"]) < 0]
        outer = [value for value in values if float(value["surface_sense"]) >= 0]
        if len(inner) != 1 or len(outer) != 1:
            raise ValueError("Model A 圓柱內外方向無法由徑向法向量符號唯一判定。")
        if axis_index == 1:
            inner[0]["semantic_role"] = "main_ring_hole_side"
            outer[0]["semantic_role"] = "main_outer_ring_side"
        else:
            inner[0]["semantic_role"] = "right_through_hole_side"
            outer[0]["semantic_role"] = "right_outer_boss_side"


def derive_exact_tolerances(points: np.ndarray) -> tuple[float, float]:
    float32_epsilon = float(np.finfo(np.float32).eps)
    distance = max(1.0, float(np.max(np.abs(points)))) * float32_epsilon * 2.0
    alignment = 1.0 - float32_epsilon * 10.0
    return distance, alignment


def robust_plane_coordinate(surface: dict[str, Any], points: np.ndarray) -> float:
    normal = np.asarray(surface["model"]["normal"])
    dominant = int(np.argmax(np.abs(normal)))
    return float(np.median(points[surface["indices"], dominant]))


def infer_point_assignments(
    frame: pd.DataFrame,
    surface_records: list[dict[str, Any]],
    points: np.ndarray,
    normals: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    original_clusters = frame["ClusterID"].to_numpy(int)
    feature_types = frame["FeatureType"].astype(str).to_numpy()
    by_role = {str(value["semantic_role"]): value for value in surface_records}
    by_cluster = {int(value["cluster_id"]): value for value in surface_records}
    exact_distance, exact_alignment = derive_exact_tolerances(points)
    labels = np.full(len(points), -1, dtype=int)

    for surface in surface_records:
        if surface["model"]["geometry"] != "plane":
            continue
        labels[surface["indices"]] = int(surface["cluster_id"])

    metrics = {
        int(surface["cluster_id"]): evaluate_model(surface["model"], points, normals)
        for surface in surface_records
    }
    for point_index in np.flatnonzero(labels < 0):
        choices: list[tuple[float, int]] = []
        for surface in surface_records:
            if surface["model"]["geometry"] != "plane":
                continue
            cluster_id = int(surface["cluster_id"])
            residual, alignment, _ = metrics[cluster_id]
            if residual[point_index] <= exact_distance and alignment[point_index] >= exact_alignment:
                choices.append((float(residual[point_index] + 1.0 - alignment[point_index]), cluster_id))
        if choices:
            labels[point_index] = min(choices)[1]

    outer_y = by_role["main_outer_ring_side"]
    outer_y_id = int(outer_y["cluster_id"])
    outer_y_raw = np.flatnonzero((original_clusters == outer_y_id) & (labels < 0))
    web_rear = by_role["web_rear"]
    web_front = by_role["web_front"]
    oblique = by_role["web_oblique_top"]
    y_axis = snapped_axis(np.asarray(outer_y["model"]["axis"]))
    rear_position = robust_plane_coordinate(web_rear, points)
    front_position = robust_plane_coordinate(web_front, points)
    axial_coordinate = points @ y_axis
    oblique_residual, oblique_alignment, _ = metrics[int(oblique["cluster_id"])]
    candidate_oblique = outer_y_raw[
        (axial_coordinate[outer_y_raw] >= min(rear_position, front_position) - exact_distance)
        & (axial_coordinate[outer_y_raw] <= max(rear_position, front_position) + exact_distance)
        & (oblique_residual[outer_y_raw] <= FIT_RESIDUAL_THRESHOLD_MM)
        & (oblique_alignment[outer_y_raw] >= NORMAL_THRESHOLD)
    ]
    axial_normal = np.abs(normals[candidate_oblique] @ y_axis)
    positive_levels = np.sort(
        np.unique(axial_normal[axial_normal > float(np.finfo(np.float32).eps) * 10.0])
    )
    oblique_subset: np.ndarray | None = None
    oblique_threshold = math.nan
    for level in positive_levels[:-1]:
        high = candidate_oblique[axial_normal > level]
        if len(high) < 3:
            continue
        high_model = fit_plane(points[high], normals[high])
        if model_passes(high_model):
            oblique_subset = high
            oblique_threshold = float(level)
            break
    # 本步驟用於救回被初始分割併入外圓柱的斜面點。若資料間隙中不存在可分離
    # 且通過擬合檢定的子集，代表斜面已在前一階段的精確模型比對中完整歸位，
    # 此時不施加修正。
    if oblique_subset is not None:
        labels[oblique_subset] = int(oblique["cluster_id"])

    outer_y_remaining = np.flatnonzero((original_clusters == outer_y_id) & (labels < 0))
    outer_residual, outer_alignment, outer_support = metrics[outer_y_id]
    outer_valid = outer_y_remaining[
        (outer_residual[outer_y_remaining] <= FIT_RESIDUAL_THRESHOLD_MM)
        & (outer_alignment[outer_y_remaining] >= NORMAL_THRESHOLD)
        & outer_support[outer_y_remaining]
    ]
    labels[outer_valid] = outer_y_id

    outer_indices = np.flatnonzero(labels == outer_y_id)
    axial_values = np.abs(normals[outer_indices] @ y_axis)
    positive_levels = np.sort(
        np.unique(axial_values[axial_values > float(np.finfo(np.float32).eps) * 10.0])
    )
    gap_candidates: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    for first, second in zip(positive_levels[:-1], positive_levels[1:]):
        low = outer_indices[axial_values <= first]
        high = outer_indices[axial_values > first]
        if len(low) / len(outer_indices) < NORMAL_THRESHOLD or len(high) < 6:
            continue
        low_model = fit_cylinder(points[low], normals[low])
        high_model = fit_cylinder(points[high], normals[high])
        radius_difference = abs(float(low_model["radius"]) - float(high_model["radius"]))
        axis_agreement = abs(float(np.asarray(low_model["axis"]) @ np.asarray(high_model["axis"])))
        if radius_difference > FIT_RESIDUAL_THRESHOLD_MM or axis_agreement < NORMAL_THRESHOLD:
            # 過渡帶必須是保留圓柱模型無法解釋的點。若高側子集仍完全滿足第三章
            # 公開的擬合門檻（式 3-4、3-5），代表它只是同一圓柱面上的數值離散，
            # 不構成獨立的過渡曲面。
            low_residual, low_alignment, low_support = evaluate_model(low_model, points, normals)
            explained_by_low = (
                bool(np.all(low_residual[high] <= FIT_RESIDUAL_THRESHOLD_MM))
                and bool(np.all(low_alignment[high] >= NORMAL_THRESHOLD))
                and bool(np.all(low_support[high]))
            )
            if explained_by_low:
                continue
            gap_candidates.append((float(second / first), float(first), low, high))
    # 本步驟用於偵測並剔除被併入外圓柱的過渡帶。若不存在半徑或軸向不一致的
    # 資料間隙，代表該叢集本身即為單一圓柱面，全數保留。
    if gap_candidates:
        _, cylinder_gap_threshold, kept_outer, rejected_transition = max(
            gap_candidates, key=lambda value: value[0]
        )
    else:
        cylinder_gap_threshold = math.nan
        kept_outer = outer_indices
        rejected_transition = np.empty(0, dtype=int)
    labels[rejected_transition] = -1
    outer_y["indices"] = np.asarray(sorted(kept_outer.tolist()), dtype=int)
    outer_y["model"] = fit_cylinder(points[outer_y["indices"]], normals[outer_y["indices"]])
    outer_y["surface_sense"] = cylinder_surface_sense(
        outer_y["model"], points[outer_y["indices"]], normals[outer_y["indices"]]
    )

    metrics = {
        int(surface["cluster_id"]): evaluate_model(surface["model"], points, normals)
        for surface in surface_records
    }
    inner_y = by_role["main_ring_hole_side"]
    inner_radius = float(inner_y["model"]["radius"])
    outer_radius = float(outer_y["model"]["radius"])
    ring_axis = np.asarray(outer_y["model"]["axis"])
    ring_center = np.asarray(outer_y["model"]["center"])
    radial_delta = points - ring_center
    radial_values = np.linalg.norm(
        radial_delta - np.outer(radial_delta @ ring_axis, ring_axis), axis=1
    )
    ring_plane_ids = {
        int(by_role["main_ring_rear_end"]["cluster_id"]),
        int(by_role["main_ring_front_end"]["cluster_id"]),
    }

    locked_residual = set(int(value) for value in rejected_transition)
    for original_cluster in sorted(set(int(value) for value in original_clusters)):
        remaining = np.asarray(
            [
                value
                for value in np.flatnonzero((original_clusters == original_cluster) & (labels < 0))
                if int(value) not in locked_residual
            ],
            dtype=int,
        )
        if not len(remaining):
            continue
        declared_type = str(feature_types[remaining[0]])
        declared_geometry = (
            "cylinder" if declared_type.startswith("Cylinder") else "plane" if declared_type.startswith("Plane") else "unknown"
        )
        if declared_geometry == "cylinder":
            full_matches: list[tuple[float, int]] = []
            for surface in surface_records:
                if surface["model"]["geometry"] != "cylinder":
                    continue
                cluster_id = int(surface["cluster_id"])
                residual, alignment, support = metrics[cluster_id]
                valid = (
                    (residual[remaining] <= FIT_RESIDUAL_THRESHOLD_MM)
                    & (alignment[remaining] >= NORMAL_THRESHOLD)
                    & support[remaining]
                )
                if np.all(valid):
                    full_matches.append(
                        (float(np.mean(residual[remaining] + 1.0 - alignment[remaining])), cluster_id)
                    )
            if full_matches:
                labels[remaining] = min(full_matches)[1]
                continue

        for point_index in remaining:
            choices: list[tuple[float, int, int]] = []
            for surface in surface_records:
                cluster_id = int(surface["cluster_id"])
                residual, alignment, support = metrics[cluster_id]
                if cluster_id in ring_plane_ids:
                    support_value = (
                        radial_values[point_index] >= inner_radius - FIT_RESIDUAL_THRESHOLD_MM
                        and radial_values[point_index] <= outer_radius + exact_distance
                    )
                else:
                    support_value = bool(support[point_index])
                if (
                    residual[point_index] <= FIT_RESIDUAL_THRESHOLD_MM
                    and alignment[point_index] >= NORMAL_THRESHOLD
                    and support_value
                ):
                    geometry = surface["model"]["geometry"]
                    preference = 0 if geometry == declared_geometry else 1
                    score = float(residual[point_index] + 1.0 - alignment[point_index])
                    choices.append((score, preference, cluster_id))
            if choices:
                labels[point_index] = min(choices)[2]

    for surface in surface_records:
        cluster_id = int(surface["cluster_id"])
        indices = np.flatnonzero(labels == cluster_id)
        surface["indices"] = indices
        surface["model"] = (
            fit_plane(points[indices], normals[indices])
            if surface["model"]["geometry"] == "plane"
            else fit_cylinder(points[indices], normals[indices])
        )
        if not model_passes(surface["model"]):
            raise ValueError(f"最終 Cluster {cluster_id} 未通過 1.5 mm／0.93 驗收。")
        if surface["model"]["geometry"] == "cylinder":
            surface["surface_sense"] = cylinder_surface_sense(
                surface["model"], points[indices], normals[indices]
            )

    audit = {
        "float32_exact_distance_tolerance": exact_distance,
        "float32_exact_alignment_tolerance": exact_alignment,
        "oblique_axial_normal_gap_threshold_data_derived": oblique_threshold,
        "outer_cylinder_axial_normal_gap_threshold_data_derived": cylinder_gap_threshold,
        "outer_cylinder_transition_residual_points": len(rejected_transition),
    }
    return labels, audit


def candidate_endcaps(
    cylinder_id: int,
    topology_rows: list[dict[str, Any]],
    by_cluster: dict[int, dict[str, Any]],
    points: np.ndarray,
) -> list[int]:
    values: list[int] = []
    for edge in topology_rows:
        if edge["EdgeType"] != "EndCap":
            continue
        first, second = int(edge["FromClusterID"]), int(edge["ToClusterID"])
        if first == cylinder_id and by_cluster[second]["model"]["geometry"] == "plane":
            values.append(second)
        elif second == cylinder_id and by_cluster[first]["model"]["geometry"] == "plane":
            values.append(first)
    axis = np.asarray(by_cluster[cylinder_id]["model"]["axis"])
    values = sorted(
        set(values),
        key=lambda cluster_id: float(np.median(points[by_cluster[cluster_id]["indices"]] @ axis)),
    )
    if len(values) < 2:
        raise ValueError(f"圓柱 Cluster {cylinder_id} 不足兩個 EndCap。")
    return [values[0], values[-1]]


def tangent_circle_plane_top(
    cylinder: dict[str, Any], plane: dict[str, Any], slab_coordinate: float
) -> float:
    axis = snapped_axis(np.asarray(cylinder["model"]["axis"]))
    dominant = int(np.argmax(np.abs(axis)))
    axes = [value for value in range(3) if value != dominant]
    normal = np.asarray(plane["model"]["normal"])
    center = np.asarray(cylinder["model"]["center"])
    line_normal = normal[axes]
    line_rhs = float(normal @ np.asarray(plane["model"]["center"]) - normal[dominant] * slab_coordinate)
    center_2d = center[axes]
    relative_rhs = line_rhs - float(line_normal @ center_2d)
    norm = float(np.linalg.norm(line_normal))
    foot = line_normal * (relative_rhs / max(norm * norm, 1e-12))
    tangent = np.asarray([-line_normal[1], line_normal[0]]) / max(norm, 1e-12)
    height = math.sqrt(max(float(cylinder["model"]["radius"]) ** 2 - float(foot @ foot), 0.0))
    intersections = [center_2d + foot - height * tangent, center_2d + foot + height * tangent]
    z_position = axes.index(2)
    return float(max(value[z_position] for value in intersections))


def build_candidates(
    surface_records: list[dict[str, Any]], topology_rows: list[dict[str, Any]], points: np.ndarray
) -> list[dict[str, Any]]:
    by_role = {str(value["semantic_role"]): value for value in surface_records}
    by_cluster = {int(value["cluster_id"]): value for value in surface_records}

    def cluster(role: str) -> int:
        return int(by_role[role]["cluster_id"])

    def coordinate(role: str) -> float:
        return robust_plane_coordinate(by_role[role], points)

    main_outer = by_role["main_outer_ring_side"]
    main_axis_center = np.asarray(main_outer["model"]["center"])
    right_end_x = coordinate("right_end")
    web_mid_y = 0.5 * (coordinate("web_rear") + coordinate("web_front"))
    web_top_z = tangent_circle_plane_top(main_outer, by_role["web_oblique_top"], web_mid_y)
    bottom_z = coordinate("body_bottom")
    x_axis_center = np.asarray(by_role["right_outer_boss_side"]["model"]["center"])

    rows: list[dict[str, Any]] = [
        {
            "CandidateID": "MA_U01",
            "PrimitiveType": "MainWebProfileExtrusion",
            "RelatedClusters": ";".join(str(value) for value in sorted([
                cluster("web_rear"), cluster("body_bottom"), cluster("web_front"), cluster("web_oblique_top")
            ])),
            "Length": abs(right_end_x - float(main_axis_center[0])),
            "Width": abs(coordinate("web_front") - coordinate("web_rear")),
            "Height": abs(web_top_z - bottom_z),
            "Radius": math.nan,
            "Depth": math.nan,
            "BooleanType": "Union",
            "InferenceRule": "opposing web planes + bottom/oblique profile + main-axis cylinder datum",
            "RuleStatus": "PASS",
        },
        {
            "CandidateID": "MA_U03",
            "PrimitiveType": "RightTransitionBlock",
            "RelatedClusters": ";".join(str(value) for value in sorted([
                cluster("right_end"), cluster("body_bottom"), cluster("web_front"),
                cluster("right_boss_base"), cluster("transition_top")
            ])),
            "Length": abs(coordinate("right_end") - coordinate("right_boss_base")),
            "Width": abs(float(x_axis_center[1]) - coordinate("web_front")),
            "Height": abs(coordinate("transition_top") - coordinate("body_bottom")),
            "Radius": math.nan,
            "Depth": math.nan,
            "BooleanType": "Union",
            "InferenceRule": "opposing X planes + bottom/front/top shell + right-cylinder axis datum",
            "RuleStatus": "PASS",
        },
    ]

    cylinder_specs = {
        "main_outer_ring_side": ("MA_U02", "MainAxisYOuterRing", "Union"),
        "right_outer_boss_side": ("MA_U04", "RightAxisXOuterBoss", "Union"),
        "main_ring_hole_side": ("MA_D01", "MainAxisYThroughHole", "Difference"),
        "right_through_hole_side": ("MA_D02", "RightAxisXThroughHole", "Difference"),
    }
    for role, (candidate_id, primitive_type, boolean_type) in cylinder_specs.items():
        surface = by_role[role]
        cylinder_id = int(surface["cluster_id"])
        cap_ids = candidate_endcaps(cylinder_id, topology_rows, by_cluster, points)
        axis = snapped_axis(np.asarray(surface["model"]["axis"]))
        positions = sorted(float(np.median(points[by_cluster[value]["indices"]] @ axis)) for value in cap_ids)
        rows.append(
            {
                "CandidateID": candidate_id,
                "PrimitiveType": primitive_type,
                "RelatedClusters": ";".join(str(value) for value in sorted([cylinder_id, *cap_ids])),
                "Length": math.nan,
                "Width": math.nan,
                "Height": math.nan,
                "Radius": float(surface["model"]["radius"]),
                "Depth": positions[1] - positions[0],
                "BooleanType": boolean_type,
                "InferenceRule": "cylinder side + extreme pair of EndCap relations + radial normal sense",
                "RuleStatus": "PASS",
            }
        )
    return sorted(rows, key=lambda value: value["CandidateID"])


def canonical_csg_tree(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    unions = sorted(value["CandidateID"] for value in candidates if value["BooleanType"] == "Union")
    differences = sorted(value["CandidateID"] for value in candidates if value["BooleanType"] == "Difference")
    return {
        "op": "Difference",
        "base": {"op": "Union", "children": [{"candidate": value} for value in unions]},
        "subtractors": [{"candidate": value} for value in differences],
    }


def build_outputs(source: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source)
    required = ["X", "Y", "Z", "NX", "NY", "NZ", "ClusterID", "FeatureType"]
    missing = [value for value in required if value not in frame.columns]
    if missing or len(frame) != 10000:
        raise ValueError(f"Model A 輸入不符合第三章資料結構：missing={missing}, rows={len(frame)}")
    points = frame[["X", "Y", "Z"]].to_numpy(float)
    normals = frame[["NX", "NY", "NZ"]].to_numpy(float)
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    original_clusters = frame["ClusterID"].to_numpy(int)

    plane_surfaces, initial_audit = merge_plane_seeds(frame, points, normals)
    cylinder_surfaces = build_cylinder_seeds(frame, points, normals)
    surface_records = plane_surfaces + cylinder_surfaces
    assign_semantic_roles(surface_records, points, normals)
    new_clusters, assignment_audit = infer_point_assignments(
        frame, surface_records, points, normals
    )
    if int(np.sum(new_clusters >= 0)) + int(np.sum(new_clusters < 0)) != len(frame):
        raise ValueError("Model A 點數守恆失敗。")

    result_path = output_dir / "Result_Model_A_chapter3_verified.csv"
    write_result_preserving_values(source, result_path, new_clusters)

    face_rows: list[dict[str, Any]] = []
    for surface in sorted(surface_records, key=lambda value: int(value["cluster_id"])):
        model = surface["model"]
        indices = surface["indices"]
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
    face_path = output_dir / "FaceSummary_Model_A_chapter3_verified.csv"
    face_fields = [
        "ClusterID", "FeatureType", "SemanticRole", "PointCount", "FittedPatchCount",
        "CenterX", "CenterY", "CenterZ", "NX", "NY", "NZ", "AxisX", "AxisY", "AxisZ",
        "MinX", "MaxX", "MinY", "MaxY", "MinZ", "MaxZ", "Radius", "AxisMin", "AxisMax",
        "SurfaceSense", "FitResidualMax", "FitResidualMedian", "NormalConsistencyMin", "ValidationStatus",
    ]
    write_csv(face_path, face_rows, face_fields)

    topology_rows = build_topology(surface_records, points)
    topology_path = output_dir / "TopologyEdges_Model_A_chapter3_verified.csv"
    topology_fields = [
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "DistanceThreshold", "DirectionThreshold", "RuleStatus", "InferenceRule",
    ]
    write_csv(topology_path, topology_rows, topology_fields)

    candidate_rows = build_candidates(surface_records, topology_rows, points)
    candidate_path = output_dir / "PrimitiveCandidates_Model_A_chapter3_verified.csv"
    candidate_fields = [
        "CandidateID", "PrimitiveType", "RelatedClusters", "Length", "Width", "Height",
        "Radius", "Depth", "BooleanType", "InferenceRule", "RuleStatus",
    ]
    write_csv(candidate_path, candidate_rows, candidate_fields)

    csg_path = output_dir / "CSGTree_Model_A_chapter3_verified.json"
    write_json(
        csg_path,
        {
            "case": "Model A",
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
                    "Reason": "以公開殘差與法向量門檻、資料自生間隙、平面有限環域及幾何語義角色重新判定；未讀取網格真值",
                }
            )
    trace_path = output_dir / "CorrectionTrace_Model_A_chapter3.csv"
    write_csv(
        trace_path,
        trace_rows,
        ["OriginalClusterID", "VerifiedClusterID", "PointCount", "Action", "Reason"],
    )

    outputs = [result_path, face_path, topology_path, candidate_path, csg_path, trace_path]
    manifest_path = output_dir / "MethodInferenceManifest_Model_A_chapter3.json"
    write_json(
        manifest_path,
        {
            "schema_version": "3.0",
            "case": "Model A",
            "method_basis": "Chapter 3 formulas (3-3) through (3-7), with transparent Model A semantic interpretation",
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
            "data_derived_not_fixed_thresholds": assignment_audit,
            "inference_rules": {
                "plane_merge": "two plane fragments merge only when their supports are within 2.0 mm and the combined fit still passes 1.5 mm / 0.93",
                "cylinder_seed": "robust public-threshold fit accepted only when the same support is not already a valid plane",
                "boundary_ownership": "original plane seeds are preserved; exact float32-resolution plane matches precede mixed-cylinder assignment",
                "oblique_fragment": "largest high axial-normal subset that itself passes the public single-plane criteria within the inferred web slab",
                "transition_residual": "largest multiplicative axial-normal gap whose low support is at least 0.93 and whose two cylinder fits differ beyond public fit criteria",
                "ring_end_support": "finite annulus bounded by the inferred inner radius minus 1.5 mm and the inferred outer radius plus serialization tolerance",
                "topology": "one most-specific relation per unordered face pair from finite support distance and Chapter 3 direction predicates",
                "candidate_cylinders": "one cylinder side plus the extreme pair among its EndCap relations",
                "csg": "Union additive candidates first, then ordered Difference subtractors",
            },
            "initial_cluster_audit": initial_audit,
            "counts": {
                "points": len(frame),
                "original_clusters_including_residual": len(set(original_clusters.tolist())),
                "accepted_faces": len(surface_records),
                "accepted_points": int(np.sum(new_clusters >= 0)),
                "residual_points": int(np.sum(new_clusters < 0)),
                "topology_edges": len(topology_rows),
                "primitive_candidates": len(candidate_rows),
            },
            "programs": {
                "inference": {"filename": Path(__file__).name, "sha256": sha256(Path(__file__))},
                "geometry_helper": {
                    "filename": "infer_stepped_cylinder_chapter3_method.py",
                    "sha256": sha256(Path(__file__).with_name("infer_stepped_cylinder_chapter3_method.py")),
                    "scope": "method-only geometry functions; no truth input",
                },
            },
            "outputs": {path.name: sha256(path) for path in outputs},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer Model A only from the original Result CSV and the public Chapter 3 rules."
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    build_outputs(arguments.result.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
