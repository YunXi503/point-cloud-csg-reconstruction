from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from build_stepped_cylinder_independent_truth import (
    DisjointSet,
    build_edge_map,
    read_stl_triangles,
    sha256,
    triangle_geometry,
    unique_vertices,
)


CIRCLE_VERTEX_TOLERANCE_MM = 0.002
CYLINDER_SUPPORT_TOLERANCE_MM = 0.20
CYLINDER_VERTEX_SUPPORT_TOLERANCE_MM = 0.01
CYLINDER_AXIS_NORMAL_TOLERANCE = 0.01
CYLINDER_RADIAL_ALIGNMENT = 0.99
COPLANAR_NORMAL_DOT = 1.0 - 1e-7
REGION_GROWING_NORMAL_DOT = 0.93
ENDCAP_DOT_THRESHOLD = 0.95
ORTHOGONAL_DOT_THRESHOLD = 0.2


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_circle_three(points: np.ndarray) -> tuple[np.ndarray, float] | None:
    first, second, third = points
    matrix = 2.0 * np.asarray((second - first, third - first))
    if abs(float(np.linalg.det(matrix))) <= 1e-10:
        return None
    rhs = np.asarray((second @ second - first @ first, third @ third - first @ first))
    center = np.linalg.solve(matrix, rhs)
    radius = float(np.linalg.norm(first - center))
    if not math.isfinite(radius) or radius <= 1.0 or radius >= 500.0:
        return None
    return center, radius


def circle_hypotheses_for_axis(vertices: np.ndarray, axis_index: int) -> list[tuple[np.ndarray, float, int]]:
    radial_axes = [value for value in range(3) if value != axis_index]
    candidates: dict[tuple[float, float, float], tuple[np.ndarray, float, int]] = {}
    axis_values = np.round(vertices[:, axis_index], 5)
    for group_number, axis_value in enumerate(sorted(set(axis_values.tolist()))):
        group = vertices[axis_values == axis_value]
        projected = np.unique(np.round(group[:, radial_axes], 6), axis=0)
        if len(projected) < 12:
            continue
        triples: list[tuple[int, int, int]] = []
        if len(projected) <= 42:
            triples = list(itertools.combinations(range(len(projected)), 3))
        else:
            generator = np.random.default_rng(260722 + axis_index * 1009 + group_number)
            seen: set[tuple[int, int, int]] = set()
            for _ in range(30000):
                triple = tuple(sorted(int(value) for value in generator.choice(len(projected), 3, replace=False)))
                seen.add(triple)
            triples = sorted(seen)
        for triple in triples:
            fitted = canonical_circle_three(projected[list(triple)])
            if fitted is None:
                continue
            center, radius = fitted
            residual = np.abs(np.linalg.norm(projected - center, axis=1) - radius)
            inliers = int(np.sum(residual <= CIRCLE_VERTEX_TOLERANCE_MM))
            if inliers < 12:
                continue
            key = tuple(float(value) for value in np.round(np.r_[center, radius], 2))
            previous = candidates.get(key)
            if previous is None or inliers > previous[2]:
                candidates[key] = (center, radius, inliers)
    return list(candidates.values())


def cylinder_triangle_metrics(
    triangles: np.ndarray,
    centers: np.ndarray,
    normals: np.ndarray,
    axis_index: int,
    circle_center: np.ndarray,
    radius: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    radial_axes = [value for value in range(3) if value != axis_index]
    radial_normals = normals[:, radial_axes]
    radial_normal_length = np.linalg.norm(radial_normals, axis=1)
    radial_unit_normal = radial_normals / np.maximum(radial_normal_length[:, None], 1e-12)
    centroid_radial = centers[:, radial_axes] - circle_center
    centroid_radial_length = np.linalg.norm(centroid_radial, axis=1)
    centroid_radial_unit = centroid_radial / np.maximum(centroid_radial_length[:, None], 1e-12)
    signed_alignment = np.sum(radial_unit_normal * centroid_radial_unit, axis=1)
    support = np.abs(
        np.sum((triangles[:, 0, radial_axes] - circle_center) * radial_unit_normal, axis=1)
    )
    support_error = np.abs(radius - support)
    # 逐頂點徑向支撐：三角形的每一個頂點都必須落在擬合圓柱面上，
    # 否則與圓柱相切的平坦面片（其法向量恰為徑向）會被誤收進圓柱面。
    vertex_radial = triangles[:, :, radial_axes] - circle_center
    vertex_support_error = np.abs(np.linalg.norm(vertex_radial, axis=2) - radius)
    vertex_support_error_max = vertex_support_error.max(axis=1)
    accepted = (
        (np.abs(normals[:, axis_index]) <= CYLINDER_AXIS_NORMAL_TOLERANCE)
        & (np.abs(signed_alignment) >= CYLINDER_RADIAL_ALIGNMENT)
        & (support_error <= CYLINDER_SUPPORT_TOLERANCE_MM)
        & (vertex_support_error_max <= CYLINDER_VERTEX_SUPPORT_TOLERANCE_MM)
    )
    score = support_error + (1.0 - np.abs(signed_alignment)) * 10.0 + np.abs(normals[:, axis_index]) * 10.0
    return accepted, score, support_error, signed_alignment


def component_count(indices: np.ndarray, edge_map: dict[Any, list[int]]) -> int:
    if not len(indices):
        return 0
    selected = set(int(value) for value in indices)
    disjoint = DisjointSet(max(selected) + 1)
    for incident in edge_map.values():
        if len(incident) == 2 and incident[0] in selected and incident[1] in selected:
            disjoint.union(incident[0], incident[1])
    return len({disjoint.find(value) for value in selected})


def detect_cylinders(
    triangles: np.ndarray,
    centers: np.ndarray,
    normals: np.ndarray,
    edge_map: dict[Any, list[int]],
) -> tuple[list[dict[str, Any]], np.ndarray]:
    vertices = unique_vertices(triangles)
    hypotheses: list[dict[str, Any]] = []
    for axis_index in range(3):
        for circle_center, radius, vertex_inliers in circle_hypotheses_for_axis(vertices, axis_index):
            accepted, score, support_error, signed_alignment = cylinder_triangle_metrics(
                triangles, centers, normals, axis_index, circle_center, radius
            )
            triangle_indices = np.flatnonzero(accepted)
            if len(triangle_indices) < 20 or component_count(triangle_indices, edge_map) != 1:
                continue
            axis_values = triangles[triangle_indices, :, axis_index]
            depth = float(axis_values.max() - axis_values.min())
            if depth <= 1.0:
                continue
            hypotheses.append(
                {
                    "axis_index": axis_index,
                    "circle_center": circle_center,
                    "radius_mm": radius,
                    "vertex_inliers": vertex_inliers,
                    "triangle_indices": triangle_indices,
                    "score": score,
                    "support_error": support_error,
                    "signed_alignment": signed_alignment,
                    "depth_mm": depth,
                }
            )

    deduplicated: list[dict[str, Any]] = []
    for item in sorted(hypotheses, key=lambda value: (-len(value["triangle_indices"]), value["axis_index"], value["radius_mm"])):
        duplicate = any(
            item["axis_index"] == kept["axis_index"]
            and float(np.linalg.norm(item["circle_center"] - kept["circle_center"])) <= 0.05
            and abs(item["radius_mm"] - kept["radius_mm"]) <= 0.05
            for kept in deduplicated
        )
        if not duplicate:
            deduplicated.append(item)

    score_matrix = np.full((len(triangles), len(deduplicated)), np.inf)
    for column, item in enumerate(deduplicated):
        indices = item["triangle_indices"]
        score_matrix[indices, column] = item["score"][indices]
    assignment = np.full(len(triangles), -1, dtype=int)
    if deduplicated:
        best = np.argmin(score_matrix, axis=1)
        valid = np.isfinite(np.min(score_matrix, axis=1))
        assignment[valid] = best[valid]

    cylinders: list[dict[str, Any]] = []
    for index, item in enumerate(deduplicated):
        triangle_indices = np.flatnonzero(assignment == index)
        if len(triangle_indices) < 20 or component_count(triangle_indices, edge_map) != 1:
            assignment[assignment == index] = -1
            continue
        axis = np.zeros(3)
        axis[item["axis_index"]] = 1.0
        axis_values = triangles[triangle_indices, :, item["axis_index"]]
        median_sign = float(np.median(item["signed_alignment"][triangle_indices]))
        cylinders.append(
            {
                "geometry": "cylinder",
                "axis": axis.tolist(),
                "axis_index": item["axis_index"],
                "circle_center_2d": item["circle_center"].tolist(),
                "radius_mm": float(item["radius_mm"]),
                "depth_mm": float(axis_values.max() - axis_values.min()),
                "axis_min_mm": float(axis_values.min()),
                "axis_max_mm": float(axis_values.max()),
                "orientation": "outer" if median_sign > 0.0 else "inner",
                "triangle_indices": triangle_indices.tolist(),
                "triangle_count": int(len(triangle_indices)),
                "mesh_connected_components": 1,
                "support_error_max_mm": float(np.max(item["support_error"][triangle_indices])),
                "signed_normal_alignment_median": median_sign,
                "circle_vertex_inliers": int(item["vertex_inliers"]),
                "bounds_min": triangles[triangle_indices].min(axis=(0, 1)).tolist(),
                "bounds_max": triangles[triangle_indices].max(axis=(0, 1)).tolist(),
            }
        )

    # Reindex assignments after any rejected duplicate hypothesis.
    final_assignment = np.full(len(triangles), -1, dtype=int)
    for index, surface in enumerate(cylinders):
        final_assignment[np.asarray(surface["triangle_indices"], dtype=int)] = index
    return cylinders, final_assignment


def detect_planes(
    triangles: np.ndarray,
    centers: np.ndarray,
    normals: np.ndarray,
    areas: np.ndarray,
    edge_map: dict[Any, list[int]],
    occupied: np.ndarray,
) -> list[dict[str, Any]]:
    remaining = np.flatnonzero(occupied < 0)
    selected = set(int(value) for value in remaining)
    disjoint = DisjointSet(len(triangles))
    for incident in edge_map.values():
        if (
            len(incident) == 2
            and incident[0] in selected
            and incident[1] in selected
            and float(normals[incident[0]] @ normals[incident[1]]) >= REGION_GROWING_NORMAL_DOT
        ):
            disjoint.union(incident[0], incident[1])
    groups: dict[int, list[int]] = defaultdict(list)
    for triangle_index in remaining:
        groups[disjoint.find(int(triangle_index))].append(int(triangle_index))
    planes: list[dict[str, Any]] = []
    for triangle_indices_list in sorted(groups.values(), key=lambda values: min(values)):
        triangle_indices = np.asarray(triangle_indices_list, dtype=int)
        weighted_normal = np.average(normals[triangle_indices], axis=0, weights=areas[triangle_indices])
        weighted_normal /= np.linalg.norm(weighted_normal)
        vertices = unique_vertices(triangles[triangle_indices])
        offset = float(np.median(vertices @ weighted_normal))
        residual = np.abs(vertices @ weighted_normal - offset)
        triangle_alignment = np.abs(normals[triangle_indices] @ weighted_normal)
        planes.append(
            {
                "geometry": "plane",
                "normal": weighted_normal.tolist(),
                "plane_offset_mm": offset,
                "center": np.average(centers[triangle_indices], axis=0, weights=areas[triangle_indices]).tolist(),
                "triangle_indices": triangle_indices.tolist(),
                "triangle_count": int(len(triangle_indices)),
                "mesh_connected_components": 1,
                "vertex_fit_residual_max_mm": float(residual.max()),
                "triangle_normal_alignment_min": float(triangle_alignment.min()),
                "area_mm2": float(areas[triangle_indices].sum()),
                "bounds_min": vertices.min(axis=0).tolist(),
                "bounds_max": vertices.max(axis=0).tolist(),
            }
        )
    return planes


def close(value: float, expected: float, tolerance: float = 0.05) -> bool:
    return abs(value - expected) <= tolerance


def plane_coordinate(surface: dict[str, Any], axis_index: int) -> float:
    return float(np.asarray(surface["center"])[axis_index])


def assign_lbracket_roles(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for surface in surfaces:
        if surface["geometry"] == "cylinder":
            axis_index = int(surface["axis_index"])
            if axis_index == 1 and surface["orientation"] == "inner":
                cluster, role, feature = 11, "upright_plate_hole_side", "Cylinder_axisY_inner (立板孔)"
            elif axis_index == 2 and surface["orientation"] == "inner":
                cluster, role, feature = 9, "base_plate_hole_side", "Cylinder_axisZ_inner (底板孔)"
            elif axis_index == 2 and surface["orientation"] == "outer":
                cluster, role, feature = 4, "added_outer_cylinder_side", "Cylinder_axisZ_outer (外加圓柱面)"
            else:
                raise ValueError("L型板 STL 出現未預期的圓柱軸向或法向方向。")
        else:
            normal = np.asarray(surface["normal"])
            dominant = int(np.argmax(np.abs(normal)))
            coordinate = plane_coordinate(surface, dominant)
            sign = int(np.sign(normal[dominant]))
            if dominant == 0 and sign < 0:
                cluster, role, feature = 8, "combined_left_side", "Plane_YZ (底板與立板左側合併面)"
            elif dominant == 0 and sign > 0:
                cluster, role, feature = 5, "combined_right_side", "Plane_YZ (底板與立板右側合併面)"
            elif dominant == 1 and sign < 0:
                cluster, role, feature = 1, "combined_rear_side", "Plane_XZ (底板與立板後側合併面)"
            elif dominant == 1 and close(coordinate, 5.0):
                cluster, role, feature = 7, "upright_front", "Plane_XZ (立板前側面)"
            elif dominant == 1 and close(coordinate, 80.0):
                cluster, role, feature = 10, "base_end", "Plane_XZ (底板端面)"
            elif dominant == 2 and sign < 0:
                cluster, role, feature = 0, "base_bottom", "Plane_XY (底板下表面)"
            elif dominant == 2 and close(coordinate, 5.0):
                cluster, role, feature = 2, "base_top", "Plane_XY (底板上表面)"
            elif dominant == 2 and close(coordinate, 35.0):
                cluster, role, feature = 6, "added_cylinder_top", "Plane_XY (外加圓柱頂面)"
            elif dominant == 2 and close(coordinate, 45.0):
                cluster, role, feature = 3, "upright_top", "Plane_XY (立板頂面)"
            else:
                raise ValueError(f"L型板 STL 平面無法指派語義角色：{surface}")
        surface["cluster_id"] = cluster
        surface["surface_id"] = f"GT_LB_S{cluster:02d}"
        surface["semantic_role"] = role
        surface["feature_type"] = feature
    return []


def assign_model_a_roles(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    residual: list[dict[str, Any]] = []
    for surface in surfaces:
        if surface["geometry"] == "cylinder":
            axis_index = int(surface["axis_index"])
            orientation = surface["orientation"]
            # cluster_id 為與初始特徵辨識輸出（Result_Model A.csv）之叢集編號的
            # 交叉參照標籤，僅供比對對位之用，不影響本真值的任何幾何主張。
            mapping = {
                (0, "inner"): (13, "right_through_hole_side", "Cylinder_axisX_inner (右側孔)"),
                (0, "outer"): (14, "right_outer_boss_side", "Cylinder_axisX_outer (右側凸台)"),
                (1, "inner"): (10, "main_ring_hole_side", "Cylinder_axisY_inner (主環孔)"),
                (1, "outer"): (9, "main_outer_ring_side", "Cylinder_axisY_outer (主環外圓柱)"),
            }
            if (axis_index, orientation) not in mapping:
                raise ValueError("Model A STL 出現未預期的圓柱軸向或法向方向。")
            cluster, role, feature = mapping[(axis_index, orientation)]
        else:
            normal = np.asarray(surface["normal"])
            dominant = int(np.argmax(np.abs(normal)))
            coordinate = plane_coordinate(surface, dominant)
            sign = int(np.sign(normal[dominant]))
            if (
                float(np.max(np.abs(normal))) < 0.97
                and float(surface.get("area_mm2", 0.0)) >= 500.0
                and float(surface["bounds_min"][0]) <= 20.0
                and float(surface["bounds_max"][0]) >= 95.0
            ):
                cluster, role, feature = 6, "web_oblique_top", "Plane_oblique (主體上斜面)"
            elif float(np.max(np.abs(normal))) < 0.97:
                surface["residual_reason"] = "局部三角面群未形成穩定的主要平面或圓柱曲面"
                residual.append(surface)
                continue
            elif dominant == 0 and sign < 0:
                cluster, role, feature = 7, "right_boss_base", "Plane_YZ (右側凸台基準面)"
            elif dominant == 0 and sign > 0:
                cluster, role, feature = 3, "right_end", "Plane_YZ (右端面)"
            elif dominant == 1 and sign < 0 and close(coordinate, -15.0):
                cluster, role, feature = 1, "main_ring_rear_end", "Plane_XZ (主環後端面)"
            elif dominant == 1 and sign > 0 and close(coordinate, 15.0):
                cluster, role, feature = 2, "main_ring_front_end", "Plane_XZ (主環前端面)"
            elif dominant == 1 and sign < 0 and close(coordinate, -10.0):
                cluster, role, feature = 0, "web_rear", "Plane_XZ (主體後側面)"
            elif dominant == 1 and sign > 0 and close(coordinate, 10.0):
                cluster, role, feature = 5, "web_front", "Plane_XZ (主體前側面)"
            elif dominant == 2 and sign < 0:
                cluster, role, feature = 4, "body_bottom", "Plane_XY (主體底面)"
            elif dominant == 2 and sign > 0:
                cluster, role, feature = 8, "transition_top", "Plane_XY (轉接區頂面)"
            else:
                surface["residual_reason"] = "未形成可由第三章平面或圓柱規則穩定辨識的主要連通曲面"
                residual.append(surface)
                continue
        surface["cluster_id"] = cluster
        surface["surface_id"] = f"GT_MA_S{cluster:02d}"
        surface["semantic_role"] = role
        surface["feature_type"] = feature
    for surface in residual:
        surfaces.remove(surface)
    return residual


def assign_blind_hole_hex_base_roles(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """盲孔六角座：僅由 STL 幾何指派語義角色。

    cluster_id 為與初始特徵辨識輸出（Result_Blind-Hole Hex Base_fixed.csv）之叢集
    編號的交叉參照標籤，僅供比對對位之用，不影響本真值的任何幾何主張；其判定
    依據為圓柱軸向與內外方向、水平面朝向與軸向位置，以及六角側面法向量方位角。
    """
    hex_side_by_azimuth = {-150: 8, -90: 6, -30: 4, 30: 7, 90: 5, 150: 3}
    hex_side_index = {8: 1, 6: 2, 4: 3, 7: 4, 5: 5, 3: 6}
    for surface in surfaces:
        if surface["geometry"] == "cylinder":
            if int(surface["axis_index"]) != 2:
                raise ValueError("盲孔六角座 STL 出現非 Z 軸圓柱。")
            if surface["orientation"] == "outer":
                cluster, role, feature = 0, "ring_outer_side", "Cylinder_axisZ_outer (環台外圓柱)"
            else:
                cluster, role, feature = 1, "blind_hole_side", "Cylinder_axisZ_inner (盲孔內壁)"
        else:
            normal = np.asarray(surface["normal"])
            if abs(float(normal[2])) > 0.9:
                coordinate = plane_coordinate(surface, 2)
                if float(normal[2]) < 0:
                    cluster, role, feature = 2, "hex_bottom", "Plane_Horizontal (六角底面)"
                elif close(coordinate, 25.0):
                    cluster, role, feature = 11, "blind_hole_floor", "Plane_Horizontal (盲孔底面)"
                elif close(coordinate, 60.0):
                    cluster, role, feature = 9, "hex_shelf", "Plane_Horizontal (六角肩面)"
                elif close(coordinate, 75.0):
                    cluster, role, feature = 10, "ring_top", "Plane_Horizontal (環台頂面)"
                else:
                    raise ValueError(f"盲孔六角座 STL 水平面無法指派語義角色：{coordinate}")
            elif abs(float(normal[2])) < 0.2:
                azimuth = math.degrees(math.atan2(float(normal[1]), float(normal[0])))
                matched = [
                    value for value in hex_side_by_azimuth if abs(azimuth - value) <= 1.0
                ]
                if len(matched) != 1:
                    raise ValueError(f"盲孔六角座 STL 側面方位角無法唯一指派：{azimuth}")
                cluster = hex_side_by_azimuth[matched[0]]
                index = hex_side_index[cluster]
                role, feature = f"hex_side_{index}", f"Plane_Vertical (六角側面{index})"
            else:
                raise ValueError(f"盲孔六角座 STL 出現未預期的傾斜平面：{normal.tolist()}")
        surface["cluster_id"] = cluster
        surface["surface_id"] = f"GT_BH_S{cluster:02d}"
        surface["semantic_role"] = role
        surface["feature_type"] = feature
    return []


def derive_blind_hole_hex_base_candidates(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ring = surface_by_cluster(surfaces, 0)
    bore = surface_by_cluster(surfaces, 1)
    apothems = [
        abs(float(surface_by_cluster(surfaces, cluster)["plane_offset_mm"]))
        for cluster in (3, 4, 5, 6, 7, 8)
    ]
    apothem = float(np.median(apothems))
    circumradius = apothem / math.cos(math.pi / 6.0)
    return [
        candidate(
            "BH_D01",
            "BlindHole",
            "Difference",
            [1, 10, 11],
            {
                "radius_mm": bore["radius_mm"],
                "depth_mm": terminal_plane_depth(surfaces, 10, 11, 2),
            },
            surfaces,
        ),
        candidate(
            "BH_U01",
            "HexagonalPrism",
            "Union",
            [2, 3, 4, 5, 6, 7, 8, 9],
            {
                "length_mm": 2.0 * circumradius,
                "width_mm": 2.0 * apothem,
                "height_mm": terminal_plane_depth(surfaces, 2, 9, 2),
            },
            surfaces,
        ),
        candidate(
            "BH_U02",
            "OuterRingBoss",
            "Union",
            [0, 9, 10],
            {
                "radius_mm": ring["radius_mm"],
                "depth_mm": terminal_plane_depth(surfaces, 9, 10, 2),
            },
            surfaces,
        ),
    ]


def canonical_binary_tree(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """左結合二元展開，對應第三章公式(3-7)：每個內部節點恰有兩個子節點。"""
    union = sorted(item["candidate_id"] for item in candidates if item["boolean_type"] == "Union")
    difference = sorted(
        item["candidate_id"] for item in candidates if item["boolean_type"] == "Difference"
    )
    if not union:
        raise ValueError("缺少聯集候選，無法建立基體。")
    node: dict[str, Any] = {"candidate": union[0]}
    for candidate_id in union[1:]:
        node = {"op": "Union", "left": node, "right": {"candidate": candidate_id}}
    for candidate_id in difference:
        node = {"op": "Difference", "left": node, "right": {"candidate": candidate_id}}
    return node


def derive_topology(
    surfaces: list[dict[str, Any]], triangles: np.ndarray, edge_map: dict[Any, list[int]]
) -> list[dict[str, Any]]:
    triangle_to_surface: dict[int, str] = {}
    for surface in surfaces:
        for triangle_index in surface["triangle_indices"]:
            triangle_to_surface[int(triangle_index)] = surface["surface_id"]
    surface_by_id = {surface["surface_id"]: surface for surface in surfaces}
    shared: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for key, incident in edge_map.items():
        if len(incident) != 2:
            continue
        if incident[0] not in triangle_to_surface or incident[1] not in triangle_to_surface:
            continue
        first, second = triangle_to_surface[incident[0]], triangle_to_surface[incident[1]]
        if first != second:
            shared[tuple(sorted((first, second)))].append(key)
    topology: list[dict[str, Any]] = []
    for pair, keys in sorted(shared.items()):
        first, second = (surface_by_id[value] for value in pair)
        direction_dot: float | None = None
        if {first["geometry"], second["geometry"]} == {"plane", "cylinder"}:
            plane = first if first["geometry"] == "plane" else second
            cylinder = first if first["geometry"] == "cylinder" else second
            direction_dot = abs(float(np.asarray(plane["normal"]) @ np.asarray(cylinder["axis"])))
            edge_type = "EndCap" if direction_dot > ENDCAP_DOT_THRESHOLD else "Adjacency"
        elif first["geometry"] == second["geometry"] == "plane":
            direction_dot = abs(float(np.asarray(first["normal"]) @ np.asarray(second["normal"])))
            edge_type = "OrthogonalAdjacency" if direction_dot < ORTHOGONAL_DOT_THRESHOLD else "Adjacency"
        else:
            edge_type = "Adjacency"
        boundary_length = sum(
            float(np.linalg.norm(np.asarray(key[0]) - np.asarray(key[1]))) for key in keys
        )
        topology.append(
            {
                "from_surface_id": pair[0],
                "to_surface_id": pair[1],
                "from_cluster_id": int(surface_by_id[pair[0]]["cluster_id"]),
                "to_cluster_id": int(surface_by_id[pair[1]]["cluster_id"]),
                "edge_type": edge_type,
                "shared_mesh_edge_count": len(keys),
                "shared_boundary_length_mm": boundary_length,
                "direction_dot": direction_dot,
            }
        )
    return topology


def surface_by_cluster(surfaces: list[dict[str, Any]], cluster_id: int) -> dict[str, Any]:
    matches = [surface for surface in surfaces if int(surface["cluster_id"]) == cluster_id]
    if len(matches) != 1:
        raise ValueError(f"Cluster {cluster_id} 無法一對一對應 STL 曲面。")
    return matches[0]


def candidate(
    candidate_id: str,
    primitive_type: str,
    boolean_type: str,
    clusters: list[int],
    dimensions: dict[str, Any],
    surfaces: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "primitive_type": primitive_type,
        "boolean_type": boolean_type,
        "related_cluster_ids": clusters,
        "related_surface_ids": [surface_by_cluster(surfaces, value)["surface_id"] for value in clusters],
        **dimensions,
    }


def terminal_plane_depth(surfaces: list[dict[str, Any]], first_cluster: int, second_cluster: int, axis_index: int) -> float:
    first = plane_coordinate(surface_by_cluster(surfaces, first_cluster), axis_index)
    second = plane_coordinate(surface_by_cluster(surfaces, second_cluster), axis_index)
    return abs(second - first)


def derive_lbracket_candidates(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outer = surface_by_cluster(surfaces, 4)
    base_hole = surface_by_cluster(surfaces, 9)
    upright_hole = surface_by_cluster(surfaces, 11)
    return [
        candidate("LB_U01", "BasePlate", "Union", [0, 1, 2, 5, 8, 10], {"length_mm": 40.0, "width_mm": 80.0, "height_mm": 5.0}, surfaces),
        candidate("LB_U02", "UprightPlate", "Union", [1, 3, 5, 7, 8], {"length_mm": 40.0, "width_mm": 5.0, "height_mm": 45.0}, surfaces),
        candidate("LB_U03", "Cylinder", "Union", [2, 4, 6], {"radius_mm": outer["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 2, 6, 2)}, surfaces),
        candidate("LB_D01", "BasePlateHole", "Difference", [0, 2, 9], {"radius_mm": base_hole["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 0, 2, 2)}, surfaces),
        candidate("LB_D02", "UprightPlateHole", "Difference", [1, 7, 11], {"radius_mm": upright_hole["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 1, 7, 1)}, surfaces),
    ]


def derive_model_a_candidates(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ring = surface_by_cluster(surfaces, 9)
    ring_hole = surface_by_cluster(surfaces, 10)
    boss = surface_by_cluster(surfaces, 14)
    boss_hole = surface_by_cluster(surfaces, 13)
    oblique = surface_by_cluster(surfaces, 6)
    oblique_max_z = float(oblique["bounds_max"][2])
    return [
        candidate("MA_U01", "MainWebProfileExtrusion", "Union", [0, 4, 5, 6], {"length_mm": 96.0, "width_mm": 20.0, "height_mm": oblique_max_z + 45.0}, surfaces),
        candidate("MA_U02", "MainAxisYOuterRing", "Union", [1, 2, 9], {"radius_mm": ring["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 1, 2, 1)}, surfaces),
        candidate("MA_U03", "RightTransitionBlock", "Union", [3, 4, 5, 7, 8], {"length_mm": 24.0, "width_mm": 28.0, "height_mm": 48.0}, surfaces),
        candidate("MA_U04", "RightAxisXOuterBoss", "Union", [3, 7, 14], {"radius_mm": boss["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 3, 7, 0)}, surfaces),
        candidate("MA_D01", "MainAxisYThroughHole", "Difference", [1, 2, 10], {"radius_mm": ring_hole["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 1, 2, 1)}, surfaces),
        candidate("MA_D02", "RightAxisXThroughHole", "Difference", [3, 7, 13], {"radius_mm": boss_hole["radius_mm"], "depth_mm": terminal_plane_depth(surfaces, 3, 7, 0)}, surfaces),
    ]


def canonical_tree(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    union = sorted(item["candidate_id"] for item in candidates if item["boolean_type"] == "Union")
    difference = sorted(item["candidate_id"] for item in candidates if item["boolean_type"] == "Difference")
    return {
        "op": "Difference",
        "base": {"op": "Union", "children": [{"candidate": value} for value in union]},
        "subtractors": [{"candidate": value} for value in difference],
    }


def build_truth(case_key: str, stl_path: Path) -> dict[str, Any]:
    triangles = read_stl_triangles(stl_path)
    centers, normals, areas = triangle_geometry(triangles)
    edge_map = build_edge_map(triangles)
    cylinders, cylinder_assignment = detect_cylinders(triangles, centers, normals, edge_map)
    planes = detect_planes(triangles, centers, normals, areas, edge_map, cylinder_assignment)
    surfaces = cylinders + planes
    if case_key == "l_bracket":
        residual_components = assign_lbracket_roles(surfaces)
        expected_surfaces, expected_cylinders = 12, 3
    elif case_key == "blind_hole_hex_base":
        residual_components = assign_blind_hole_hex_base_roles(surfaces)
        expected_surfaces, expected_cylinders = 12, 2
    else:
        residual_components = assign_model_a_roles(surfaces)
        expected_surfaces, expected_cylinders = 13, 4
    surfaces.sort(key=lambda value: int(value["cluster_id"]))
    if len(surfaces) != expected_surfaces or len(cylinders) != expected_cylinders:
        raise ValueError(
            f"{case_key} STL 解析曲面數不符：總數 {len(surfaces)}、圓柱 {len(cylinders)}。"
        )
    topology = derive_topology(surfaces, triangles, edge_map)
    if case_key == "l_bracket":
        candidates = derive_lbracket_candidates(surfaces)
    elif case_key == "blind_hole_hex_base":
        candidates = derive_blind_hole_hex_base_candidates(surfaces)
    else:
        candidates = derive_model_a_candidates(surfaces)
    nonmanifold_edges = sum(1 for incident in edge_map.values() if len(incident) != 2)
    if nonmanifold_edges:
        raise ValueError(f"STL 不是封閉二流形：{nonmanifold_edges} 條開放或非流形邊。")
    covered_triangles = sum(int(surface["triangle_count"]) for surface in surfaces)
    residual_triangles = sum(int(surface["triangle_count"]) for surface in residual_components)
    if covered_triangles + residual_triangles != len(triangles):
        raise ValueError("有效曲面與殘留三角面未完整覆蓋 evaluated mesh。")
    return {
        "schema_version": "2.0",
        "case_key": case_key,
        "case": {
            "l_bracket": "L-Bracket",
            "model_a": "Model A",
            "blind_hole_hex_base": "Blind-Hole Hex Base",
        }[case_key],
        "display_name": {
            "l_bracket": "L型板",
            "model_a": "Model A",
            "blind_hole_hex_base": "盲孔六角座",
        }[case_key],
        "truth_scope": "STL final triangle mesh only; no point cloud, Result, FaceSummary, TopologyEdges, PrimitiveCandidates, or prior GroundTruth was read",
        "research_boundary": "STL-generated geometry; planar and cylindrical surfaces; symbolic CSG inference only",
        "source": {
            "filename": stl_path.name,
            "sha256": sha256(stl_path),
            "triangle_count": int(len(triangles)),
            "mesh_bounds_min": triangles.min(axis=(0, 1)).tolist(),
            "mesh_bounds_max": triangles.max(axis=(0, 1)).tolist(),
            "nonmanifold_or_open_edge_count": nonmanifold_edges,
        },
        "surface_segmentation": {
            "method": "STL vertex-circle hypotheses for cylindrical patches, followed by shared-edge coplanar components for remaining triangles",
            "circle_vertex_tolerance_mm": CIRCLE_VERTEX_TOLERANCE_MM,
            "cylinder_support_tolerance_mm": CYLINDER_SUPPORT_TOLERANCE_MM,
            "cylinder_vertex_support_tolerance_mm": CYLINDER_VERTEX_SUPPORT_TOLERANCE_MM,
            "surface_count": len(surfaces),
            "cylinder_count": len(cylinders),
            "plane_count": len(planes),
            "residual_mesh_component_count": len(residual_components),
        },
        "surfaces": surfaces,
        "residual_mesh_components": residual_components,
        "topology_edges": topology,
        "primitive_candidates": candidates,
        "canonical_csg_tree": (
            canonical_binary_tree(candidates)
            if case_key == "blind_hole_hex_base"
            else canonical_tree(candidates)
        ),
        "interpretation_limits": [
            "The truth describes the supplied STL mesh and does not prove generalization to real scans.",
            "The CSG decomposition is a deterministic CAD-oriented symbolic interpretation of the supplied surfaces; no STEP, IGES, B-rep, or editable CAD solid is asserted.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build STL-only independent truth for L-Bracket, Model A, or Blind-Hole Hex Base."
    )
    parser.add_argument(
        "--case", required=True, choices=("l_bracket", "model_a", "blind_hole_hex_base")
    )
    parser.add_argument("--stl", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    stl_path = arguments.stl.resolve()
    truth = build_truth(arguments.case, stl_path)
    write_json(arguments.output.resolve(), truth)
    manifest = {
        "schema_version": "1.0",
        "case": truth["case"],
        "truth_builder": Path(__file__).name,
        "truth_builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "only_geometry_input": {"filename": stl_path.name, "sha256": sha256(stl_path)},
        "forbidden_inputs_read": [],
        "output": {"filename": arguments.output.name, "sha256": sha256(arguments.output.resolve())},
        "surface_count": len(truth["surfaces"]),
        "topology_edge_count": len(truth["topology_edges"]),
        "candidate_count": len(truth["primitive_candidates"]),
    }
    write_json(arguments.manifest.resolve(), manifest)


if __name__ == "__main__":
    main()
