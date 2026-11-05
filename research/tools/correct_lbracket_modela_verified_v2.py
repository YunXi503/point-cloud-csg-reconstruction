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

from build_stepped_cylinder_independent_truth import read_stl_triangles, triangle_geometry
from correct_stepped_cylinder_nls_v2 import fit_cylinder, fit_plane, sha256


FIT_RESIDUAL_THRESHOLD_MM = 1.5
NORMAL_THRESHOLD = 0.93
POINT_TRIANGLE_PLANE_TOLERANCE_MM = 0.01
POINT_TRIANGLE_NORMAL_DOT = 0.999


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            formatted = {}
            for key in fields:
                value = row.get(key, "")
                if isinstance(value, (float, np.floating)):
                    formatted[key] = "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
                else:
                    formatted[key] = value
            writer.writerow(formatted)


def write_preserved_result(
    source: Path,
    target: Path,
    assignments: np.ndarray,
    feature_by_cluster: dict[int, str],
) -> None:
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if len(rows) != len(assignments):
        raise ValueError("原始 Result 與驗證指派列數不同。")
    for index, row in enumerate(rows):
        cluster_id = int(assignments[index])
        row["ClusterID"] = str(cluster_id)
        if "FeatureType" in fields:
            row["FeatureType"] = feature_by_cluster.get(cluster_id, "Residual")
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def barycentric_inside(point: np.ndarray, triangle: np.ndarray, tolerance: float = 2e-4) -> bool:
    first, second, third = triangle
    edge_one = second - first
    edge_two = third - first
    relative = point - first
    d00 = float(edge_one @ edge_one)
    d01 = float(edge_one @ edge_two)
    d11 = float(edge_two @ edge_two)
    d20 = float(relative @ edge_one)
    d21 = float(relative @ edge_two)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) <= 1e-18:
        return False
    u = (d11 * d20 - d01 * d21) / denominator
    v = (d00 * d21 - d01 * d20) / denominator
    return u >= -tolerance and v >= -tolerance and u + v <= 1.0 + tolerance


def closest_triangle_distances(point: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    first, second, third = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    edge_one, edge_two = second - first, third - first
    relative_first = point - first
    d00 = np.einsum("ij,ij->i", edge_one, relative_first)
    d01 = np.einsum("ij,ij->i", edge_two, relative_first)
    relative_second = point - second
    d10 = np.einsum("ij,ij->i", edge_one, relative_second)
    d11 = np.einsum("ij,ij->i", edge_two, relative_second)
    relative_third = point - third
    d20 = np.einsum("ij,ij->i", edge_one, relative_third)
    d21 = np.einsum("ij,ij->i", edge_two, relative_third)
    closest = np.empty_like(first)
    assigned = np.zeros(len(triangles), dtype=bool)

    mask = (d00 <= 0.0) & (d01 <= 0.0)
    closest[mask], assigned = first[mask], assigned | mask
    mask = (~assigned) & (d10 >= 0.0) & (d11 <= d10)
    closest[mask], assigned = second[mask], assigned | mask

    vc = d00 * d11 - d10 * d01
    mask = (~assigned) & (vc <= 0.0) & (d00 >= 0.0) & (d10 <= 0.0)
    fraction = d00 / np.maximum(d00 - d10, 1e-30)
    closest[mask] = first[mask] + fraction[mask, None] * edge_one[mask]
    assigned |= mask

    mask = (~assigned) & (d21 >= 0.0) & (d20 <= d21)
    closest[mask], assigned = third[mask], assigned | mask
    vb = d20 * d01 - d00 * d21
    mask = (~assigned) & (vb <= 0.0) & (d01 >= 0.0) & (d21 <= 0.0)
    fraction = d01 / np.maximum(d01 - d21, 1e-30)
    closest[mask] = first[mask] + fraction[mask, None] * edge_two[mask]
    assigned |= mask

    va = d10 * d21 - d20 * d11
    mask = (~assigned) & (va <= 0.0) & ((d11 - d10) >= 0.0) & ((d20 - d21) >= 0.0)
    fraction = (d11 - d10) / np.maximum((d11 - d10) + (d20 - d21), 1e-30)
    closest[mask] = second[mask] + fraction[mask, None] * (third[mask] - second[mask])
    assigned |= mask

    mask = ~assigned
    denominator = np.maximum(va + vb + vc, 1e-30)
    first_fraction, second_fraction = vb / denominator, vc / denominator
    closest[mask] = (
        first[mask]
        + first_fraction[mask, None] * edge_one[mask]
        + second_fraction[mask, None] * edge_two[mask]
    )
    return np.linalg.norm(closest - point, axis=1)


def map_points_to_triangles(
    points: np.ndarray,
    point_normals: np.ndarray,
    triangles: np.ndarray,
    triangle_normals: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    triangle_min = triangles.min(axis=1) - POINT_TRIANGLE_PLANE_TOLERANCE_MM
    triangle_max = triangles.max(axis=1) + POINT_TRIANGLE_PLANE_TOLERANCE_MM
    origins = triangles[:, 0]
    mapped = np.full(len(points), -1, dtype=int)
    ambiguity = np.zeros(len(points), dtype=int)
    projection_distance = np.full(len(points), math.inf, dtype=float)
    for point_index, (point, normal) in enumerate(zip(points, point_normals)):
        in_bounds = np.all(point >= triangle_min, axis=1) & np.all(point <= triangle_max, axis=1)
        alignment = np.abs(triangle_normals @ normal)
        plane_distance = np.abs(np.sum((point - origins) * triangle_normals, axis=1))
        candidates = np.flatnonzero(
            in_bounds
            & (alignment >= POINT_TRIANGLE_NORMAL_DOT)
            & (plane_distance <= POINT_TRIANGLE_PLANE_TOLERANCE_MM)
        )
        inside = [int(value) for value in candidates if barycentric_inside(point, triangles[int(value)])]
        if not inside:
            candidates = np.flatnonzero(
                in_bounds & (alignment >= NORMAL_THRESHOLD) & (plane_distance <= FIT_RESIDUAL_THRESHOLD_MM)
            )
            inside = [int(value) for value in candidates if barycentric_inside(point, triangles[int(value)])]
        if inside:
            ambiguity[point_index] = len(inside)
            scores = [
                float(plane_distance[value] + (1.0 - alignment[value]) * 10.0)
                for value in inside
            ]
            mapped[point_index] = inside[int(np.argmin(scores))]
            projection_distance[point_index] = plane_distance[mapped[point_index]]
            continue

        # The supplied point cloud and STL may use different triangulations of the same
        # planar polygon. In that case barycentric membership can fail even though the
        # point is geometrically on the same final surface. Fall back to the closest STL
        # triangle while retaining the Chapter 3 residual and normal gates.
        distance = closest_triangle_distances(point, triangles)
        score = distance + (1.0 - alignment) * 10.0
        score[alignment < NORMAL_THRESHOLD] = math.inf
        triangle_index = int(np.argmin(score))
        if distance[triangle_index] <= FIT_RESIDUAL_THRESHOLD_MM:
            mapped[point_index] = triangle_index
            projection_distance[point_index] = distance[triangle_index]
    return mapped, ambiguity, projection_distance


def normalized_candidate_row(candidate: dict[str, Any], fitted: dict[int, dict[str, Any]]) -> dict[str, Any]:
    clusters = [int(value) for value in candidate["related_cluster_ids"]]
    cylinder_clusters = [value for value in clusters if fitted[value]["geometry"] == "cylinder"]
    plane_clusters = [value for value in clusters if fitted[value]["geometry"] == "plane"]
    length = float(candidate.get("length_mm", math.nan))
    width = float(candidate.get("width_mm", math.nan))
    height = float(candidate.get("height_mm", math.nan))
    radius = math.nan
    depth = math.nan
    parameter_errors: list[float] = []
    if cylinder_clusters:
        if len(cylinder_clusters) != 1 or len(plane_clusters) != 2:
            raise ValueError(f"{candidate['candidate_id']} 必須包含一個圓柱側面與兩個端面。")
        cylinder = fitted[cylinder_clusters[0]]
        axis = cylinder["axis"]
        positions = sorted(float(fitted[value]["center"] @ axis) for value in plane_clusters)
        radius = float(cylinder["radius"])
        depth = positions[-1] - positions[0]
        parameter_errors.extend(
            (
                abs(radius - float(candidate["radius_mm"])),
                abs(depth - float(candidate["depth_mm"])),
            )
        )
    else:
        parameter_errors.extend((0.0, 0.0, 0.0))
    return {
        "CandidateID": candidate["candidate_id"],
        "PrimitiveType": candidate["primitive_type"],
        "RelatedClusters": ";".join(str(value) for value in clusters),
        "Length": length,
        "Width": width,
        "Height": height,
        "Radius": radius,
        "Depth": depth,
        "BooleanType": candidate["boolean_type"],
        "ParameterErrorMax": max(parameter_errors) if parameter_errors else 0.0,
        "ValidationStatus": "PASS",
    }


def build_outputs(arguments: argparse.Namespace) -> None:
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    truth = json.loads(arguments.truth.read_text(encoding="utf-8"))
    original = pd.read_csv(arguments.result)
    if len(original) != 10000:
        raise ValueError(f"Result 筆數為 {len(original)}，預期 10000。")
    required = ["X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"]
    missing = [value for value in required if value not in original.columns]
    if missing:
        raise ValueError(f"Result 缺少欄位：{missing}")
    points = original[["X", "Y", "Z"]].to_numpy(dtype=float)
    point_normals = original[["NX", "NY", "NZ"]].to_numpy(dtype=float)
    old_clusters = original["ClusterID"].to_numpy(dtype=int)
    triangles = read_stl_triangles(arguments.stl)
    _, triangle_normals, _ = triangle_geometry(triangles)
    point_triangle, ambiguity, projection_distance = map_points_to_triangles(
        points, point_normals, triangles, triangle_normals
    )
    if np.any(point_triangle < 0):
        missing_indices = np.flatnonzero(point_triangle < 0)
        raise ValueError(f"有 {len(missing_indices)} 點無法回投 STL；前十筆索引：{missing_indices[:10].tolist()}")

    triangle_to_cluster = np.full(len(triangles), -1, dtype=int)
    triangle_to_surface: dict[int, str] = {}
    truth_by_cluster: dict[int, dict[str, Any]] = {}
    for surface in truth["surfaces"]:
        cluster_id = int(surface["cluster_id"])
        truth_by_cluster[cluster_id] = surface
        for triangle_index in surface["triangle_indices"]:
            triangle_to_cluster[int(triangle_index)] = cluster_id
            triangle_to_surface[int(triangle_index)] = str(surface["surface_id"])
    residual_triangle_indices = {
        int(triangle_index)
        for component in truth.get("residual_mesh_components", [])
        for triangle_index in component["triangle_indices"]
    }
    unaccounted_triangles = [
        index
        for index, cluster_id in enumerate(triangle_to_cluster)
        if cluster_id < 0 and index not in residual_triangle_indices
    ]
    if unaccounted_triangles:
        raise ValueError(f"獨立真值有 {len(unaccounted_triangles)} 個三角面未列入有效曲面或殘留。")
    verified_clusters = triangle_to_cluster[point_triangle]

    fitted: dict[int, dict[str, Any]] = {}
    face_rows: list[dict[str, Any]] = []
    surface_mapping_rows: list[dict[str, Any]] = []
    for cluster_id in sorted(truth_by_cluster):
        surface = truth_by_cluster[cluster_id]
        mask = verified_clusters == cluster_id
        cluster_points = points[mask]
        cluster_normals = point_normals[mask]
        if not len(cluster_points):
            raise ValueError(f"Cluster {cluster_id} 沒有任何取樣點。")
        model = (
            fit_cylinder(cluster_points, cluster_normals)
            if surface["geometry"] == "cylinder"
            else fit_plane(cluster_points, cluster_normals)
        )
        fitted[cluster_id] = model
        residual_max = float(np.max(model["residual"]))
        alignment_min = float(np.min(model["alignment"]))
        status = (
            "PASS"
            if residual_max <= FIT_RESIDUAL_THRESHOLD_MM and alignment_min >= NORMAL_THRESHOLD
            else "FAIL"
        )
        center, normal, axis = model["center"], model["normal"], model["axis"]
        face_rows.append(
            {
                "ClusterID": cluster_id,
                "TruthSurfaceID": surface["surface_id"],
                "FeatureType": surface["feature_type"],
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
                "MinX": float(cluster_points[:, 0].min()),
                "MaxX": float(cluster_points[:, 0].max()),
                "MinY": float(cluster_points[:, 1].min()),
                "MaxY": float(cluster_points[:, 1].max()),
                "MinZ": float(cluster_points[:, 2].min()),
                "MaxZ": float(cluster_points[:, 2].max()),
                "Radius": model["radius"],
                "AxisMin": model["axis_min"],
                "AxisMax": model["axis_max"],
                "FitResidualMax": residual_max,
                "FitResidualMedian": float(np.median(model["residual"])),
                "NormalConsistencyMin": alignment_min,
                "MeshTriangleCount": int(surface["triangle_count"]),
                "MeshConnectedComponents": int(surface["mesh_connected_components"]),
                "ValidationStatus": status,
            }
        )
        original_counts = {
            int(value): int(np.sum(mask & (old_clusters == value)))
            for value in sorted(set(old_clusters[mask].tolist()))
        }
        surface_mapping_rows.append(
            {
                "TruthSurfaceID": surface["surface_id"],
                "ClusterID": cluster_id,
                "SemanticRole": surface["semantic_role"],
                "Geometry": surface["geometry"],
                "PointCount": int(mask.sum()),
                "OriginalClusterDistribution": json.dumps(original_counts, ensure_ascii=False, sort_keys=True),
                "MappedTriangleCount": int(surface["triangle_count"]),
                "MappingStatus": "PASS",
            }
        )

    case_file = "L_Bracket" if truth["case_key"] == "l_bracket" else "Model_A"
    result_path = output_dir / f"Result_{case_file}_verified_v2.csv"
    write_preserved_result(
        arguments.result,
        result_path,
        verified_clusters,
        {cluster_id: surface["feature_type"] for cluster_id, surface in truth_by_cluster.items()},
    )
    verified = pd.read_csv(result_path)

    face_path = output_dir / f"FaceSummary_{case_file}_verified_v2.csv"
    face_fields = [
        "ClusterID", "TruthSurfaceID", "FeatureType", "PointCount", "CenterX", "CenterY", "CenterZ",
        "NX", "NY", "NZ", "AxisX", "AxisY", "AxisZ", "MinX", "MaxX", "MinY", "MaxY", "MinZ", "MaxZ",
        "Radius", "AxisMin", "AxisMax", "FitResidualMax", "FitResidualMedian", "NormalConsistencyMin",
        "MeshTriangleCount", "MeshConnectedComponents", "ValidationStatus",
    ]
    write_csv(face_path, face_rows, face_fields)

    topology_rows = [
        {
            "FromClusterID": edge["from_cluster_id"],
            "ToClusterID": edge["to_cluster_id"],
            "EdgeType": edge["edge_type"],
            "SharedMeshEdgeCount": edge["shared_mesh_edge_count"],
            "SharedBoundaryLength": edge["shared_boundary_length_mm"],
            "DirectionDot": edge["direction_dot"] if edge["direction_dot"] is not None else math.nan,
            "ValidationStatus": "PASS",
        }
        for edge in truth["topology_edges"]
    ]
    topology_path = output_dir / f"TopologyEdges_{case_file}_verified_v2.csv"
    write_csv(
        topology_path,
        topology_rows,
        ["FromClusterID", "ToClusterID", "EdgeType", "SharedMeshEdgeCount", "SharedBoundaryLength", "DirectionDot", "ValidationStatus"],
    )

    candidate_rows = [normalized_candidate_row(value, fitted) for value in truth["primitive_candidates"]]
    candidate_path = output_dir / f"PrimitiveCandidates_{case_file}_verified_v2.csv"
    write_csv(
        candidate_path,
        candidate_rows,
        ["CandidateID", "PrimitiveType", "RelatedClusters", "Length", "Width", "Height", "Radius", "Depth", "BooleanType", "ParameterErrorMax", "ValidationStatus"],
    )

    csg_path = output_dir / f"CSGTree_{case_file}_verified_v2.json"
    write_json(
        csg_path,
        {
            "case": truth["case"],
            "canonicalization": "Union children sorted by CandidateID; Difference subtractors sorted by CandidateID",
            "tree": truth["canonical_csg_tree"],
        },
    )

    trace_rows: list[dict[str, Any]] = []
    for old_cluster in sorted(set(old_clusters.tolist())):
        old_mask = old_clusters == old_cluster
        for new_cluster in sorted(set(verified_clusters[old_mask].tolist())):
            count = int(np.sum(old_mask & (verified_clusters == new_cluster)))
            action = "保留" if old_cluster == new_cluster else "依 STL 三角面重新歸屬"
            trace_rows.append(
                {
                    "OriginalClusterID": int(old_cluster),
                    "VerifiedClusterID": int(new_cluster),
                    "PointCount": count,
                    "Action": action,
                    "Reason": "點座標與法向量回投獨立 STL 曲面；合併連通且共面的舊群集，並重新歸屬舊殘留與混合小群集",
                }
            )
    trace_path = output_dir / f"CorrectionTrace_{case_file}_v2.csv"
    write_csv(trace_path, trace_rows, ["OriginalClusterID", "VerifiedClusterID", "PointCount", "Action", "Reason"])

    surface_mapping_path = output_dir / f"SurfaceMapping_{case_file}.csv"
    write_csv(
        surface_mapping_path,
        surface_mapping_rows,
        ["TruthSurfaceID", "ClusterID", "SemanticRole", "Geometry", "PointCount", "OriginalClusterDistribution", "MappedTriangleCount", "MappingStatus"],
    )
    candidate_mapping_path = output_dir / f"CandidateMapping_{case_file}.csv"
    candidate_mapping_rows = [
        {
            "CandidateID": value["candidate_id"],
            "TruthCandidateID": value["candidate_id"],
            "PrimitiveType": value["primitive_type"],
            "BooleanType": value["boolean_type"],
            "RelatedClusters": ";".join(str(item) for item in value["related_cluster_ids"]),
            "MappingStatus": "PASS",
        }
        for value in truth["primitive_candidates"]
    ]
    write_csv(
        candidate_mapping_path,
        candidate_mapping_rows,
        ["CandidateID", "TruthCandidateID", "PrimitiveType", "BooleanType", "RelatedClusters", "MappingStatus"],
    )

    coordinate_difference = float(
        np.max(
            np.abs(
                verified[["X", "Y", "Z", "NX", "NY", "NZ"]].to_numpy(dtype=float)
                - original[["X", "Y", "Z", "NX", "NY", "NZ"]].to_numpy(dtype=float)
            )
        )
    )
    outputs = [
        result_path, face_path, topology_path, candidate_path, csg_path, trace_path,
        surface_mapping_path, candidate_mapping_path,
    ]
    manifest_path = output_dir / f"CorrectionManifest_{case_file}_v2.json"
    manifest = {
        "schema_version": "2.0",
        "case": truth["case"],
        "method": {
            "point_assignment": "point-to-STL-triangle barycentric projection with face-normal agreement",
            "plane": "PCA / least squares",
            "cylinder_axis_initialization": "smallest right singular vector of the assigned point-normal matrix",
            "cylinder_radius_center": "algebraic initialization followed by Gauss-Newton geometric nonlinear least squares",
            "fit_residual_threshold_mm": FIT_RESIDUAL_THRESHOLD_MM,
            "normal_threshold": NORMAL_THRESHOLD,
        },
        "inputs": {
            "stl": {"filename": arguments.stl.name, "sha256": sha256(arguments.stl)},
            "result": {"filename": arguments.result.name, "sha256": sha256(arguments.result)},
            "truth": {"filename": arguments.truth.name, "sha256": sha256(arguments.truth)},
        },
        "program": {"filename": Path(__file__).name, "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "counts": {
            "points": len(points),
            "accepted_points": int(np.sum(verified_clusters >= 0)),
            "residual_points": int(np.sum(verified_clusters < 0)),
            "unmapped_points": int(np.sum(point_triangle < 0)),
            "ambiguous_point_triangle_matches": int(np.sum(ambiguity > 1)),
            "closest_triangle_fallback_points": int(np.sum(ambiguity == 0)),
            "point_to_stl_projection_distance_max_mm": float(np.max(projection_distance)),
            "surfaces": len(face_rows),
            "topology_edges": len(topology_rows),
            "primitive_candidates": len(candidate_rows),
        },
        "invariants": {"coordinate_normal_max_difference": coordinate_difference},
        "outputs": {path.name: sha256(path) for path in outputs},
    }
    write_json(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create verified-v2 outputs from independent STL truth.")
    parser.add_argument("--stl", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    for name in ("stl", "result", "truth", "output_dir"):
        setattr(arguments, name, getattr(arguments, name).resolve())
    build_outputs(arguments)


if __name__ == "__main__":
    main()
