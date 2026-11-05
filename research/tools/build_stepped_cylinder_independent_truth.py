from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


EDGE_DECIMALS = 6
VERTEX_DECIMALS = 8
NUMERIC_EPSILON_MM = 1e-6
ENDCAP_DOT_THRESHOLD = 0.95
ORTHOGONAL_DOT_THRESHOLD = 0.2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_stl_triangles(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            triangles = np.empty((count, 3, 3), dtype=float)
            offset = 84
            for index in range(count):
                values = struct.unpack_from("<12fH", data, offset)
                triangles[index] = np.asarray(values[3:12], dtype=float).reshape(3, 3)
                offset += 50
            return triangles

    vertices: list[list[float]] = []
    for line in data.decode("utf-8", errors="strict").splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            vertices.append([float(value) for value in fields[1:]])
    if not vertices or len(vertices) % 3:
        raise ValueError(f"無法解析 STL：{path}")
    return np.asarray(vertices, dtype=float).reshape(-1, 3, 3)


def triangle_geometry(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    doubled_area = np.linalg.norm(cross, axis=1)
    if np.any(doubled_area <= 1e-12):
        raise ValueError("STL 含退化三角形，無法建立獨立真值。")
    normals = cross / doubled_area[:, None]
    return triangles.mean(axis=1), normals, doubled_area / 2.0


def vertex_key(vertex: np.ndarray, decimals: int = EDGE_DECIMALS) -> tuple[float, float, float]:
    return tuple(float(value) for value in np.round(vertex, decimals))


def edge_key(a: np.ndarray, b: np.ndarray) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    first, second = vertex_key(a), vertex_key(b)
    return (first, second) if first <= second else (second, first)


def build_edge_map(triangles: np.ndarray) -> dict[Any, list[int]]:
    edges: dict[Any, list[int]] = defaultdict(list)
    for triangle_index, triangle in enumerate(triangles):
        for a_index, b_index in ((0, 1), (1, 2), (2, 0)):
            edges[edge_key(triangle[a_index], triangle[b_index])].append(triangle_index)
    return dict(edges)


class DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        root_first, root_second = self.find(first), self.find(second)
        if root_first == root_second:
            return
        if self.rank[root_first] < self.rank[root_second]:
            root_first, root_second = root_second, root_first
        self.parent[root_second] = root_first
        if self.rank[root_first] == self.rank[root_second]:
            self.rank[root_first] += 1


def derive_smooth_merge_threshold(
    edge_map: dict[Any, list[int]], normals: np.ndarray
) -> tuple[float, list[float]]:
    adjacent_dots: list[float] = []
    for incident in edge_map.values():
        if len(incident) != 2:
            continue
        dot = float(np.clip(normals[incident[0]] @ normals[incident[1]], -1.0, 1.0))
        adjacent_dots.append(dot)
    if not adjacent_dots:
        raise ValueError("STL 沒有可用的三角形共邊。")
    levels = sorted(set(round(value, 12) for value in adjacent_dots if value >= 0.0))
    if len(levels) < 2:
        raise ValueError("無法由相鄰三角形法向量的分布推導曲面分割界線。")
    gaps = [(levels[index + 1] - levels[index], index) for index in range(len(levels) - 1)]
    _, gap_index = max(gaps, key=lambda item: (item[0], -item[1]))
    threshold = (levels[gap_index] + levels[gap_index + 1]) / 2.0
    return threshold, levels


def mesh_surface_components(
    triangles: np.ndarray, normals: np.ndarray, edge_map: dict[Any, list[int]]
) -> tuple[list[np.ndarray], float, list[float]]:
    merge_threshold, levels = derive_smooth_merge_threshold(edge_map, normals)
    disjoint = DisjointSet(len(triangles))
    for incident in edge_map.values():
        if len(incident) != 2:
            continue
        first, second = incident
        if float(normals[first] @ normals[second]) > merge_threshold:
            disjoint.union(first, second)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(triangles)):
        grouped[disjoint.find(index)].append(index)
    components = [np.asarray(indices, dtype=int) for indices in grouped.values()]
    components.sort(key=lambda values: (int(values.min()), len(values)))
    return components, merge_threshold, levels


def unique_vertices(triangles: np.ndarray) -> np.ndarray:
    values = np.round(triangles.reshape(-1, 3), VERTEX_DECIMALS)
    return np.unique(values, axis=0)


def canonical_direction(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, dtype=float)
    result /= np.linalg.norm(result)
    dominant = int(np.argmax(np.abs(result)))
    if result[dominant] < 0:
        result = -result
    return result


def radial_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    candidates = np.eye(3)
    seed = candidates[int(np.argmin(np.abs(candidates @ axis)))]
    first = np.cross(axis, seed)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    second /= np.linalg.norm(second)
    return first, second


def fit_circle(points_2d: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    x, y = points_2d[:, 0], points_2d[:, 1]
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(points_2d))))
    rhs = x * x + y * y
    center_x, center_y, constant = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    radius = math.sqrt(max(float(constant + center_x * center_x + center_y * center_y), 0.0))
    center = np.asarray([center_x, center_y], dtype=float)
    residual = np.abs(np.linalg.norm(points_2d - center, axis=1) - radius)
    return center, radius, residual


def classify_component(
    component_index: int,
    triangle_indices: np.ndarray,
    triangles: np.ndarray,
    centers: np.ndarray,
    normals: np.ndarray,
    areas: np.ndarray,
) -> dict[str, Any]:
    component_triangles = triangles[triangle_indices]
    component_normals = normals[triangle_indices]
    component_areas = areas[triangle_indices]
    vertices = unique_vertices(component_triangles)
    weighted_normal = np.sum(component_normals * component_areas[:, None], axis=0)
    weighted_normal_length = float(np.linalg.norm(weighted_normal))
    normal_resultant = weighted_normal_length / float(component_areas.sum())
    triangle_hash = hashlib.sha256(
        ",".join(str(int(value)) for value in triangle_indices).encode("ascii")
    ).hexdigest()

    common = {
        "component_index": component_index,
        "triangle_count": int(len(triangle_indices)),
        "triangle_indices_sha256": triangle_hash,
        "mesh_connected_components": 1,
        "area_mm2": float(component_areas.sum()),
        "bounds_min": vertices.min(axis=0).tolist(),
        "bounds_max": vertices.max(axis=0).tolist(),
        "normal_resultant_length": normal_resultant,
    }

    if normal_resultant >= 1.0 - 1e-10:
        normal = weighted_normal / weighted_normal_length
        signed_distances = vertices @ normal
        plane_offset = float(np.median(signed_distances))
        residual = np.abs(signed_distances - plane_offset)
        return {
            **common,
            "geometry": "plane",
            "normal": normal.tolist(),
            "plane_offset_mm": plane_offset,
            "center": np.average(centers[triangle_indices], axis=0, weights=component_areas).tolist(),
            "vertex_fit_residual_max_mm": float(residual.max()),
        }

    _, _, vh = np.linalg.svd(component_normals, full_matrices=False)
    axis = canonical_direction(vh[-1])
    axis_orthogonality_max = float(np.max(np.abs(component_normals @ axis)))
    basis_first, basis_second = radial_basis(axis)
    projected = np.column_stack((vertices @ basis_first, vertices @ basis_second))
    circle_center, radius, vertex_residual = fit_circle(projected)
    axis_values = vertices @ axis
    axis_min, axis_max = float(axis_values.min()), float(axis_values.max())
    line_midpoint = (
        basis_first * circle_center[0]
        + basis_second * circle_center[1]
        + axis * ((axis_min + axis_max) / 2.0)
    )
    triangle_projected = np.column_stack(
        (centers[triangle_indices] @ basis_first, centers[triangle_indices] @ basis_second)
    )
    triangle_radial = triangle_projected - circle_center
    triangle_radial /= np.maximum(np.linalg.norm(triangle_radial, axis=1)[:, None], 1e-12)
    signed_alignment = np.sum(
        component_normals
        * (triangle_radial[:, 0, None] * basis_first + triangle_radial[:, 1, None] * basis_second),
        axis=1,
    )

    edge_midpoints: list[np.ndarray] = []
    for triangle in component_triangles:
        edge_midpoints.extend(
            ((triangle[0] + triangle[1]) / 2.0, (triangle[1] + triangle[2]) / 2.0, (triangle[2] + triangle[0]) / 2.0)
        )
    edge_midpoints_array = np.asarray(edge_midpoints)
    edge_projected = np.column_stack(
        (edge_midpoints_array @ basis_first, edge_midpoints_array @ basis_second)
    )
    edge_radii = np.linalg.norm(edge_projected - circle_center, axis=1)
    facet_sagitta = float(np.max(np.abs(edge_radii - radius)))
    orientation = "outer" if float(np.median(signed_alignment)) > 0.0 else "inner"

    return {
        **common,
        "geometry": "cylinder",
        "axis": axis.tolist(),
        "axis_line_midpoint": line_midpoint.tolist(),
        "axis_min_mm": axis_min,
        "axis_max_mm": axis_max,
        "depth_mm": axis_max - axis_min,
        "radius_mm": float(radius),
        "orientation": orientation,
        "axis_orthogonality_max": axis_orthogonality_max,
        "vertex_fit_residual_max_mm": float(vertex_residual.max()),
        "facet_sagitta_max_mm": facet_sagitta,
        "radius_comparison_tolerance_mm": facet_sagitta + NUMERIC_EPSILON_MM,
        "signed_normal_alignment_median": float(np.median(signed_alignment)),
    }


def assign_semantic_roles(surfaces: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], np.ndarray]:
    cylinders = [surface for surface in surfaces if surface["geometry"] == "cylinder"]
    planes = [surface for surface in surfaces if surface["geometry"] == "plane"]
    if len(cylinders) != 3 or len(planes) != 3:
        raise ValueError(f"Stepped Cylinder 應由 3 個圓柱曲面與 3 個平面構成，實得 {len(cylinders)} 與 {len(planes)}。")
    axes = np.asarray([surface["axis"] for surface in cylinders], dtype=float)
    reference_axis = canonical_direction(axes.mean(axis=0))
    if np.min(np.abs(axes @ reference_axis)) < 1.0 - 1e-8:
        raise ValueError("三個圓柱曲面未共享同一軸向。")

    inner = [surface for surface in cylinders if surface["orientation"] == "inner"]
    outer = sorted(
        [surface for surface in cylinders if surface["orientation"] == "outer"],
        key=lambda surface: (surface["axis_min_mm"], surface["radius_mm"]),
    )
    if len(inner) != 1 or len(outer) != 2:
        raise ValueError("無法由 STL 法向量方向辨識一個內圓柱與兩個外圓柱。")
    planes_sorted = sorted(
        planes,
        key=lambda surface: float(np.asarray(surface["center"], dtype=float) @ reference_axis),
    )

    role_assignments = [
        (inner[0], "GT_S01", "through_hole_side", "Cylinder_axisZ_inner (貫穿孔)"),
        (outer[0], "GT_S02", "lower_outer_cylinder", "Cylinder_axisZ_outer (下階外圓柱)"),
        (planes_sorted[0], "GT_S03", "base_annular_plane", "Plane_Horizontal (底面環)"),
        (planes_sorted[1], "GT_S04", "shoulder_annular_plane", "Plane_Horizontal (階梯肩面)"),
        (planes_sorted[2], "GT_S05", "top_annular_plane", "Plane_Horizontal (頂面環)"),
        (outer[1], "GT_S06", "upper_outer_cylinder", "Cylinder_axisZ_outer (上階外圓柱)"),
    ]
    for surface, surface_id, role, feature_type in role_assignments:
        surface["surface_id"] = surface_id
        surface["semantic_role"] = role
        surface["feature_type"] = feature_type
    return sorted(surfaces, key=lambda surface: surface["surface_id"]), reference_axis


def derive_topology(
    surfaces: list[dict[str, Any]], edge_map: dict[Any, list[int]], triangles: np.ndarray
) -> list[dict[str, Any]]:
    triangle_to_surface: dict[int, str] = {}
    component_to_id = {surface["component_index"]: surface["surface_id"] for surface in surfaces}
    component_by_triangle: dict[int, int] = {}
    # Component hashes are for traceability; the actual index lists are recovered by repeating the
    # same deterministic smooth-component calculation in main and injected temporarily below.
    for surface in surfaces:
        for triangle_index in surface.pop("_triangle_indices"):
            component_by_triangle[int(triangle_index)] = int(surface["component_index"])
    for triangle_index, component_index in component_by_triangle.items():
        triangle_to_surface[triangle_index] = component_to_id[component_index]

    surface_by_id = {surface["surface_id"]: surface for surface in surfaces}
    shared: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for key, incident in edge_map.items():
        if len(incident) != 2:
            continue
        first_id, second_id = triangle_to_surface[incident[0]], triangle_to_surface[incident[1]]
        if first_id == second_id:
            continue
        pair = tuple(sorted((first_id, second_id)))
        shared[pair].append(key)

    topology: list[dict[str, Any]] = []
    for (first_id, second_id), keys in sorted(shared.items()):
        first, second = surface_by_id[first_id], surface_by_id[second_id]
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

        boundary_length = 0.0
        for key in keys:
            first_vertex, second_vertex = np.asarray(key[0]), np.asarray(key[1])
            boundary_length += float(np.linalg.norm(first_vertex - second_vertex))
        topology.append(
            {
                "from_surface_id": first_id,
                "to_surface_id": second_id,
                "edge_type": edge_type,
                "shared_mesh_edge_count": len(keys),
                "shared_boundary_length_mm": boundary_length,
                "direction_dot": direction_dot,
            }
        )
    return topology


def derive_candidates(
    surfaces: list[dict[str, Any]], topology: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    surface_by_id = {surface["surface_id"]: surface for surface in surfaces}
    end_planes: dict[str, list[str]] = defaultdict(list)
    for edge in topology:
        if edge["edge_type"] != "EndCap":
            continue
        first = surface_by_id[edge["from_surface_id"]]
        second = surface_by_id[edge["to_surface_id"]]
        cylinder = first if first["geometry"] == "cylinder" else second
        plane = first if first["geometry"] == "plane" else second
        end_planes[cylinder["surface_id"]].append(plane["surface_id"])

    role_to_candidate = {
        "lower_outer_cylinder": ("GT_C01", "CylinderLower", "Union"),
        "upper_outer_cylinder": ("GT_C02", "CylinderUpper", "Union"),
        "through_hole_side": ("GT_C03", "ThroughHole", "Difference"),
    }
    candidates: list[dict[str, Any]] = []
    for surface in surfaces:
        if surface["geometry"] != "cylinder":
            continue
        planes = sorted(end_planes.get(surface["surface_id"], []))
        if len(planes) != 2:
            raise ValueError(f"{surface['surface_id']} 未由 STL 共邊取得兩個端面。")
        candidate_id, primitive_type, boolean_type = role_to_candidate[surface["semantic_role"]]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "primitive_type": primitive_type,
                "boolean_type": boolean_type,
                "side_surface_id": surface["surface_id"],
                "end_surface_ids": planes,
                "related_surface_ids": sorted([surface["surface_id"], *planes]),
                "radius_mm": surface["radius_mm"],
                "depth_mm": surface["depth_mm"],
                "radius_comparison_tolerance_mm": surface["radius_comparison_tolerance_mm"],
                "depth_comparison_tolerance_mm": NUMERIC_EPSILON_MM,
            }
        )
    return sorted(candidates, key=lambda candidate: candidate["candidate_id"])


def build_truth(stl_path: Path) -> dict[str, Any]:
    triangles = read_stl_triangles(stl_path)
    centers, normals, areas = triangle_geometry(triangles)
    edge_map = build_edge_map(triangles)
    components, merge_threshold, adjacent_dot_levels = mesh_surface_components(triangles, normals, edge_map)
    raw_surfaces = []
    for component_index, triangle_indices in enumerate(components):
        surface = classify_component(
            component_index, triangle_indices, triangles, centers, normals, areas
        )
        surface["_triangle_indices"] = triangle_indices.tolist()
        raw_surfaces.append(surface)
    surfaces, reference_axis = assign_semantic_roles(raw_surfaces)
    topology = derive_topology(surfaces, edge_map, triangles)
    candidates = derive_candidates(surfaces, topology)
    union_candidates = [candidate["candidate_id"] for candidate in candidates if candidate["boolean_type"] == "Union"]
    difference_candidates = [candidate["candidate_id"] for candidate in candidates if candidate["boolean_type"] == "Difference"]
    csg_tree = {
        "op": "Difference",
        "base": {"op": "Union", "children": [{"candidate": value} for value in union_candidates]},
        "subtractors": [{"candidate": value} for value in difference_candidates],
    }

    nonmanifold_edges = sum(1 for incident in edge_map.values() if len(incident) != 2)
    return {
        "schema_version": "1.0",
        "case": "Stepped Cylinder",
        "display_name": "階梯狀圓柱",
        "truth_scope": "STL final triangle mesh only; no Result, FaceSummary, TopologyEdges, PrimitiveCandidates, point cloud, or prior GroundTruth was read",
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
            "method": "shared-edge connectivity plus the largest data-derived gap in adjacent triangle normal dot products",
            "adjacent_normal_dot_levels": adjacent_dot_levels,
            "derived_merge_dot_threshold": merge_threshold,
            "surface_count": len(surfaces),
            "reference_axis": reference_axis.tolist(),
        },
        "surfaces": surfaces,
        "topology_edges": topology,
        "primitive_candidates": candidates,
        "canonical_csg_tree": csg_tree,
        "interpretation_limits": [
            "The truth describes the supplied STL mesh and does not prove generalization to real scans.",
            "Candidate solids and the CSG tree are symbolic inference targets; no STEP, IGES, B-rep, or editable CAD solid is asserted.",
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an STL-only independent truth for Stepped Cylinder.")
    parser.add_argument("--stl", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    truth = build_truth(arguments.stl.resolve())
    write_json(arguments.output.resolve(), truth)


if __name__ == "__main__":
    main()
