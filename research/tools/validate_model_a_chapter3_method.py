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

from build_stepped_cylinder_independent_truth import read_stl_triangles, sha256
from validate_lbracket_modela_v2 import expected_point_clusters


FIT_RESIDUAL_THRESHOLD_MM = 1.5
NORMAL_THRESHOLD = 0.93
ENDCAP_DOT_THRESHOLD = 0.95
BASE_PARAMETER_TOLERANCE_MM = 0.05
ALLOWED_EDGE_TYPES = {"Adjacency", "OrthogonalAdjacency", "EndCap"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            formatted = {}
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, (float, np.floating)):
                    formatted[field] = "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
                else:
                    formatted[field] = value
            writer.writerow(formatted)


def parse_clusters(value: Any) -> list[int]:
    return sorted(int(item.strip()) for item in str(value).split(";") if item.strip())


def normalize_pair(first: Any, second: Any) -> tuple[int, int]:
    values = sorted((int(first), int(second)))
    return values[0], values[1]


def numeric_vector(row: pd.Series, fields: list[str]) -> np.ndarray:
    vector = np.asarray([float(row[field]) for field in fields], dtype=float)
    vector /= max(float(np.linalg.norm(vector)), 1e-12)
    return vector


def validate(arguments: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    truth = load_json(arguments.truth)
    manifest = load_json(arguments.inference_manifest)
    raw = pd.read_csv(arguments.raw_result)
    point_cloud = pd.read_csv(arguments.point_cloud)
    verified = pd.read_csv(arguments.verified_result)
    faces = pd.read_csv(arguments.face_summary)
    topology = pd.read_csv(arguments.topology)
    candidates = pd.read_csv(arguments.candidates)
    csg = load_json(arguments.csg)
    evaluated_triangles = read_stl_triangles(arguments.evaluated_mesh)
    expected_clusters, ambiguity, projection_distance = expected_point_clusters(
        raw, evaluated_triangles, truth
    )

    coordinate_columns = ["X", "Y", "Z", "NX", "NY", "NZ"]
    coordinate_difference = float(
        np.max(
            np.abs(
                raw[coordinate_columns].to_numpy(float)
                - verified[coordinate_columns].to_numpy(float)
            )
        )
    )
    point_cloud_difference = float(
        np.max(
            np.abs(
                raw[coordinate_columns].to_numpy(float)
                - point_cloud[coordinate_columns].to_numpy(float)
            )
        )
    )
    actual_clusters = verified["ClusterID"].to_numpy(int)
    assignment_exact = np.array_equal(actual_clusters, expected_clusters)
    accepted_points = int(np.sum(actual_clusters >= 0))
    residual_points = int(np.sum(actual_clusters < 0))
    cluster_counts = {
        int(value): int(np.sum(actual_clusters == value))
        for value in sorted(set(actual_clusters.tolist()))
    }
    expected_face_clusters = {int(value["cluster_id"]) for value in truth["surfaces"]}
    actual_face_clusters = {int(value) for value in faces["ClusterID"]}
    segmentation_pass = (
        len(raw) == len(point_cloud) == len(verified) == 10000
        and accepted_points + residual_points == 10000
        and coordinate_difference == 0.0
        and point_cloud_difference <= 1e-12
        and assignment_exact
        and actual_face_clusters == expected_face_clusters
        and all(int(value["mesh_connected_components"]) == 1 for value in truth["surfaces"])
    )

    face_by_cluster = {int(row["ClusterID"]): row for _, row in faces.iterrows()}
    surface_mapping: list[dict[str, Any]] = []
    geometry_checks: list[bool] = []
    for surface in truth["surfaces"]:
        cluster_id = int(surface["cluster_id"])
        row = face_by_cluster.get(cluster_id)
        status = False
        direction_agreement = math.nan
        position_or_radius_error = math.nan
        parameter_tolerance = FIT_RESIDUAL_THRESHOLD_MM
        if row is not None:
            feature_match = str(row["FeatureType"]) == str(surface["feature_type"])
            semantic_match = str(row.get("SemanticRole", "")) == str(surface["semantic_role"])
            point_count_match = int(row["PointCount"]) == cluster_counts.get(cluster_id, 0)
            quality_pass = (
                float(row["FitResidualMax"]) <= FIT_RESIDUAL_THRESHOLD_MM
                and float(row["NormalConsistencyMin"]) >= NORMAL_THRESHOLD
                and str(row["ValidationStatus"]) == "PASS"
            )
            if surface["geometry"] == "plane":
                reported_direction = numeric_vector(row, ["NX", "NY", "NZ"])
                truth_direction = np.asarray(surface["normal"], dtype=float)
                truth_direction /= max(float(np.linalg.norm(truth_direction)), 1e-12)
                direction_agreement = abs(float(reported_direction @ truth_direction))
                reported_center = np.asarray(
                    [float(row["CenterX"]), float(row["CenterY"]), float(row["CenterZ"])],
                    dtype=float,
                )
                truth_offset = float(surface.get("plane_offset_mm", truth_direction @ reported_center))
                position_or_radius_error = abs(float(reported_center @ truth_direction) - truth_offset)
                parameter_tolerance = FIT_RESIDUAL_THRESHOLD_MM
                parameter_pass = (
                    direction_agreement >= NORMAL_THRESHOLD
                    and position_or_radius_error <= parameter_tolerance
                )
            else:
                reported_direction = numeric_vector(row, ["AxisX", "AxisY", "AxisZ"])
                truth_direction = np.asarray(surface["axis"], dtype=float)
                truth_direction /= max(float(np.linalg.norm(truth_direction)), 1e-12)
                direction_agreement = abs(float(reported_direction @ truth_direction))
                position_or_radius_error = abs(float(row["Radius"]) - float(surface["radius_mm"]))
                parameter_tolerance = max(
                    BASE_PARAMETER_TOLERANCE_MM,
                    float(surface.get("support_error_max_mm", 0.0)) + 1e-6,
                )
                parameter_pass = (
                    direction_agreement >= ENDCAP_DOT_THRESHOLD
                    and position_or_radius_error <= parameter_tolerance
                )
            status = all(
                (feature_match, semantic_match, point_count_match, quality_pass, parameter_pass)
            )
        geometry_checks.append(status)
        surface_mapping.append(
            {
                "ClusterID": cluster_id,
                "TruthSurfaceID": surface["surface_id"],
                "Geometry": surface["geometry"],
                "SemanticRole": surface["semantic_role"],
                "PointCount": cluster_counts.get(cluster_id, 0),
                "DirectionAgreement": direction_agreement,
                "PositionOrRadiusErrorMM": position_or_radius_error,
                "ParameterToleranceMM": parameter_tolerance,
                "ValidationStatus": "PASS" if status else "FAIL",
            }
        )
    geometry_pass = all(geometry_checks) and len(faces) == len(truth["surfaces"])

    observed_topology = {
        (*normalize_pair(row.FromClusterID, row.ToClusterID), str(row.EdgeType))
        for row in topology.itertuples(index=False)
    }
    truth_topology = {
        (*normalize_pair(edge["from_cluster_id"], edge["to_cluster_id"]), edge["edge_type"])
        for edge in truth["topology_edges"]
    }
    topology_ordered = all(
        int(row.FromClusterID) < int(row.ToClusterID) for row in topology.itertuples(index=False)
    )
    topology_types_allowed = set(str(value) for value in topology["EdgeType"]) <= ALLOWED_EDGE_TYPES
    topology_rules_pass = set(str(value) for value in topology["RuleStatus"]) == {"PASS"}
    topology_pass = (
        observed_topology == truth_topology
        and len(topology) == len(truth_topology)
        and topology_ordered
        and topology_types_allowed
        and topology_rules_pass
    )

    expected_candidates = {str(value["candidate_id"]): value for value in truth["primitive_candidates"]}
    observed_candidates = {str(row["CandidateID"]): row for _, row in candidates.iterrows()}
    candidate_mapping: list[dict[str, Any]] = []
    candidate_checks: list[bool] = []
    for candidate_id in sorted(set(expected_candidates) | set(observed_candidates)):
        expected = expected_candidates.get(candidate_id)
        observed = observed_candidates.get(candidate_id)
        if expected is None or observed is None:
            candidate_checks.append(False)
            candidate_mapping.append(
                {"CandidateID": candidate_id, "ValidationStatus": "FAIL", "Reason": "missing or unexpected candidate"}
            )
            continue
        related = parse_clusters(observed["RelatedClusters"])
        identity_pass = (
            str(observed["PrimitiveType"]) == str(expected["primitive_type"])
            and str(observed["BooleanType"]) == str(expected["boolean_type"])
            and related == sorted(int(value) for value in expected["related_cluster_ids"])
            and str(observed["RuleStatus"]) == "PASS"
        )
        related_residual = max(float(face_by_cluster[value]["FitResidualMax"]) for value in related)
        parameter_tolerance = max(BASE_PARAMETER_TOLERANCE_MM, related_residual + 1e-6)
        errors: dict[str, float] = {}
        for truth_field, output_field in (
            ("length_mm", "Length"),
            ("width_mm", "Width"),
            ("height_mm", "Height"),
            ("radius_mm", "Radius"),
            ("depth_mm", "Depth"),
        ):
            if truth_field in expected:
                errors[output_field] = abs(float(observed[output_field]) - float(expected[truth_field]))
        parameter_pass = all(value <= parameter_tolerance for value in errors.values())
        status = identity_pass and parameter_pass
        candidate_checks.append(status)
        candidate_mapping.append(
            {
                "CandidateID": candidate_id,
                "PrimitiveType": str(observed["PrimitiveType"]),
                "BooleanType": str(observed["BooleanType"]),
                "RelatedClusters": ";".join(str(value) for value in related),
                "ParameterErrorsMM": json.dumps(errors, ensure_ascii=False, sort_keys=True),
                "ParameterToleranceMM": parameter_tolerance,
                "ValidationStatus": "PASS" if status else "FAIL",
                "Reason": "",
            }
        )
    candidate_pass = (
        set(observed_candidates) == set(expected_candidates)
        and all(candidate_checks)
        and len(candidates) == len(expected_candidates)
    )

    csg_tree = csg.get("tree", csg)
    csg_pass = csg_tree == truth["canonical_csg_tree"]
    only_original_result = set(manifest.get("inputs_read", {})) == {"result"}
    provenance_pass = (
        only_original_result
        and manifest.get("forbidden_inputs_read") == []
        and manifest.get("truth_or_mesh_used_for_inference") is False
    )

    blend_manifest = load_json(arguments.blend_manifest)
    truth_manifest = load_json(arguments.truth_manifest)
    evidence_integrity = (
        blend_manifest["output_sha256"] == sha256(arguments.evaluated_mesh)
        and truth_manifest["only_geometry_input"]["sha256"] == sha256(arguments.evaluated_mesh)
        and truth_manifest.get("forbidden_inputs_read") == []
        and truth["source"]["sha256"] == sha256(arguments.evaluated_mesh)
    )
    five_layer = {
        "segmentation": "PASS" if segmentation_pass else "FAIL",
        "geometry_semantics": "PASS" if geometry_pass else "FAIL",
        "topology": "PASS" if topology_pass else "FAIL",
        "primitive_candidates": "PASS" if candidate_pass else "FAIL",
        "csg_symbolic_tree": "PASS" if csg_pass else "FAIL",
    }
    overall_pass = (
        all(value == "PASS" for value in five_layer.values())
        and provenance_pass
        and evidence_integrity
    )
    summary = {
        "schema_version": "3.0",
        "case": "Model A",
        "validation_scope": "method-only Result inference compared after completion against independent evaluated-mesh truth",
        "method_source_separation": {
            "only_original_result_read": only_original_result,
            "forbidden_inputs_read_is_empty": manifest.get("forbidden_inputs_read") == [],
            "truth_or_mesh_used_for_inference": manifest.get("truth_or_mesh_used_for_inference"),
            "status": "PASS" if provenance_pass else "FAIL",
        },
        "counts": {
            "total_points": len(verified),
            "accepted_points": accepted_points,
            "residual_points": residual_points,
            "accepted_faces": len(faces),
            "residual_mesh_components": len(truth.get("residual_mesh_components", [])),
            "topology_edges": len(topology),
            "primitive_candidates": len(candidates),
        },
        "input_integrity": {
            "coordinate_normal_max_difference": coordinate_difference,
            "raw_point_cloud_vs_result_max_difference": point_cloud_difference,
            "point_assignment_exact_match": assignment_exact,
            "point_to_evaluated_mesh_projection_distance_max_mm": float(np.max(projection_distance)),
            "ambiguous_exact_triangle_matches": int(np.sum(ambiguity > 1)),
            "pass": coordinate_difference == 0.0 and point_cloud_difference <= 1e-12,
        },
        "five_layer_validation": five_layer,
        "details": {
            "failed_surface_clusters": [
                row["ClusterID"] for row in surface_mapping if row["ValidationStatus"] == "FAIL"
            ],
            "topology_missing": sorted(truth_topology - observed_topology),
            "topology_unexpected": sorted(observed_topology - truth_topology),
            "failed_candidates": [
                row["CandidateID"] for row in candidate_mapping if row["ValidationStatus"] == "FAIL"
            ],
            "csg_exact_match": csg_pass,
            "independent_truth_evidence_integrity": evidence_integrity,
        },
        "overall": "PASS" if overall_pass else "FAIL",
        "limits": [
            "STL-generated point-normal data only; no real-scan validation.",
            "Only planar and cylindrical accepted surfaces are evaluated; explicit residuals are retained.",
            "CSG validation ends at the canonical symbolic inference tree; no editable CAD solid is asserted.",
        ],
        "input_sha256": {
            "raw_result": sha256(arguments.raw_result),
            "point_cloud": sha256(arguments.point_cloud),
            "evaluated_mesh": sha256(arguments.evaluated_mesh),
            "independent_truth": sha256(arguments.truth),
            "inference_manifest": sha256(arguments.inference_manifest),
        },
    }
    return summary, surface_mapping, candidate_mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate truth-free Model A inference against independent mesh truth.")
    parser.add_argument("--raw-result", required=True, type=Path)
    parser.add_argument("--point-cloud", required=True, type=Path)
    parser.add_argument("--evaluated-mesh", required=True, type=Path)
    parser.add_argument("--blend-manifest", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--truth-manifest", required=True, type=Path)
    parser.add_argument("--verified-result", required=True, type=Path)
    parser.add_argument("--face-summary", required=True, type=Path)
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--csg", required=True, type=Path)
    parser.add_argument("--inference-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    for name in vars(arguments):
        value = getattr(arguments, name)
        if isinstance(value, Path):
            setattr(arguments, name, value.resolve())
    summary, surface_rows, candidate_rows = validate(arguments)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(arguments.output_dir / "ValidationAgainstIndependentTruth_Model_A.json", summary)
    write_csv(
        arguments.output_dir / "SurfaceMapping_Model_A_chapter3.csv",
        [
            "ClusterID", "TruthSurfaceID", "Geometry", "SemanticRole", "PointCount",
            "DirectionAgreement", "PositionOrRadiusErrorMM", "ParameterToleranceMM", "ValidationStatus",
        ],
        surface_rows,
    )
    write_csv(
        arguments.output_dir / "CandidateMapping_Model_A_chapter3.csv",
        [
            "CandidateID", "PrimitiveType", "BooleanType", "RelatedClusters", "ParameterErrorsMM",
            "ParameterToleranceMM", "ValidationStatus", "Reason",
        ],
        candidate_rows,
    )
    if summary["overall"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
