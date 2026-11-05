"""Run auditable one-factor threshold checks without mutating production code.

Each run receives a private copy of the four inference scripts with exactly one
literal threshold changed.  This prevents a parameter experiment from silently
altering the checked-in method implementation or its baseline outputs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
OUT = ROOT / "碩士論文" / "審查報告" / "敏感度分析_260731"
SCRIPTS = [
    "correct_stepped_cylinder_nls_v2.py",
    "infer_stepped_cylinder_chapter3_method.py",
    "infer_lbracket_chapter3_method.py",
    "infer_model_a_chapter3_method.py",
    "infer_blind_hole_hex_base_chapter3_method.py",
]
CASES = {
    "Stepped_Cylinder": ("infer_stepped_cylinder_chapter3_method.py", "零件/Result_Stepped Cylinder.csv"),
    "L_Bracket": ("infer_lbracket_chapter3_method.py", "零件/Result_L Bracket.csv"),
    "Model_A": ("infer_model_a_chapter3_method.py", "零件/Result_Model A.csv"),
    "Blind_Hole_Hex_Base": ("infer_blind_hole_hex_base_chapter3_method.py", "零件/Result_Blind-Hole Hex Base_fixed.csv"),
}
FACTORS = {
    "distance_mm": ("DISTANCE_THRESHOLD_MM = 2.0", [1.5, 2.0, 2.5]),
    "normal_dot": ("NORMAL_THRESHOLD = 0.93", [0.90, 0.93, 0.96]),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_variant(target: Path, factor: str, value: float) -> None:
    target.mkdir(parents=True, exist_ok=True)
    expected, _ = FACTORS[factor]
    replacement = (
        f"DISTANCE_THRESHOLD_MM = {value:.1f}"
        if factor == "distance_mm"
        else f"NORMAL_THRESHOLD = {value:.2f}"
    )
    for name in SCRIPTS:
        text = (TOOLS / name).read_text(encoding="utf-8")
        if factor == "distance_mm" and expected in text:
            text = text.replace(expected, replacement)
        elif "NORMAL_THRESHOLD = 0.93" in text:
            text = text.replace("NORMAL_THRESHOLD = 0.93", replacement)
        # Model A and Blind-Hole import NORMAL_THRESHOLD from the stepped helper;
        # the copied helper in this directory supplies the altered value.
        (target / name).write_text(text, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    baseline_hashes: dict[str, dict[str, str]] = {}
    for case, (script, source_rel) in CASES.items():
        for factor, (_, values) in FACTORS.items():
            for value in values:
                run_id = f"{case}__{factor}_{value:.2f}"
                variant_dir = OUT / "variants" / run_id
                output_dir = OUT / "runs" / run_id
                make_variant(variant_dir, factor, value)
                output_dir.mkdir(parents=True, exist_ok=True)
                command = [
                    sys.executable, str(variant_dir / script),
                    "--result", str(ROOT / source_rel),
                    "--output-dir", str(output_dir),
                ]
                completed = subprocess.run(
                    command,
                    cwd=variant_dir,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                )
                manifest = next(output_dir.glob("MethodInferenceManifest_*.json"), None)
                record: dict = {
                    "case": case,
                    "factor": factor,
                    "value": value,
                    "fixed_parameters": {"distance_mm": 2.0, "normal_dot": 0.93},
                    "variant_sha256": {name: sha256(variant_dir / name) for name in SCRIPTS},
                    "source": source_rel,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.strip(),
                    "stdout": completed.stdout.strip(),
                    "output_dir": str(output_dir.relative_to(ROOT)).replace("\\", "/"),
                }
                if manifest and completed.returncode == 0:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    record["counts"] = data["counts"]
                    record["outputs"] = data["outputs"]
                    key = "|".join([case, factor])
                    if value == 2.0 if factor == "distance_mm" else value == 0.93:
                        baseline_hashes[key] = data["outputs"]
                        record["matches_baseline"] = True
                    else:
                        record["matches_baseline"] = data["outputs"] == baseline_hashes.get(key)
                else:
                    record["matches_baseline"] = None
                results.append(record)

    report = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "design": {
            "type": "one-factor-at-a-time",
            "distance_mm": [1.5, 2.0, 2.5],
            "normal_dot": [0.90, 0.93, 0.96],
            "baseline": {"distance_mm": 2.0, "normal_dot": 0.93},
            "criterion": "A run is only labelled output-stable when all recorded inference-output hashes equal its same-factor baseline. This is not a correctness claim.",
            "prediction": "Changing one threshold may alter segmentation, accepted faces, topology, candidate units, or the symbolic CSG output; unchanged output indicates local stability under the tested controlled inputs.",
            "falsification": "Any failed run or any hash difference from the same-factor baseline falsifies output stability at that setting.",
        },
        "runs": results,
    }
    (OUT / "sensitivity_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 四案例核心門檻單因子敏感度分析（2026-07-31）",
        "",
        "## 設計與判準",
        "",
        "本分析固定一項門檻、一次只改變另一項。距離門檻測試 1.5、2.0、2.5 mm；法向量內積門檻測試 0.90、0.93、0.96。每個結果僅與相同因素的基準輸出比較；輸出雜湊完全相同才記為「輸出穩定」，不將穩定誤寫為正確性或泛化能力。",
        "",
        "## 事前預期、證偽條件與輸入版本",
        "",
        "- **預期**：只改變一項門檻時，可能改變分割、接受面、拓樸關係、候選幾何單元或 CSG 符號輸出；若輸出雜湊不變，僅表示該受控輸入在該設定附近具有局部輸出穩定性。",
        "- **證偽條件**：任一執行失敗，或任一輸出檔雜湊與同一因素的基準設定不一致，即否定該設定的「輸出穩定」；不以面數恰好相同取代雜湊比對。",
        "- **固定輸入與基準**：距離測試固定法向量內積門檻 0.93；法向量測試固定距離門檻 2.0 mm。四個輸入分別為 `Result_Stepped Cylinder.csv`、`Result_L Bracket.csv`、`Result_Model A.csv` 與 `Result_Blind-Hole Hex Base_fixed.csv`。每次執行使用私有程式副本；各副本 SHA-256、原始輸入路徑、標準輸出與錯誤輸出均記錄於 `sensitivity_results.json`。",
        "",
        "## 結果摘要",
        "",
        "| 實作範例 | 因素 | 設定值 | 執行狀態 | 與基準輸出一致 | 接受面數 | 殘留點 | 拓樸關係 | 候選幾何單元 |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in results:
        counts = row.get("counts", {})
        status = "完成" if row["returncode"] == 0 else "失敗"
        match = "是" if row["matches_baseline"] is True else "否" if row["matches_baseline"] is False else "不適用"
        lines.append(
            f"| {row['case']} | {row['factor']} | {row['value']:.2f} | {status} | {match} | "
            f"{counts.get('accepted_faces', '—')} | {counts.get('residual_points', '—')} | "
            f"{counts.get('topology_edges', '—')} | {counts.get('primitive_candidates', '—')} |"
        )
    lines.extend([
        "",
        "## 未完成執行的如實紀錄",
        "",
        "L 型板在距離門檻 1.5 mm 時，第三章推論程式產生 28 個面級記錄，未通過程式內「L 型板應有 12 個面」的一致性檢查而停止。此項結果保留為失敗，不以放寬檢查、併入額外規則或改動其他參數使其通過。",
        "",
        "## 證據界線",
        "",
        "本分析只使用點級分割結果與公開方法規則；變體程式、副本雜湊、原始輸入與各次輸出均保留於同資料夾。它不讀取真值、網格面或候選模板，亦不取代真實掃描雜訊條件下的魯棒性驗證。",
    ])
    (OUT / "敏感度分析報告_260731.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
