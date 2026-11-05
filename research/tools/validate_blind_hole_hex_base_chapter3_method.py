"""盲孔六角座（Blind-Hole Hex Base）五層驗收。

驗收邏輯、門檻與判定條件全部沿用 validate_model_a_chapter3_method 之 validate()，
以確保四個實作範例採用同一套驗收程序；本檔僅設定案例名稱與輸出檔名。
推論完成後才讀取獨立真值與 evaluated mesh，推論階段不得讀取兩者。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from validate_model_a_chapter3_method import validate, write_csv, write_json


CASE_NAME = "Blind-Hole Hex Base"
CASE_KEY = "Blind_Hole_Hex_Base"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate truth-free Blind-Hole Hex Base inference against independent mesh truth."
        )
    )
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
    summary["case"] = CASE_NAME
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        arguments.output_dir / f"ValidationAgainstIndependentTruth_{CASE_KEY}.json", summary
    )
    write_csv(
        arguments.output_dir / f"SurfaceMapping_{CASE_KEY}_chapter3.csv",
        [
            "ClusterID", "TruthSurfaceID", "Geometry", "SemanticRole", "PointCount",
            "DirectionAgreement", "PositionOrRadiusErrorMM", "ParameterToleranceMM",
            "ValidationStatus",
        ],
        surface_rows,
    )
    write_csv(
        arguments.output_dir / f"CandidateMapping_{CASE_KEY}_chapter3.csv",
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
