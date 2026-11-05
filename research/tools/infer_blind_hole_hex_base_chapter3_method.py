"""盲孔六角座（Blind-Hole Hex Base）第三章方法推論。

與階梯狀圓柱／L型板／模型A 相同：僅讀取原始 Result CSV（點座標、法向量、
點級 ClusterID）與第三章公開規則，不讀取任何獨立真值、網格面或候選模板。
幾何函式、擬合門檻與拓樸判準全部沿用 infer_stepped_cylinder_chapter3_method，
以確保三個既有範例與本範例套用同一套方法。

本範例新增之處僅為 3.8 節的貫穿孔／盲孔分類：圓柱孔兩端 EndCap 之中，若有一
端平面之支撐為覆蓋孔截面的圓盤（內部封底），則判為盲孔，Depth 記錄自開口至
該封底平面的有限深度；若兩端皆為環域開口，則判為貫穿孔。
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from infer_stepped_cylinder_chapter3_method import (
    DISTANCE_THRESHOLD_MM,
    ENDCAP_DISTANCE_THRESHOLD_MM,
    ENDCAP_DOT_THRESHOLD,
    FIT_RESIDUAL_THRESHOLD_MM,
    NORMAL_THRESHOLD,
    ORTHOGONAL_DOT_THRESHOLD,
    build_topology,
    canonical_direction,
    cylinder_surface_sense,
    infer_surfaces,
    sha256,
    write_csv,
    write_json,
    write_result_preserving_values,
)


HEX_SIDE_COUNT = 6


FEATURE_NAMES = {
    "hex_bottom": "Plane_Horizontal (六角底面)",
    "hex_shelf": "Plane_Horizontal (六角肩面)",
    "ring_top": "Plane_Horizontal (環台頂面)",
    "blind_hole_floor": "Plane_Horizontal (盲孔底面)",
    "ring_outer_side": "Cylinder_axisZ_outer (環台外圓柱)",
    "blind_hole_side": "Cylinder_axisZ_inner (盲孔內壁)",
}
for _index in range(1, HEX_SIDE_COUNT + 1):
    FEATURE_NAMES[f"hex_side_{_index}"] = f"Plane_Vertical (六角側面{_index})"


def radial_extent(
    surface: dict[str, Any], points: np.ndarray, axis: np.ndarray, center: np.ndarray
) -> tuple[float, float]:
    """回傳該面支撐點相對共同軸線的最小與最大徑向距離。"""
    delta = points[surface["indices"]] - center
    radial = delta - np.outer(delta @ axis, axis)
    lengths = np.linalg.norm(radial, axis=1)
    return float(lengths.min()), float(lengths.max())


def assign_semantic_roles(
    surface_records: list[dict[str, Any]], points: np.ndarray, normals: np.ndarray
) -> None:
    planes = [value for value in surface_records if value["model"]["geometry"] == "plane"]
    cylinders = [value for value in surface_records if value["model"]["geometry"] == "cylinder"]
    if len(planes) != 10 or len(cylinders) != 2:
        raise ValueError(
            f"盲孔六角座應由十個平面與兩個圓柱面構成，實際為 {len(planes)} 與 {len(cylinders)}。"
        )

    # 圓柱：以徑向法向量符號判定內外（與其他範例相同規則）
    inner: list[dict[str, Any]] = []
    outer: list[dict[str, Any]] = []
    for surface in cylinders:
        indices = surface["indices"]
        sense = cylinder_surface_sense(surface["model"], points[indices], normals[indices])
        surface["surface_sense"] = sense
        (inner if sense < 0 else outer).append(surface)
    if len(inner) != 1 or len(outer) != 1:
        raise ValueError("盲孔六角座圓柱內外方向無法由徑向法向量符號唯一判定。")
    inner[0]["semantic_role"] = "blind_hole_side"
    outer[0]["semantic_role"] = "ring_outer_side"

    common_axis = canonical_direction(
        np.mean([np.asarray(value["model"]["axis"]) for value in cylinders], axis=0)
    )
    ring_center = np.asarray(outer[0]["model"]["center"])
    bore_radius = float(inner[0]["model"]["radius"])
    ring_radius = float(outer[0]["model"]["radius"])

    # 平面：先依代表法向量與共同軸線的關係分為水平面與側面
    horizontal: list[dict[str, Any]] = []
    vertical: list[dict[str, Any]] = []
    for surface in planes:
        alignment = abs(float(np.asarray(surface["model"]["normal"]) @ common_axis))
        (horizontal if alignment > ENDCAP_DOT_THRESHOLD else vertical).append(surface)
    if len(horizontal) != 4 or len(vertical) != HEX_SIDE_COUNT:
        raise ValueError(
            f"盲孔六角座應有四個水平面與六個六角側面，實際為 {len(horizontal)} 與 {len(vertical)}。"
        )

    # 六角側面：法向量與共同軸線近似垂直，依方位角排序後編號
    def azimuth(surface: dict[str, Any]) -> float:
        normal = np.asarray(surface["model"]["normal"])
        radial = normal - common_axis * float(normal @ common_axis)
        first, second = np.eye(3)[[0, 1]] if abs(common_axis[2]) > 0.9 else np.eye(3)[[1, 2]]
        return float(math.atan2(float(radial @ second), float(radial @ first)))

    for index, surface in enumerate(sorted(vertical, key=azimuth), start=1):
        surface["semantic_role"] = f"hex_side_{index}"

    # 四個水平面：底面朝共同軸線負向；其餘三面依徑向支撐範圍區分
    axial_values = {
        id(surface): float(np.asarray(surface["model"]["center"]) @ common_axis)
        for surface in horizontal
    }
    downward = [
        surface
        for surface in horizontal
        if float(np.asarray(surface["model"]["normal"]) @ common_axis) < 0
    ]
    if len(downward) != 1:
        raise ValueError("盲孔六角座應恰有一個朝軸線負向的六角底面。")
    downward[0]["semantic_role"] = "hex_bottom"

    upward = [surface for surface in horizontal if surface not in downward]
    if len(upward) != 3:
        raise ValueError("盲孔六角座應有三個朝軸線正向的水平面。")

    for surface in upward:
        minimum, maximum = radial_extent(surface, points, common_axis, ring_center)
        surface["_radial"] = (minimum, maximum)

    # 盲孔底面：支撐為覆蓋孔截面的圓盤（最大徑向不超過孔半徑加擬合容許值）
    floors = [
        surface
        for surface in upward
        if surface["_radial"][1] <= bore_radius + FIT_RESIDUAL_THRESHOLD_MM
    ]
    if len(floors) != 1:
        raise ValueError(
            "盲孔六角座應恰有一個位於孔內部、覆蓋孔截面的封底平面（盲孔底面）。"
        )
    floors[0]["semantic_role"] = "blind_hole_floor"

    annuli = [surface for surface in upward if surface not in floors]
    # 環台頂面：內徑起於孔半徑、外徑止於環台半徑；六角肩面：內徑起於環台半徑
    ring_tops = [
        surface
        for surface in annuli
        if surface["_radial"][1] <= ring_radius + FIT_RESIDUAL_THRESHOLD_MM
    ]
    if len(ring_tops) != 1:
        raise ValueError("盲孔六角座應恰有一個止於環台半徑的環台頂面。")
    ring_tops[0]["semantic_role"] = "ring_top"
    shelves = [surface for surface in annuli if surface not in ring_tops]
    if len(shelves) != 1:
        raise ValueError("盲孔六角座應恰有一個位於環台外側的六角肩面。")
    shelves[0]["semantic_role"] = "hex_shelf"

    for surface in upward:
        surface.pop("_radial", None)

    # 軸向次序查驗：盲孔底面低於六角肩面，六角肩面低於環台頂面
    order = [
        axial_values[id(downward[0])],
        axial_values[id(floors[0])],
        axial_values[id(shelves[0])],
        axial_values[id(ring_tops[0])],
    ]
    if not all(first < second for first, second in zip(order, order[1:])):
        raise ValueError(f"盲孔六角座水平面軸向次序不符預期：{order}")


def endcap_partners(
    cylinder_id: int, topology_rows: list[dict[str, Any]], by_cluster: dict[int, dict[str, Any]]
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
    return sorted(set(values))


def classify_hole_end_condition(
    cylinder: dict[str, Any],
    cap_ids: list[int],
    by_cluster: dict[int, dict[str, Any]],
    points: np.ndarray,
) -> tuple[str, str]:
    """依 3.8 節規則判定圓柱孔為貫穿孔或盲孔。

    封底端：EndCap 平面之支撐為覆蓋孔截面的圓盤（最小徑向約為零、
    最大徑向不超過孔半徑加擬合容許值）。恰有一端封底時為盲孔。
    """
    axis = np.asarray(cylinder["model"]["axis"])
    center = np.asarray(cylinder["model"]["center"])
    radius = float(cylinder["model"]["radius"])
    closed_ends = 0
    for cap_id in cap_ids:
        minimum, maximum = radial_extent(by_cluster[cap_id], points, axis, center)
        covers_section = (
            minimum <= FIT_RESIDUAL_THRESHOLD_MM
            and maximum <= radius + FIT_RESIDUAL_THRESHOLD_MM
        )
        if covers_section:
            closed_ends += 1
    if closed_ends == 0:
        return "ThroughHole", "both EndCap planes are annular openings reaching the outer boundary"
    if closed_ends == 1:
        return "BlindHole", "one EndCap plane is an interior disc covering the hole section"
    raise ValueError("圓柱孔兩端皆為封底圓盤，不屬於本研究處理範圍。")


def build_candidates(
    surface_records: list[dict[str, Any]], topology_rows: list[dict[str, Any]], points: np.ndarray
) -> list[dict[str, Any]]:
    by_role = {str(value["semantic_role"]): value for value in surface_records}
    by_cluster = {int(value["cluster_id"]): value for value in surface_records}

    def cluster(role: str) -> int:
        return int(by_role[role]["cluster_id"])

    ring_outer = by_role["ring_outer_side"]
    common_axis = canonical_direction(np.asarray(ring_outer["model"]["axis"]))
    ring_center = np.asarray(ring_outer["model"]["center"])

    def axial_coordinate(role: str) -> float:
        return float(np.median(points[by_role[role]["indices"]] @ common_axis))

    # 六角柱：由六個側面與底面、肩面界定。內切半徑取六側面到軸線的距離中位數，
    # 外接半徑由正六邊形幾何關係換算；高度由底面與肩面的軸向位置差得到。
    apothems: list[float] = []
    for index in range(1, HEX_SIDE_COUNT + 1):
        surface = by_role[f"hex_side_{index}"]
        normal = np.asarray(surface["model"]["normal"])
        offset = float((np.asarray(surface["model"]["center"]) - ring_center) @ normal)
        apothems.append(abs(offset))
    apothem = float(np.median(apothems))
    circumradius = apothem / math.cos(math.pi / 6.0)
    hex_height = abs(axial_coordinate("hex_shelf") - axial_coordinate("hex_bottom"))

    hex_clusters = sorted(
        [cluster(f"hex_side_{index}") for index in range(1, HEX_SIDE_COUNT + 1)]
        + [cluster("hex_bottom"), cluster("hex_shelf")]
    )
    rows: list[dict[str, Any]] = [
        {
            "CandidateID": "BH_U01",
            "PrimitiveType": "HexagonalPrism",
            "RelatedClusters": ";".join(str(value) for value in hex_clusters),
            "Length": 2.0 * circumradius,
            "Width": 2.0 * apothem,
            "Height": hex_height,
            "Radius": math.nan,
            "Depth": math.nan,
            "BooleanType": "Union",
            "InferenceRule": (
                "six vertical planes at equal azimuth spacing bounded by the bottom and shelf planes"
            ),
            "RuleStatus": "PASS",
        }
    ]

    cylinder_specs = {
        "ring_outer_side": ("BH_U02", "Union"),
        "blind_hole_side": ("BH_D01", "Difference"),
    }
    for role, (candidate_id, boolean_type) in cylinder_specs.items():
        surface = by_role[role]
        cylinder_id = int(surface["cluster_id"])
        cap_ids = endcap_partners(cylinder_id, topology_rows, by_cluster)
        if len(cap_ids) != 2:
            raise ValueError(f"{role} 未由兩個 EndCap 關係界定：{cap_ids}")
        axis = canonical_direction(np.asarray(surface["model"]["axis"]))
        cap_coordinates = sorted(
            float(np.median(points[by_cluster[cap_id]["indices"]] @ axis)) for cap_id in cap_ids
        )
        if boolean_type == "Difference":
            primitive_type, end_rule = classify_hole_end_condition(
                surface, cap_ids, by_cluster, points
            )
            inference_rule = (
                "cylinder side + two EndCap relations + radial normal sense; " + end_rule
            )
        else:
            primitive_type = "OuterRingBoss"
            inference_rule = "cylinder side + two EndCap relations + radial normal sense"
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
                "InferenceRule": inference_rule,
                "RuleStatus": "PASS",
            }
        )
    return sorted(rows, key=lambda value: value["CandidateID"])


def canonical_csg_tree(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """左結合二元展開：聯集候選依 CandidateID 兩兩聯集，再依序相減。

    對應第三章公式(3-7)：每個內部節點恰有兩個子節點。
    """
    unions = sorted(value["CandidateID"] for value in candidates if value["BooleanType"] == "Union")
    differences = sorted(
        value["CandidateID"] for value in candidates if value["BooleanType"] == "Difference"
    )
    if not unions:
        raise ValueError("缺少聯集候選，無法建立基體。")
    node: dict[str, Any] = {"candidate": unions[0]}
    for candidate_id in unions[1:]:
        node = {"op": "Union", "left": node, "right": {"candidate": candidate_id}}
    for candidate_id in differences:
        node = {"op": "Difference", "left": node, "right": {"candidate": candidate_id}}
    return node


def build_outputs(source: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source)
    required = ["X", "Y", "Z", "NX", "NY", "NZ", "ClusterID"]
    missing = [value for value in required if value not in frame.columns]
    if missing or len(frame) != 10000:
        raise ValueError(
            f"盲孔六角座輸入不符合第三章資料結構：missing={missing}, rows={len(frame)}"
        )

    points = frame[["X", "Y", "Z"]].to_numpy(float)
    normals = frame[["NX", "NY", "NZ"]].to_numpy(float)
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    original_clusters = frame["ClusterID"].to_numpy(int)

    surfaces, new_clusters, initial_audit = infer_surfaces(points, normals, original_clusters)
    assign_semantic_roles(surfaces, points, normals)
    if int(np.sum(new_clusters >= 0)) + int(np.sum(new_clusters < 0)) != len(frame):
        raise ValueError("盲孔六角座點數守恆失敗。")

    result_path = output_dir / "Result_Blind_Hole_Hex_Base_chapter3_verified.csv"
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
    face_path = output_dir / "FaceSummary_Blind_Hole_Hex_Base_chapter3_verified.csv"
    face_fields = [
        "ClusterID", "FeatureType", "SemanticRole", "PointCount", "FittedPatchCount",
        "CenterX", "CenterY", "CenterZ", "NX", "NY", "NZ", "AxisX", "AxisY", "AxisZ",
        "MinX", "MaxX", "MinY", "MaxY", "MinZ", "MaxZ", "Radius", "AxisMin", "AxisMax",
        "SurfaceSense", "FitResidualMax", "FitResidualMedian", "NormalConsistencyMin",
        "ValidationStatus",
    ]
    write_csv(face_path, face_rows, face_fields)

    topology_rows = build_topology(surfaces, points)
    topology_path = output_dir / "TopologyEdges_Blind_Hole_Hex_Base_chapter3_verified.csv"
    topology_fields = [
        "FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "DirectionDot",
        "DistanceThreshold", "DirectionThreshold", "RuleStatus", "InferenceRule",
    ]
    write_csv(topology_path, topology_rows, topology_fields)

    candidate_rows = build_candidates(surfaces, topology_rows, points)
    candidate_path = output_dir / "PrimitiveCandidates_Blind_Hole_Hex_Base_chapter3_verified.csv"
    candidate_fields = [
        "CandidateID", "PrimitiveType", "RelatedClusters", "Length", "Width", "Height",
        "Radius", "Depth", "BooleanType", "InferenceRule", "RuleStatus",
    ]
    write_csv(candidate_path, candidate_rows, candidate_fields)

    csg_path = output_dir / "CSGTree_Blind_Hole_Hex_Base_chapter3_verified.json"
    write_json(
        csg_path,
        {
            "case": "Blind-Hole Hex Base",
            "source": candidate_path.name,
            "canonicalization": (
                "binary tree; Union candidates left-associated by CandidateID, "
                "then Difference subtractors applied in CandidateID order"
            ),
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
    trace_path = output_dir / "CorrectionTrace_Blind_Hole_Hex_Base_chapter3.csv"
    write_csv(
        trace_path,
        trace_rows,
        ["OriginalClusterID", "VerifiedClusterID", "PointCount", "Action", "Reason"],
    )

    outputs = [result_path, face_path, topology_path, candidate_path, csg_path, trace_path]
    manifest_path = output_dir / "MethodInferenceManifest_Blind_Hole_Hex_Base_chapter3.json"
    write_json(
        manifest_path,
        {
            "schema_version": "3.0",
            "case": "Blind-Hole Hex Base",
            "method_basis": (
                "Chapter 3 formulas (3-3) through (3-7), with the 3.8 through-hole/blind-hole "
                "end-condition rule"
            ),
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
                "seed_acceptance": (
                    "an original cluster must pass exactly one accepted plane/cylinder fit; "
                    "plane is tested before cylinder"
                ),
                "reassignment": (
                    "best finite-support surface satisfying residual <= 1.5 mm and normal "
                    "agreement >= 0.93"
                ),
                "semantics": (
                    "cylinder radial-normal sense for inner/outer; horizontal planes separated by "
                    "radial support extent relative to the inferred bore and ring radii; six "
                    "vertical planes ordered by normal azimuth"
                ),
                "hole_end_condition": (
                    "blind when exactly one EndCap plane is an interior disc covering the hole "
                    "section; through when both EndCap planes are annular openings"
                ),
                "topology": "finite sampled support distance plus the Chapter 3 direction predicates",
                "candidates": (
                    "hexagonal prism from six vertical planes bounded by bottom and shelf; "
                    "each cylinder from one side plus exactly two EndCap relations"
                ),
                "csg": (
                    "binary tree; Union candidates left-associated by CandidateID, then ordered "
                    "Difference subtractors"
                ),
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
            "programs": {
                "inference": {
                    "filename": Path(__file__).name,
                    "sha256": sha256(Path(__file__)),
                },
                "geometry_helper": {
                    "filename": "infer_stepped_cylinder_chapter3_method.py",
                    "sha256": sha256(
                        Path(__file__).with_name("infer_stepped_cylinder_chapter3_method.py")
                    ),
                    "scope": "method-only geometry functions; no truth input",
                },
            },
            "outputs": {path.name: sha256(path) for path in outputs},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Infer Blind-Hole Hex Base only from the original Result CSV and the public "
            "Chapter 3 rules."
        )
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    build_outputs(arguments.result.resolve(), arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
