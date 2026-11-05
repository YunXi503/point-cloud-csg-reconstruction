from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_stepped_cylinder_independent_truth import read_stl_triangles, sha256
from validate_lbracket_modela_v2 import expected_point_clusters, mesh_bidirectional_distance, parse_clusters


FIT_RESIDUAL_THRESHOLD_MM = 1.5
NORMAL_THRESHOLD = 0.93
ORTHOGONAL_DOT_THRESHOLD = 0.2
ADJACENCY_DISTANCE_THRESHOLD_MM = 2.0
ENDCAP_DISTANCE_THRESHOLD_MM = 5.0
ENDCAP_DOT_THRESHOLD = 0.95
ALLOWED_EDGE_TYPES = {"Adjacency", "OrthogonalAdjacency", "EndCap"}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_pair(first: Any, second: Any) -> tuple[int, int]:
    values = sorted((int(first), int(second)))
    return values[0], values[1]


def compare_topology(frame: pd.DataFrame, truth: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    required = {
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "DistanceThreshold", "DirectionThreshold", "RuleStatus", "InferenceRule",
    }
    schema_pass = required <= set(frame.columns)
    actual = {
        (*normalize_pair(row.FromClusterID, row.ToClusterID), str(row.EdgeType))
        for row in frame.itertuples(index=False)
    }
    expected = {
        (*normalize_pair(edge["from_cluster_id"], edge["to_cluster_id"]), str(edge["edge_type"]))
        for edge in truth["topology_edges"]
    }
    rule_failures: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        edge_type = str(row.EdgeType)
        distance = float(row.MinDistance)
        direction = float(row.DirectionDot) if not pd.isna(row.DirectionDot) else math.nan
        if edge_type == "OrthogonalAdjacency":
            passed = distance <= ADJACENCY_DISTANCE_THRESHOLD_MM and direction < ORTHOGONAL_DOT_THRESHOLD
        elif edge_type == "EndCap":
            passed = distance <= ENDCAP_DISTANCE_THRESHOLD_MM and direction > ENDCAP_DOT_THRESHOLD
        else:
            passed = distance <= ADJACENCY_DISTANCE_THRESHOLD_MM
        if not passed or str(row.RuleStatus) != "PASS":
            rule_failures.append(
                {
                    "pair": list(normalize_pair(row.FromClusterID, row.ToClusterID)),
                    "edge_type": edge_type,
                    "min_distance_mm": distance,
                    "direction_dot": direction,
                }
            )
    allowed = set(str(value) for value in frame["EdgeType"]) <= ALLOWED_EDGE_TYPES
    passed = schema_pass and actual == expected and allowed and not rule_failures
    return passed, {
        "schema_pass": schema_pass,
        "required_columns": sorted(required),
        "expected_edge_count": len(expected),
        "actual_edge_count": len(actual),
        "edge_type_counts": {str(key): int(value) for key, value in frame["EdgeType"].value_counts().sort_index().items()},
        "missing": sorted(expected - actual),
        "unexpected": sorted(actual - expected),
        "edge_types_allowed": allowed,
        "rule_failures": rule_failures,
        "orthogonal_distance_max_mm": float(frame.loc[frame.EdgeType == "OrthogonalAdjacency", "MinDistance"].max()),
        "orthogonal_direction_dot_max": float(frame.loc[frame.EdgeType == "OrthogonalAdjacency", "DirectionDot"].max()),
        "endcap_distance_max_mm": float(frame.loc[frame.EdgeType == "EndCap", "MinDistance"].max()),
        "endcap_direction_dot_min": float(frame.loc[frame.EdgeType == "EndCap", "DirectionDot"].min()),
    }


def compare_candidates(frame: pd.DataFrame, truth: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    expected = {str(value["candidate_id"]): value for value in truth["primitive_candidates"]}
    actual = {str(row["CandidateID"]): row for _, row in frame.iterrows()}
    surface_by_cluster = {int(value["cluster_id"]): value for value in truth["surfaces"]}
    passed = set(expected) == set(actual)
    details: list[dict[str, Any]] = []
    for candidate_id in sorted(expected):
        expected_row = expected[candidate_id]
        actual_row = actual.get(candidate_id)
        if actual_row is None:
            details.append({"candidate_id": candidate_id, "status": "MISSING"})
            passed = False
            continue
        identity_pass = (
            str(actual_row["PrimitiveType"]) == str(expected_row["primitive_type"])
            and str(actual_row["BooleanType"]) == str(expected_row["boolean_type"])
            and parse_clusters(actual_row["RelatedClusters"]) == sorted(int(value) for value in expected_row["related_cluster_ids"])
        )
        errors: dict[str, float] = {}
        tolerances: dict[str, float] = {}
        for truth_key, csv_key in (
            ("length_mm", "Length"), ("width_mm", "Width"), ("height_mm", "Height"),
            ("radius_mm", "Radius"), ("depth_mm", "Depth"),
        ):
            if truth_key not in expected_row:
                continue
            errors[csv_key] = abs(float(actual_row[csv_key]) - float(expected_row[truth_key]))
            if truth_key in {"radius_mm", "depth_mm"}:
                cylinder_ids = [
                    int(value) for value in expected_row["related_cluster_ids"]
                    if surface_by_cluster[int(value)]["geometry"] == "cylinder"
                ]
                support = max(
                    [float(surface_by_cluster[value].get("support_error_max_mm", 0.0)) for value in cylinder_ids]
                    or [0.0]
                )
                tolerances[csv_key] = max(0.05, support + 1e-6)
            else:
                tolerances[csv_key] = 1e-5
        parameter_pass = all(errors[key] <= tolerances[key] for key in errors)
        row_pass = identity_pass and parameter_pass and str(actual_row["RuleStatus"]) == "PASS"
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
    return passed, {"expected_count": len(expected), "actual_count": len(actual), "details": details}


def validate(arguments: argparse.Namespace) -> dict[str, Any]:
    output_dir = arguments.output_dir.resolve()
    truth = json.loads(arguments.truth.read_text(encoding="utf-8"))
    if truth.get("case_key") != "l_bracket":
        raise ValueError("此驗證程式只處理 L-Bracket。")
    paths = {
        "result": output_dir / "Result_L_Bracket_chapter3_verified.csv",
        "faces": output_dir / "FaceSummary_L_Bracket_chapter3_verified.csv",
        "topology": output_dir / "TopologyEdges_L_Bracket_chapter3_verified.csv",
        "candidates": output_dir / "PrimitiveCandidates_L_Bracket_chapter3_verified.csv",
        "csg": output_dir / "CSGTree_L_Bracket_chapter3_verified.json",
        "trace": output_dir / "CorrectionTrace_L_Bracket_chapter3.csv",
        "manifest": output_dir / "MethodInferenceManifest_L_Bracket_chapter3.json",
    }
    missing = [path.name for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"缺少第三章方法輸出：{missing}")

    raw = pd.read_csv(arguments.raw_result)
    result = pd.read_csv(paths["result"])
    faces = pd.read_csv(paths["faces"])
    topology = pd.read_csv(paths["topology"])
    candidates = pd.read_csv(paths["candidates"])
    csg = json.loads(paths["csg"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    evaluated_triangles = read_stl_triangles(arguments.evaluated_mesh)
    expected_clusters, ambiguity, projection_distance = expected_point_clusters(raw, evaluated_triangles, truth)

    coordinate_columns = ["X", "Y", "Z", "NX", "NY", "NZ"]
    coordinate_difference = float(np.max(np.abs(raw[coordinate_columns].to_numpy(float) - result[coordinate_columns].to_numpy(float))))
    assignment_exact = bool(np.array_equal(result["ClusterID"].to_numpy(int), expected_clusters.astype(int)))
    accepted = int(np.sum(result["ClusterID"].to_numpy(int) >= 0))
    residual = int(np.sum(result["ClusterID"].to_numpy(int) < 0))
    segmentation_pass = len(result) == 10000 and accepted + residual == 10000 and coordinate_difference <= 1e-12 and assignment_exact

    truth_surfaces = {int(value["cluster_id"]): value for value in truth["surfaces"]}
    geometry_details: list[dict[str, Any]] = []
    geometry_pass = set(faces["ClusterID"].astype(int)) == set(truth_surfaces)
    for _, row in faces.sort_values("ClusterID").iterrows():
        cluster_id = int(row["ClusterID"])
        expected_geometry = truth_surfaces[cluster_id]["geometry"]
        actual_geometry = "cylinder" if str(row["FeatureType"]).startswith("Cylinder") else "plane"
        row_pass = (
            actual_geometry == expected_geometry
            and float(row["FitResidualMax"]) <= FIT_RESIDUAL_THRESHOLD_MM
            and float(row["NormalConsistencyMin"]) >= NORMAL_THRESHOLD
            and str(row["ValidationStatus"]) == "PASS"
        )
        geometry_pass &= row_pass
        geometry_details.append(
            {
                "cluster_id": cluster_id,
                "geometry": actual_geometry,
                "fit_residual_max_mm": float(row["FitResidualMax"]),
                "normal_consistency_min": float(row["NormalConsistencyMin"]),
                "status": "PASS" if row_pass else "FAIL",
            }
        )

    topology_pass, topology_details = compare_topology(topology, truth)
    candidate_pass, candidate_details = compare_candidates(candidates, truth)
    csg_pass = csg.get("tree") == truth["canonical_csg_tree"]
    manifest_outputs_match = all(
        paths[key].name in manifest.get("outputs", {})
        and manifest["outputs"][paths[key].name] == sha256(paths[key])
        for key in ("result", "faces", "topology", "candidates", "csg", "trace")
    )
    provenance_pass = (
        manifest.get("truth_or_mesh_used_for_inference") is False
        and manifest.get("forbidden_inputs_read") == []
        and set(manifest.get("inputs_read", {})) == {"result"}
        and manifest_outputs_match
    )
    five_layers = {
        "segmentation": "PASS" if segmentation_pass else "FAIL",
        "geometry_semantics": "PASS" if geometry_pass else "FAIL",
        "topology": "PASS" if topology_pass else "FAIL",
        "primitive_candidates": "PASS" if candidate_pass else "FAIL",
        "csg_symbolic_tree": "PASS" if csg_pass else "FAIL",
    }
    overall_pass = all(value == "PASS" for value in five_layers.values()) and provenance_pass
    original_triangles = read_stl_triangles(arguments.original_stl)
    mesh_comparison = mesh_bidirectional_distance(original_triangles, evaluated_triangles)
    summary = {
        "schema_version": "3.0",
        "case": "L-Bracket",
        "display_name": "L型板",
        "method_output_basis": "raw point-normal Result only; Chapter 3 formulas (3-3) through (3-7)",
        "independent_truth_basis": "evaluated final Blend mesh; used only after inference for QA comparison",
        "provenance_separation": "PASS" if provenance_pass else "FAIL",
        "parameters": manifest["parameters"],
        "counts": {
            "total_points": len(result),
            "initial_region_components": int(manifest["counts"]["initial_region_components"]),
            "accepted_points": accepted,
            "residual_points": residual,
            "accepted_faces": len(faces),
            "topology_edges": len(topology),
            "primitive_candidates": len(candidates),
        },
        "invariants": {
            "coordinate_normal_max_difference": coordinate_difference,
            "point_assignment_exact_match_to_independent_truth": assignment_exact,
            "point_to_evaluated_mesh_projection_distance_max_mm": float(np.max(projection_distance)),
            "ambiguous_exact_triangle_matches": int(np.sum(ambiguity > 1)),
        },
        "original_stl_vs_blend_evaluated_mesh": mesh_comparison,
        "five_layer_validation": five_layers,
        "details": {
            "segmentation": {
                "method_input_excludes_truth_and_mesh": provenance_pass,
                "initial_region_components": int(manifest["counts"]["initial_region_components"]),
                "final_semantic_faces": len(faces),
                "point_assignment_exact_match": assignment_exact,
            },
            "geometry_semantics": geometry_details,
            "topology": topology_details,
            "primitive_candidates": candidate_details,
            "csg_exact_match": csg_pass,
        },
        "overall": "PASS" if overall_pass else "FAIL",
        "input_sha256": {
            "raw_result": sha256(arguments.raw_result),
            "original_stl": sha256(arguments.original_stl),
            "evaluated_mesh": sha256(arguments.evaluated_mesh),
            "independent_truth": sha256(arguments.truth),
            "method_manifest": sha256(paths["manifest"]),
        },
        "output_sha256": {path.name: sha256(path) for key, path in paths.items() if key != "manifest"},
        "limits": [
            "STL-generated point-normal data only; no real-scan validation.",
            "Only planar and cylindrical surfaces are evaluated.",
            "Candidate inference includes transparent L-Bracket semantic-role rules and manual geometric verification; it is not claimed as fully automatic.",
            "CSG validation ends at the canonical symbolic inference tree; no editable CAD solid is asserted.",
        ],
    }
    output_path = output_dir / "ValidationSummary_L_Bracket_chapter3.json"
    write_json(output_path, summary)
    if not overall_pass:
        raise SystemExit(2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate L-Bracket Chapter 3 method outputs against independent mesh truth.")
    parser.add_argument("--raw-result", required=True, type=Path)
    parser.add_argument("--original-stl", required=True, type=Path)
    parser.add_argument("--evaluated-mesh", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    for name in ("raw_result", "original_stl", "evaluated_mesh", "truth", "output_dir"):
        setattr(arguments, name, getattr(arguments, name).resolve())
    summary = validate(arguments)
    print(
        f"L-Bracket Chapter 3: {summary['overall']} | "
        f"faces={summary['counts']['accepted_faces']} topology={summary['counts']['topology_edges']} "
        f"candidates={summary['counts']['primitive_candidates']} provenance={summary['provenance_separation']}"
    )


if __name__ == "__main__":
    main()
