from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_stepped_cylinder_independent_truth import read_stl_triangles, sha256, triangle_geometry
from correct_lbracket_modela_verified_v2 import (
    closest_triangle_distances,
    map_points_to_triangles,
)


FIT_RESIDUAL_THRESHOLD_MM = 1.5
NORMAL_THRESHOLD = 0.93
BASE_PARAMETER_TOLERANCE_MM = 0.05
ALLOWED_EDGE_TYPES = {"Adjacency", "OrthogonalAdjacency", "EndCap"}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_pair(first: Any, second: Any) -> tuple[int, int]:
    values = sorted((int(first), int(second)))
    return values[0], values[1]


def parse_clusters(value: Any) -> list[int]:
    return sorted(int(item.strip()) for item in str(value).split(";") if item.strip())


def mesh_bidirectional_distance(first: np.ndarray, second: np.ndarray) -> dict[str, float]:
    first_vertices = np.unique(np.round(first.reshape(-1, 3), 8), axis=0)
    second_vertices = np.unique(np.round(second.reshape(-1, 3), 8), axis=0)
    first_to_second = np.asarray(
        [float(np.min(closest_triangle_distances(point, second))) for point in first_vertices]
    )
    second_to_first = np.asarray(
        [float(np.min(closest_triangle_distances(point, first))) for point in second_vertices]
    )
    return {
        "first_to_second_max_mm": float(first_to_second.max()),
        "first_to_second_median_mm": float(np.median(first_to_second)),
        "second_to_first_max_mm": float(second_to_first.max()),
        "second_to_first_median_mm": float(np.median(second_to_first)),
        "bidirectional_max_mm": float(max(first_to_second.max(), second_to_first.max())),
    }


def expected_point_clusters(
    raw: pd.DataFrame, evaluated_triangles: np.ndarray, truth: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = raw[["X", "Y", "Z"]].to_numpy(dtype=float)
    normals = raw[["NX", "NY", "NZ"]].to_numpy(dtype=float)
    _, triangle_normals, _ = triangle_geometry(evaluated_triangles)
    mapped, ambiguity, distance = map_points_to_triangles(
        points, normals, evaluated_triangles, triangle_normals
    )
    if np.any(mapped < 0):
        raise ValueError("驗證時仍有點無法回投 evaluated Blend mesh。")
    triangle_cluster = np.full(len(evaluated_triangles), -1, dtype=int)
    accounted = set()
    for surface in truth["surfaces"]:
        for triangle_index in surface["triangle_indices"]:
            triangle_cluster[int(triangle_index)] = int(surface["cluster_id"])
            accounted.add(int(triangle_index))
    for component in truth.get("residual_mesh_components", []):
        accounted.update(int(value) for value in component["triangle_indices"])
    if len(accounted) != len(evaluated_triangles):
        raise ValueError("獨立真值未覆蓋全部 evaluated mesh 三角面。")
    return triangle_cluster[mapped], ambiguity, distance


def compare_topology(frame: pd.DataFrame, truth: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    actual = {
        (*normalize_pair(row.FromClusterID, row.ToClusterID), str(row.EdgeType))
        for row in frame.itertuples(index=False)
    }
    expected = {
        (*normalize_pair(edge["from_cluster_id"], edge["to_cluster_id"]), edge["edge_type"])
        for edge in truth["topology_edges"]
    }
    allowed = set(str(value) for value in frame["EdgeType"]) <= ALLOWED_EDGE_TYPES
    statuses = set(str(value) for value in frame["ValidationStatus"]) == {"PASS"}
    return actual == expected and allowed and statuses, {
        "expected_edge_count": len(expected),
        "actual_edge_count": len(actual),
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
        "edge_types_allowed": allowed,
    }


def compare_candidates(frame: pd.DataFrame, truth: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    actual_by_id = {str(row["CandidateID"]): row for _, row in frame.iterrows()}
    expected_by_id = {str(value["candidate_id"]): value for value in truth["primitive_candidates"]}
    details: list[dict[str, Any]] = []
    passed = set(actual_by_id) == set(expected_by_id)
    surface_by_cluster = {int(value["cluster_id"]): value for value in truth["surfaces"]}
    for candidate_id in sorted(expected_by_id):
        expected = expected_by_id[candidate_id]
        actual = actual_by_id.get(candidate_id)
        if actual is None:
            details.append({"candidate_id": candidate_id, "status": "MISSING"})
            continue
        identity_pass = (
            str(actual["PrimitiveType"]) == expected["primitive_type"]
            and str(actual["BooleanType"]) == expected["boolean_type"]
            and parse_clusters(actual["RelatedClusters"]) == sorted(expected["related_cluster_ids"])
        )
        errors: dict[str, float] = {}
        tolerances: dict[str, float] = {}
        for truth_key, csv_key in (
            ("length_mm", "Length"),
            ("width_mm", "Width"),
            ("height_mm", "Height"),
            ("radius_mm", "Radius"),
            ("depth_mm", "Depth"),
        ):
            if truth_key not in expected:
                continue
            error = abs(float(actual[csv_key]) - float(expected[truth_key]))
            tolerance = 1e-6
            if truth_key in {"radius_mm", "depth_mm"}:
                cylinder_clusters = [
                    value
                    for value in expected["related_cluster_ids"]
                    if surface_by_cluster[int(value)]["geometry"] == "cylinder"
                ]
                support = max(
                    [float(surface_by_cluster[int(value)].get("support_error_max_mm", 0.0)) for value in cylinder_clusters]
                    or [0.0]
                )
                tolerance = max(BASE_PARAMETER_TOLERANCE_MM, support + 1e-6)
            errors[csv_key] = error
            tolerances[csv_key] = tolerance
        parameter_pass = all(errors[key] <= tolerances[key] for key in errors)
        row_pass = identity_pass and parameter_pass and str(actual["ValidationStatus"]) == "PASS"
        passed &= row_pass
        details.append(
            {
                "candidate_id": candidate_id,
                "identity_pass": identity_pass,
                "parameter_errors_mm": errors,
                "parameter_tolerances_mm": tolerances,
                "status": "PASS" if row_pass else "FAIL",
            }
        )
    return passed, {"expected_count": len(expected_by_id), "actual_count": len(actual_by_id), "details": details}


def validate(arguments: argparse.Namespace) -> dict[str, Any]:
    output_dir = arguments.output_dir.resolve()
    truth = json.loads(arguments.truth.read_text(encoding="utf-8"))
    case_file = "L_Bracket" if truth["case_key"] == "l_bracket" else "Model_A"
    verified_result_path = output_dir / f"Result_{case_file}_verified_v2.csv"
    face_path = output_dir / f"FaceSummary_{case_file}_verified_v2.csv"
    topology_path = output_dir / f"TopologyEdges_{case_file}_verified_v2.csv"
    candidate_path = output_dir / f"PrimitiveCandidates_{case_file}_verified_v2.csv"
    csg_path = output_dir / f"CSGTree_{case_file}_verified_v2.json"
    mapping_path = output_dir / f"SurfaceMapping_{case_file}.csv"
    candidate_mapping_path = output_dir / f"CandidateMapping_{case_file}.csv"
    required_paths = [
        verified_result_path, face_path, topology_path, candidate_path, csg_path,
        mapping_path, candidate_mapping_path,
    ]
    if not all(path.exists() for path in required_paths):
        missing = [path.name for path in required_paths if not path.exists()]
        raise FileNotFoundError(f"缺少驗證輸出：{missing}")

    raw = pd.read_csv(arguments.raw_result)
    point_cloud = pd.read_csv(arguments.point_cloud)
    verified = pd.read_csv(verified_result_path)
    faces = pd.read_csv(face_path)
    topology = pd.read_csv(topology_path)
    candidates = pd.read_csv(candidate_path)
    evaluated_triangles = read_stl_triangles(arguments.evaluated_mesh)
    original_triangles = read_stl_triangles(arguments.original_stl)
    expected_clusters, ambiguity, projection_distance = expected_point_clusters(
        raw, evaluated_triangles, truth
    )

    coordinate_columns = ["X", "Y", "Z", "NX", "NY", "NZ"]
    point_cloud_difference = float(
        np.max(
            np.abs(
                raw[coordinate_columns].to_numpy(dtype=float)
                - point_cloud[coordinate_columns].to_numpy(dtype=float)
            )
        )
    )
    coordinate_difference = float(
        np.max(
            np.abs(
                raw[coordinate_columns].to_numpy(dtype=float)
                - verified[coordinate_columns].to_numpy(dtype=float)
            )
        )
    )
    actual_clusters = verified["ClusterID"].to_numpy(dtype=int)
    assignment_exact = np.array_equal(actual_clusters, expected_clusters)
    accepted_count = int(np.sum(actual_clusters >= 0))
    residual_count = int(np.sum(actual_clusters < 0))
    cluster_counts = {
        int(value): int(np.sum(actual_clusters == value))
        for value in sorted(set(actual_clusters.tolist()))
    }
    expected_face_clusters = {int(value["cluster_id"]) for value in truth["surfaces"]}
    actual_face_clusters = {int(value) for value in faces["ClusterID"]}
    segmentation_pass = (
        len(verified) == 10000
        and accepted_count + residual_count == 10000
        and coordinate_difference == 0.0
        and len(point_cloud) == 10000
        and point_cloud_difference <= 1e-12
        and assignment_exact
        and actual_face_clusters == expected_face_clusters
        and all(int(value["mesh_connected_components"]) == 1 for value in truth["surfaces"])
    )

    face_by_cluster = {int(row["ClusterID"]): row for _, row in faces.iterrows()}
    geometry_details: list[dict[str, Any]] = []
    geometry_pass = actual_face_clusters == expected_face_clusters
    for surface in truth["surfaces"]:
        cluster_id = int(surface["cluster_id"])
        row = face_by_cluster.get(cluster_id)
        if row is None:
            geometry_pass = False
            continue
        row_pass = (
            str(row["TruthSurfaceID"]) == surface["surface_id"]
            and str(row["FeatureType"]) == surface["feature_type"]
            and int(row["PointCount"]) == cluster_counts.get(cluster_id, 0)
            and float(row["FitResidualMax"]) <= FIT_RESIDUAL_THRESHOLD_MM
            and float(row["NormalConsistencyMin"]) >= NORMAL_THRESHOLD
            and int(row["MeshTriangleCount"]) == int(surface["triangle_count"])
            and int(row["MeshConnectedComponents"]) == 1
            and str(row["ValidationStatus"]) == "PASS"
        )
        geometry_pass &= row_pass
        geometry_details.append(
            {
                "cluster_id": cluster_id,
                "fit_residual_max_mm": float(row["FitResidualMax"]),
                "normal_consistency_min": float(row["NormalConsistencyMin"]),
                "status": "PASS" if row_pass else "FAIL",
            }
        )

    topology_pass, topology_details = compare_topology(topology, truth)
    candidate_pass, candidate_details = compare_candidates(candidates, truth)
    csg = json.loads(csg_path.read_text(encoding="utf-8"))
    csg_pass = csg.get("tree") == truth["canonical_csg_tree"]
    five_layers = {
        "segmentation": "PASS" if segmentation_pass else "FAIL",
        "geometry_semantics": "PASS" if geometry_pass else "FAIL",
        "topology": "PASS" if topology_pass else "FAIL",
        "primitive_candidates": "PASS" if candidate_pass else "FAIL",
        "csg_symbolic_tree": "PASS" if csg_pass else "FAIL",
    }
    overall_pass = all(value == "PASS" for value in five_layers.values())
    blend_manifest = json.loads(arguments.blend_manifest.read_text(encoding="utf-8"))
    truth_manifest = json.loads(arguments.truth_manifest.read_text(encoding="utf-8"))
    evidence_integrity = (
        blend_manifest["output_sha256"] == sha256(arguments.evaluated_mesh)
        and truth_manifest["only_geometry_input"]["sha256"] == sha256(arguments.evaluated_mesh)
        and truth_manifest.get("forbidden_inputs_read") == []
        and truth["source"]["sha256"] == sha256(arguments.evaluated_mesh)
    )
    overall_pass &= evidence_integrity
    summary = {
        "schema_version": "2.0",
        "case": truth["case"],
        "display_name": truth["display_name"],
        "truth_basis": "evaluated final mesh exported from the supplied Blend file; original STL retained and compared independently",
        "parameters": {
            "point_count": 10000,
            "seed": 42,
            "distance_threshold_mm": 2.0,
            "normal_threshold": NORMAL_THRESHOLD,
            "fit_residual_threshold_mm": FIT_RESIDUAL_THRESHOLD_MM,
        },
        "counts": {
            "total_points": len(verified),
            "accepted_points": accepted_count,
            "residual_points": residual_count,
            "accepted_faces": len(faces),
            "residual_mesh_components": len(truth.get("residual_mesh_components", [])),
            "topology_edges": len(topology),
            "primitive_candidates": len(candidates),
        },
        "invariants": {
            "coordinate_normal_max_difference": coordinate_difference,
            "raw_point_cloud_vs_result_max_difference": point_cloud_difference,
            "point_assignment_exact_match": assignment_exact,
            "point_to_evaluated_mesh_projection_distance_max_mm": float(np.max(projection_distance)),
            "ambiguous_exact_triangle_matches": int(np.sum(ambiguity > 1)),
        },
        "original_stl_vs_blend_evaluated_mesh": {
            **mesh_bidirectional_distance(original_triangles, evaluated_triangles),
            "original_stl_sha256": sha256(arguments.original_stl),
            "blend_sha256": sha256(arguments.blend),
            "evaluated_mesh_sha256": sha256(arguments.evaluated_mesh),
            "interpretation": "The evaluated Blend mesh is used for point-level truth because the supplied points were generated from that mesh; the original STL is preserved as a separate comparison artifact.",
        },
        "five_layer_validation": five_layers,
        "details": {
            "geometry_semantics": geometry_details,
            "topology": topology_details,
            "primitive_candidates": candidate_details,
            "csg_exact_match": csg_pass,
            "evidence_integrity": evidence_integrity,
        },
        "overall": "PASS" if overall_pass else "FAIL",
        "input_sha256": {
            "blend": sha256(arguments.blend),
            "original_stl": sha256(arguments.original_stl),
            "evaluated_mesh": sha256(arguments.evaluated_mesh),
            "raw_result": sha256(arguments.raw_result),
            "point_cloud": sha256(arguments.point_cloud),
            "raw_face_summary": sha256(arguments.raw_face),
            "raw_topology": sha256(arguments.raw_topology),
            "raw_primitive_candidates": sha256(arguments.raw_candidates),
            "independent_truth": sha256(arguments.truth),
            "blend_export_manifest": sha256(arguments.blend_manifest),
            "truth_build_manifest": sha256(arguments.truth_manifest),
        },
        "output_sha256": {path.name: sha256(path) for path in required_paths},
        "limits": [
            "STL-generated point-normal data only; no real-scan validation.",
            "Only planar and cylindrical accepted surfaces are evaluated; explicit residuals are retained.",
            "CSG validation ends at the canonical symbolic inference tree; no editable CAD solid is asserted.",
        ],
    }
    summary_path = output_dir / f"ValidationSummary_{case_file}_v2.json"
    write_json(summary_path, summary)
    if not overall_pass:
        raise SystemExit(2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate L-Bracket or Model A against independent evaluated-mesh truth.")
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--original-stl", required=True, type=Path)
    parser.add_argument("--evaluated-mesh", required=True, type=Path)
    parser.add_argument("--blend-manifest", required=True, type=Path)
    parser.add_argument("--raw-result", required=True, type=Path)
    parser.add_argument("--point-cloud", required=True, type=Path)
    parser.add_argument("--raw-face", required=True, type=Path)
    parser.add_argument("--raw-topology", required=True, type=Path)
    parser.add_argument("--raw-candidates", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--truth-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    for name in (
        "blend", "original_stl", "evaluated_mesh", "blend_manifest", "raw_result",
        "point_cloud", "raw_face", "raw_topology", "raw_candidates",
        "truth", "truth_manifest", "output_dir",
    ):
        setattr(arguments, name, getattr(arguments, name).resolve())
    summary = validate(arguments)
    print(
        f"{summary['case']}: {summary['overall']} | accepted={summary['counts']['accepted_points']} "
        f"residual={summary['counts']['residual_points']} faces={summary['counts']['accepted_faces']} "
        f"topology={summary['counts']['topology_edges']} candidates={summary['counts']['primitive_candidates']}"
    )


if __name__ == "__main__":
    main()
