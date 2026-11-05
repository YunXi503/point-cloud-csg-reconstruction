from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from correct_stepped_cylinder_nls_v2 import fit_cylinder, fit_plane


DISTANCE_THRESHOLD_MM = 2.0
NORMAL_THRESHOLD = 0.93
FIT_RESIDUAL_THRESHOLD_MM = 1.5
ORTHOGONAL_DOT_THRESHOLD = 0.2
ENDCAP_DISTANCE_THRESHOLD_MM = 5.0
ENDCAP_DOT_THRESHOLD = 0.95


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def region_growing(points: np.ndarray, normals: np.ndarray) -> np.ndarray:
    pairs = np.asarray(list(cKDTree(points).query_pairs(DISTANCE_THRESHOLD_MM)), dtype=int)
    if len(pairs):
        similarity = np.einsum("ij,ij->i", normals[pairs[:, 0]], normals[pairs[:, 1]])
        pairs = pairs[similarity >= NORMAL_THRESHOLD]
    identity = np.arange(len(points), dtype=int)
    if len(pairs):
        row = np.r_[pairs[:, 0], pairs[:, 1], identity]
        column = np.r_[pairs[:, 1], pairs[:, 0], identity]
    else:
        row = identity
        column = identity
    graph = coo_matrix((np.ones(len(row)), (row, column)), shape=(len(points), len(points)))
    _, labels = connected_components(graph, directed=False)
    return labels.astype(int)


def fit_component(indices: np.ndarray, points: np.ndarray, normals: np.ndarray) -> dict[str, Any] | None:
    component_points = points[indices]
    component_normals = normals[indices]
    if len(indices) >= 3:
        plane = fit_plane(component_points, component_normals)
        if (
            float(np.max(plane["residual"])) <= FIT_RESIDUAL_THRESHOLD_MM
            and float(np.min(plane["alignment"])) >= NORMAL_THRESHOLD
        ):
            return plane
    if len(indices) >= 6:
        cylinder = fit_cylinder(component_points, component_normals)
        if (
            float(np.max(cylinder["residual"])) <= FIT_RESIDUAL_THRESHOLD_MM
            and float(np.min(cylinder["alignment"])) >= NORMAL_THRESHOLD
        ):
            return cylinder
    return None


def interval_gap(first: tuple[float, float], second: tuple[float, float]) -> float:
    if first[1] < second[0]:
        return second[0] - first[1]
    if second[1] < first[0]:
        return first[0] - second[1]
    return 0.0


def plane_support_gap(
    first_indices: np.ndarray,
    second_indices: np.ndarray,
    normal: np.ndarray,
    points: np.ndarray,
) -> float:
    dominant = int(np.argmax(np.abs(normal)))
    axes = [value for value in range(3) if value != dominant]
    first = points[first_indices]
    second = points[second_indices]
    gaps = [
        interval_gap(
            (float(first[:, axis].min()), float(first[:, axis].max())),
            (float(second[:, axis].min()), float(second[:, axis].max())),
        )
        for axis in axes
    ]
    return float(np.linalg.norm(gaps))


def merge_surface_components(
    initial_labels: np.ndarray,
    points: np.ndarray,
    normals: np.ndarray,
) -> tuple[list[np.ndarray], list[int]]:
    component_ids = sorted(set(initial_labels.tolist()))
    component_indices = {value: np.flatnonzero(initial_labels == value) for value in component_ids}
    models = {
        value: fit_component(component_indices[value], points, normals)
        for value in component_ids
    }
    valid_ids = [value for value in component_ids if models[value] is not None]
    parent = {value: value for value in valid_ids}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: int, second: int) -> None:
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[max(root_first, root_second)] = min(root_first, root_second)

    for position, first_id in enumerate(valid_ids):
        first = models[first_id]
        assert first is not None
        for second_id in valid_ids[position + 1 :]:
            second = models[second_id]
            assert second is not None
            if first["geometry"] != second["geometry"]:
                continue
            if first["geometry"] == "plane":
                direction_dot = float(np.asarray(first["normal"]) @ np.asarray(second["normal"]))
                if direction_dot < NORMAL_THRESHOLD:
                    continue
                offset = abs(
                    float(np.asarray(first["normal"]) @ (np.asarray(first["center"]) - np.asarray(second["center"])))
                )
                support_gap = plane_support_gap(
                    component_indices[first_id], component_indices[second_id], np.asarray(first["normal"]), points
                )
                if offset <= FIT_RESIDUAL_THRESHOLD_MM and support_gap <= DISTANCE_THRESHOLD_MM:
                    union(first_id, second_id)
            else:
                axis_dot = abs(float(np.asarray(first["axis"]) @ np.asarray(second["axis"])))
                radius_error = abs(float(first["radius"]) - float(second["radius"]))
                axis = np.asarray(first["axis"])
                center_delta = np.asarray(first["center"]) - np.asarray(second["center"])
                radial_center_error = float(np.linalg.norm(center_delta - axis * float(center_delta @ axis)))
                axial_gap = interval_gap(
                    (float(first["axis_min"]), float(first["axis_max"])),
                    (float(second["axis_min"]), float(second["axis_max"])),
                )
                if (
                    axis_dot >= NORMAL_THRESHOLD
                    and radius_error <= FIT_RESIDUAL_THRESHOLD_MM
                    and radial_center_error <= FIT_RESIDUAL_THRESHOLD_MM
                    and axial_gap <= DISTANCE_THRESHOLD_MM
                ):
                    union(first_id, second_id)

    grouped: dict[int, list[int]] = defaultdict(list)
    for component_id in valid_ids:
        grouped[find(component_id)].extend(component_indices[component_id].tolist())
    surfaces = [np.asarray(sorted(values), dtype=int) for _, values in sorted(grouped.items())]
    source_components = [root for root, _ in sorted(grouped.items())]

    resolved = set(int(value) for indices in surfaces for value in indices)
    unresolved = [value for value in range(len(points)) if value not in resolved]
    models_after_merge = [fit_component(indices, points, normals) for indices in surfaces]
    if any(model is None for model in models_after_merge):
        raise ValueError("合併後仍有無法辨識的主要曲面。")

    assignments: list[list[int]] = [indices.tolist() for indices in surfaces]
    for point_index in unresolved:
        point = points[point_index]
        normal = normals[point_index]
        candidates: list[tuple[float, int]] = []
        for surface_index, (indices, model) in enumerate(zip(surfaces, models_after_merge)):
            assert model is not None
            support_min = points[indices].min(axis=0) - DISTANCE_THRESHOLD_MM
            support_max = points[indices].max(axis=0) + DISTANCE_THRESHOLD_MM
            if model["geometry"] == "plane":
                fitted_normal = np.asarray(model["normal"])
                residual = abs(float((point - np.asarray(model["center"])) @ fitted_normal))
                alignment = float(normal @ fitted_normal)
                dominant = int(np.argmax(np.abs(fitted_normal)))
                support_axes = [value for value in range(3) if value != dominant]
                support_pass = bool(np.all(point[support_axes] >= support_min[support_axes]) and np.all(point[support_axes] <= support_max[support_axes]))
            else:
                axis = np.asarray(model["axis"])
                delta = point - np.asarray(model["center"])
                radial = delta - axis * float(delta @ axis)
                radial_length = float(np.linalg.norm(radial))
                radial_unit = radial / max(radial_length, 1e-12)
                residual = abs(radial_length - float(model["radius"]))
                alignment = abs(float(normal @ radial_unit))
                axis_value = float(point @ axis)
                support_pass = float(model["axis_min"]) - DISTANCE_THRESHOLD_MM <= axis_value <= float(model["axis_max"]) + DISTANCE_THRESHOLD_MM
            if residual <= FIT_RESIDUAL_THRESHOLD_MM and alignment >= NORMAL_THRESHOLD and support_pass:
                candidates.append((residual + (1.0 - alignment), surface_index))
        if candidates:
            assignments[min(candidates)[1]].append(point_index)

    final_surfaces = [np.asarray(sorted(values), dtype=int) for values in assignments]
    still_unresolved = sorted(set(range(len(points))) - {int(value) for indices in final_surfaces for value in indices})
    return final_surfaces, still_unresolved


def assign_cluster_ids(surfaces: list[np.ndarray], old_clusters: np.ndarray) -> list[int]:
    preferences: list[list[tuple[int, int]]] = []
    for indices in surfaces:
        counts = Counter(int(value) for value in old_clusters[indices] if int(value) >= 0)
        preferences.append(sorted(((count, cluster) for cluster, count in counts.items()), reverse=True))
    order = sorted(range(len(surfaces)), key=lambda value: (-len(surfaces[value]), value))
    assigned: dict[int, int] = {}
    used: set[int] = set()
    next_id = 0
    for surface_index in order:
        chosen = None
        for _, candidate in preferences[surface_index]:
            if candidate not in used:
                chosen = candidate
                break
        if chosen is None:
            while next_id in used:
                next_id += 1
            chosen = next_id
        assigned[surface_index] = chosen
        used.add(chosen)
    return [assigned[value] for value in range(len(surfaces))]


def cylinder_surface_sense(model: dict[str, Any], points: np.ndarray, normals: np.ndarray) -> float:
    axis = np.asarray(model["axis"])
    delta = points - np.asarray(model["center"])
    radial = delta - np.outer(delta @ axis, axis)
    radial_unit = radial / np.maximum(np.linalg.norm(radial, axis=1)[:, None], 1e-12)
    return float(np.median(np.sum(normals * radial_unit, axis=1)))


def semantic_roles(surface_records: list[dict[str, Any]]) -> None:
    planes = [value for value in surface_records if value["model"]["geometry"] == "plane"]
    cylinders = [value for value in surface_records if value["model"]["geometry"] == "cylinder"]
    by_axis_sign: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for surface in planes:
        normal = np.asarray(surface["model"]["normal"])
        axis = int(np.argmax(np.abs(normal)))
        sign = 1 if normal[axis] >= 0 else -1
        by_axis_sign[(axis, sign)].append(surface)

    role_groups = {
        (2, -1): ["base_bottom"],
        (2, 1): ["base_top", "boss_top", "upright_top"],
        (1, -1): ["back"],
        (1, 1): ["upright_front", "base_end"],
        (0, 1): ["right"],
        (0, -1): ["left"],
    }
    for key, roles in role_groups.items():
        values = sorted(by_axis_sign.get(key, []), key=lambda value: float(value["model"]["center"][key[0]]))
        if len(values) != len(roles):
            raise ValueError(f"L 型板平面角色數不符：方向 {key} 得到 {len(values)}，預期 {len(roles)}。")
        for surface, role in zip(values, roles):
            surface["semantic_role"] = role

    for surface in cylinders:
        model = surface["model"]
        axis_index = int(np.argmax(np.abs(model["axis"])))
        sense = float(surface["surface_sense"])
        if axis_index == 2 and sense > 0:
            surface["semantic_role"] = "outer_boss"
        elif axis_index == 2 and sense < 0:
            surface["semantic_role"] = "base_hole"
        elif axis_index == 1 and sense < 0:
            surface["semantic_role"] = "upright_hole"
        else:
            raise ValueError("L 型板圓柱角色無法由軸向與法向量方向唯一判定。")


FEATURE_NAMES = {
    "base_bottom": "Plane_XY (底板下表面)",
    "back": "Plane_XZ (底板與立板後側合併面)",
    "base_top": "Plane_XY (底板上表面)",
    "upright_top": "Plane_XY (立板頂面)",
    "outer_boss": "Cylinder_axisZ_outer (外加圓柱面)",
    "right": "Plane_YZ (底板與立板右側合併面)",
    "boss_top": "Plane_XY (外加圓柱頂面)",
    "upright_front": "Plane_XZ (立板前側面)",
    "left": "Plane_YZ (底板與立板左側合併面)",
    "base_hole": "Cylinder_axisZ_inner (底板孔)",
    "base_end": "Plane_XZ (底板端面)",
    "upright_hole": "Cylinder_axisY_inner (立板孔)",
}


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
                direction_dot = abs(float(np.asarray(plane["model"]["normal"]) @ np.asarray(cylinder["model"]["axis"])))
                if distance <= ENDCAP_DISTANCE_THRESHOLD_MM and direction_dot > ENDCAP_DOT_THRESHOLD:
                    edge_type = "EndCap"
                    direction_rule = "|axis·normal|>0.95"
                elif distance <= DISTANCE_THRESHOLD_MM:
                    edge_type = "Adjacency"
                    direction_rule = "distance-only"
            elif first_geometry == second_geometry == "plane":
                direction_dot = abs(float(np.asarray(first["model"]["normal"]) @ np.asarray(second["model"]["normal"])))
                if distance <= DISTANCE_THRESHOLD_MM:
                    if direction_dot < ORTHOGONAL_DOT_THRESHOLD:
                        edge_type = "OrthogonalAdjacency"
                        direction_rule = "|normal·normal|<0.2"
                    else:
                        edge_type = "Adjacency"
                        direction_rule = "distance-only"
            elif distance <= DISTANCE_THRESHOLD_MM:
                edge_type = "Adjacency"
                direction_rule = "distance-only"
            if edge_type is not None:
                rows.append(
                    {
                        "FromClusterID": min(int(first["cluster_id"]), int(second["cluster_id"])),
                        "ToClusterID": max(int(first["cluster_id"]), int(second["cluster_id"])),
                        "EdgeType": edge_type,
                        "MinDistance": distance,
                        "DirectionDot": direction_dot,
                        "DistanceThreshold": ENDCAP_DISTANCE_THRESHOLD_MM if edge_type == "EndCap" else DISTANCE_THRESHOLD_MM,
                        "DirectionThreshold": ENDCAP_DOT_THRESHOLD if edge_type == "EndCap" else (ORTHOGONAL_DOT_THRESHOLD if edge_type == "OrthogonalAdjacency" else math.nan),
                        "RuleStatus": "PASS",
                        "InferenceRule": direction_rule,
                    }
                )
    return sorted(rows, key=lambda value: (value["FromClusterID"], value["ToClusterID"], value["EdgeType"]))


def graph_connected(nodes: list[int], topology_rows: list[dict[str, Any]]) -> bool:
    node_set = set(nodes)
    graph: dict[int, set[int]] = {value: set() for value in nodes}
    for edge in topology_rows:
        first, second = int(edge["FromClusterID"]), int(edge["ToClusterID"])
        if first in node_set and second in node_set:
            graph[first].add(second)
            graph[second].add(first)
    visited: set[int] = set()
    queue = deque([nodes[0]])
    while queue:
        value = queue.popleft()
        if value in visited:
            continue
        visited.add(value)
        queue.extend(sorted(graph[value] - visited))
    return visited == node_set


def build_candidates(
    surface_records: list[dict[str, Any]],
    topology_rows: list[dict[str, Any]],
    points: np.ndarray,
) -> list[dict[str, Any]]:
    by_role = {str(value["semantic_role"]): value for value in surface_records}
    all_min, all_max = points.min(axis=0), points.max(axis=0)

    def cluster(role: str) -> int:
        return int(by_role[role]["cluster_id"])

    base_roles = ["base_bottom", "back", "base_top", "right", "left", "base_end"]
    upright_roles = ["back", "upright_top", "right", "upright_front", "left"]
    base_clusters = sorted(cluster(value) for value in base_roles)
    upright_clusters = sorted(cluster(value) for value in upright_roles)
    if not graph_connected(base_clusters, topology_rows) or not graph_connected(upright_clusters, topology_rows):
        raise ValueError("板件候選的來源平面未形成可追溯的拓樸連通子圖。")

    base_height = abs(float(by_role["base_top"]["model"]["center"][2] - by_role["base_bottom"]["model"]["center"][2]))
    upright_width = abs(float(by_role["upright_front"]["model"]["center"][1] - by_role["back"]["model"]["center"][1]))
    # The upright plate overlaps the base plate in the canonical Union decomposition;
    # its lower datum is therefore the model/base bottom, not the exposed base-top face.
    upright_height = abs(float(by_role["upright_top"]["model"]["center"][2] - by_role["base_bottom"]["model"]["center"][2]))
    rows: list[dict[str, Any]] = [
        {
            "CandidateID": "LB_U01",
            "PrimitiveType": "BasePlate",
            "RelatedClusters": ";".join(str(value) for value in base_clusters),
            "Length": float(all_max[0] - all_min[0]),
            "Width": float(all_max[1] - all_min[1]),
            "Height": base_height,
            "Radius": math.nan,
            "Depth": math.nan,
            "BooleanType": "Union",
            "InferenceRule": "opposing planes + connected OrthogonalAdjacency shell",
            "RuleStatus": "PASS",
        },
        {
            "CandidateID": "LB_U02",
            "PrimitiveType": "UprightPlate",
            "RelatedClusters": ";".join(str(value) for value in upright_clusters),
            "Length": float(all_max[0] - all_min[0]),
            "Width": upright_width,
            "Height": upright_height,
            "Radius": math.nan,
            "Depth": math.nan,
            "BooleanType": "Union",
            "InferenceRule": "opposing planes + connected OrthogonalAdjacency shell",
            "RuleStatus": "PASS",
        },
    ]

    endcaps: dict[int, list[int]] = defaultdict(list)
    for edge in topology_rows:
        if edge["EdgeType"] != "EndCap":
            continue
        first, second = int(edge["FromClusterID"]), int(edge["ToClusterID"])
        first_surface = next(value for value in surface_records if int(value["cluster_id"]) == first)
        second_surface = next(value for value in surface_records if int(value["cluster_id"]) == second)
        if first_surface["model"]["geometry"] == "cylinder":
            endcaps[first].append(second)
        elif second_surface["model"]["geometry"] == "cylinder":
            endcaps[second].append(first)

    cylinder_specs = {
        "outer_boss": ("LB_U03", "Cylinder", "Union"),
        "base_hole": ("LB_D01", "BasePlateHole", "Difference"),
        "upright_hole": ("LB_D02", "UprightPlateHole", "Difference"),
    }
    for role, (candidate_id, primitive_type, boolean_type) in cylinder_specs.items():
        surface = by_role[role]
        cylinder_id = int(surface["cluster_id"])
        cap_ids = sorted(endcaps.get(cylinder_id, []))
        if len(cap_ids) != 2:
            raise ValueError(f"{role} 未由兩個 EndCap 關係封閉：{cap_ids}")
        axis = np.asarray(surface["model"]["axis"])
        cap_coordinates = []
        for cap_id in cap_ids:
            cap = next(value for value in surface_records if int(value["cluster_id"]) == cap_id)
            cap_coordinates.append(float(np.asarray(cap["model"]["center"]) @ axis))
        rows.append(
            {
                "CandidateID": candidate_id,
                "PrimitiveType": primitive_type,
                "RelatedClusters": ";".join(str(value) for value in sorted([cylinder_id, *cap_ids])),
                "Length": math.nan,
                "Width": math.nan,
                "Height": math.nan,
                "Radius": float(surface["model"]["radius"]),
                "Depth": abs(cap_coordinates[1] - cap_coordinates[0]),
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
        raise ValueError(f"L 型板輸入不符合第三章資料結構：missing={missing}, rows={len(frame)}")
    points = frame[["X", "Y", "Z"]].to_numpy(float)
    normals = frame[["NX", "NY", "NZ"]].to_numpy(float)
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    old_clusters = frame["ClusterID"].to_numpy(int)

    initial_labels = region_growing(points, normals)
    surfaces, residual_indices = merge_surface_components(initial_labels, points, normals)
    cluster_ids = assign_cluster_ids(surfaces, old_clusters)
    surface_records: list[dict[str, Any]] = []
    for indices, cluster_id in sorted(zip(surfaces, cluster_ids), key=lambda value: value[1]):
        model = fit_component(indices, points, normals)
        if model is None:
            raise ValueError(f"Cluster {cluster_id} 無法通過平面或圓柱面型驗收。")
        sense = cylinder_surface_sense(model, points[indices], normals[indices]) if model["geometry"] == "cylinder" else math.nan
        surface_records.append(
            {
                "indices": indices,
                "cluster_id": int(cluster_id),
                "model": model,
                "surface_sense": sense,
            }
        )
    if len(surface_records) != 12:
        raise ValueError(f"第三章方法得到 {len(surface_records)} 個有效面，預期 L 型板為 12 個。")
    semantic_roles(surface_records)

    new_clusters = np.full(len(frame), -1, dtype=int)
    for surface in surface_records:
        new_clusters[surface["indices"]] = int(surface["cluster_id"])
    if residual_indices:
        new_clusters[np.asarray(residual_indices, dtype=int)] = -1

    result = frame.copy()
    result["ClusterID"] = new_clusters
    if "FeatureType" in result.columns:
        feature_by_cluster = {int(value["cluster_id"]): FEATURE_NAMES[str(value["semantic_role"])] for value in surface_records}
        result["FeatureType"] = [feature_by_cluster.get(int(value), "Residual") for value in new_clusters]
    result_path = output_dir / "Result_L_Bracket_chapter3_verified.csv"
    result.to_csv(result_path, index=False, encoding="utf-8")

    boundary_counts: dict[int, int] = {}
    for surface in surface_records:
        indices = surface["indices"]
        boundary = np.zeros(len(indices), dtype=bool)
        for other in surface_records:
            if other is surface:
                continue
            distance = cKDTree(points[other["indices"]]).query(points[indices], k=1)[0]
            boundary |= distance <= DISTANCE_THRESHOLD_MM
        boundary_counts[int(surface["cluster_id"])] = int(np.sum(boundary))

    face_rows: list[dict[str, Any]] = []
    for surface in surface_records:
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
                "BoundaryPointCount": boundary_counts[int(surface["cluster_id"])],
                "CenterX": center[0], "CenterY": center[1], "CenterZ": center[2],
                "NX": normal[0], "NY": normal[1], "NZ": normal[2],
                "AxisX": axis[0], "AxisY": axis[1], "AxisZ": axis[2],
                "MinX": cluster_points[:, 0].min(), "MaxX": cluster_points[:, 0].max(),
                "MinY": cluster_points[:, 1].min(), "MaxY": cluster_points[:, 1].max(),
                "MinZ": cluster_points[:, 2].min(), "MaxZ": cluster_points[:, 2].max(),
                "Radius": float(model["radius"]) if model["geometry"] == "cylinder" else math.nan,
                "AxisMin": float(model["axis_min"]), "AxisMax": float(model["axis_max"]),
                "SurfaceSense": float(surface["surface_sense"]),
                "FitResidualMax": float(np.max(model["residual"])),
                "FitResidualMedian": float(np.median(model["residual"])),
                "NormalConsistencyMin": float(np.min(model["alignment"])),
                "ValidationStatus": "PASS",
            }
        )
    face_path = output_dir / "FaceSummary_L_Bracket_chapter3_verified.csv"
    face_fields = [
        "ClusterID", "FeatureType", "SemanticRole", "PointCount", "BoundaryPointCount",
        "CenterX", "CenterY", "CenterZ", "NX", "NY", "NZ", "AxisX", "AxisY", "AxisZ",
        "MinX", "MaxX", "MinY", "MaxY", "MinZ", "MaxZ", "Radius", "AxisMin", "AxisMax",
        "SurfaceSense", "FitResidualMax", "FitResidualMedian", "NormalConsistencyMin", "ValidationStatus",
    ]
    write_csv(face_path, face_rows, face_fields)

    topology_rows = build_topology(surface_records, points)
    topology_path = output_dir / "TopologyEdges_L_Bracket_chapter3_verified.csv"
    topology_fields = [
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "DistanceThreshold", "DirectionThreshold", "RuleStatus", "InferenceRule",
    ]
    write_csv(topology_path, topology_rows, topology_fields)

    candidate_rows = build_candidates(surface_records, topology_rows, points)
    candidate_path = output_dir / "PrimitiveCandidates_L_Bracket_chapter3_verified.csv"
    candidate_fields = [
        "CandidateID", "PrimitiveType", "RelatedClusters", "Length", "Width", "Height",
        "Radius", "Depth", "BooleanType", "InferenceRule", "RuleStatus",
    ]
    write_csv(candidate_path, candidate_rows, candidate_fields)

    csg_path = output_dir / "CSGTree_L_Bracket_chapter3_verified.json"
    write_json(
        csg_path,
        {
            "case": "L-Bracket",
            "source": "PrimitiveCandidates_L_Bracket_chapter3_verified.csv",
            "canonicalization": "Union children sorted by CandidateID; Difference subtractors sorted by CandidateID",
            "tree": canonical_csg_tree(candidate_rows),
        },
    )

    trace_rows: list[dict[str, Any]] = []
    for old_cluster in sorted(set(old_clusters.tolist())):
        old_mask = old_clusters == old_cluster
        for new_cluster in sorted(set(new_clusters[old_mask].tolist())):
            trace_rows.append(
                {
                    "OriginalClusterID": int(old_cluster),
                    "VerifiedClusterID": int(new_cluster),
                    "PointCount": int(np.sum(old_mask & (new_clusters == new_cluster))),
                    "Action": "保留" if int(old_cluster) == int(new_cluster) else ("列為殘留" if new_cluster < 0 else "依第三章規則重新歸屬"),
                    "Reason": "公式(3-3)區域成長後，依1.5 mm幾何殘差與既有2.0 mm容許值整併同一曲面片段；未讀取STL真值",
                }
            )
    trace_path = output_dir / "CorrectionTrace_L_Bracket_chapter3.csv"
    write_csv(trace_path, trace_rows, ["OriginalClusterID", "VerifiedClusterID", "PointCount", "Action", "Reason"])

    outputs = [result_path, face_path, topology_path, candidate_path, csg_path, trace_path]
    manifest_path = output_dir / "MethodInferenceManifest_L_Bracket_chapter3.json"
    write_json(
        manifest_path,
        {
            "schema_version": "3.0",
            "case": "L-Bracket",
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
            "counts": {
                "points": len(frame),
                "initial_region_components": len(set(initial_labels.tolist())),
                "accepted_faces": len(surface_records),
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
    parser = argparse.ArgumentParser(description="Infer the L-Bracket result strictly from the Chapter 3 point/face/topology rules.")
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    build_outputs(arguments.result.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
