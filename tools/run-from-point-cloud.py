"""Check the recorded C# source -> Python inference path on bundled point-normal examples."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from inference_sources import check_inference_programs

ROOT = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def token_equal(left: str, right: str) -> bool:
    if left == right:
        return True
    if not (NUMBER.fullmatch(left) and NUMBER.fullmatch(right)):
        return False
    x, y = float(left), float(right)
    return math.isfinite(x) and math.isfinite(y) and struct.pack("!d", x) == struct.pack("!d", y)


def compare_csv(actual: Path, expected: Path) -> dict:
    with actual.open(encoding="utf-8-sig", newline="") as stream:
        left = list(csv.reader(stream))
    with expected.open(encoding="utf-8-sig", newline="") as stream:
        right = list(csv.reader(stream))
    if len(left) != len(right) or not left or left[0] != right[0]:
        return {"parsed_exact": False, "actual_rows": max(0, len(left) - 1), "expected_rows": max(0, len(right) - 1), "reason": "schema or row count differs"}
    differences = []
    count = 0
    for index, (a, b) in enumerate(zip(left[1:], right[1:]), 1):
        if len(a) != len(b):
            return {"parsed_exact": False, "reason": "row width differs", "row": index}
        for column, x, y in zip(right[0], a, b):
            if not token_equal(x, y):
                count += 1
                if len(differences) < 5:
                    differences.append({"row": index, "column": column, "actual": x, "expected": y})
    return {"parsed_exact": count == 0, "different_cells": count, "examples": differences}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["all", "stepped-cylinder", "l-bracket", "model-a", "blind-hole-hex-base"], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--msbuild", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This optional C# path requires Windows and .NET Framework 4.8.")
    output = args.output_dir.resolve()
    if output.exists():
        parser.error("Output directory already exists; choose a new directory.")
    mappings = json.loads((ROOT / "examples/segmentation.json").read_text(encoding="utf-8"))
    selected = [mapping for mapping in mappings if args.case in ("all", mapping["id"])]
    cases = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    report = {"scope": "Provided point-normal CSV to existing C# classifier and Python inference; no STL sampling", "cases": []}

    def save() -> None:
        (output / "pipeline-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report["inference_programs"] = check_inference_programs(
        ROOT, [case for case in cases if case["id"] in {mapping["id"] for mapping in selected}])
    if not all(program["matches"] for program in report["inference_programs"]):
        report["status"] = "blocked-inference-source-version-mismatch"
        save()
        return 2
    save()
    framework_required = any(mapping.get("runtime", "net48") == "net48" for mapping in selected)
    msbuild = args.msbuild
    if msbuild is None and framework_required:
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
        found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-find", "MSBuild/**/Bin/MSBuild.exe"], capture_output=True, text=True, check=True).stdout.splitlines()
        if not found:
            parser.error("Specify --msbuild with a .NET Framework 4.8 MSBuild toolchain.")
        msbuild = Path(found[0])
    def build(project: str, folder: Path, extra: list[str] | None = None) -> None:
        folder.mkdir(parents=True)
        command = [str(msbuild), str(ROOT / project), "/t:Build", "/nologo", "/verbosity:minimal", "/p:Configuration=Release",
                   "/p:OutputPath=" + str(folder / "bin") + os.sep,
                   "/p:IntermediateOutputPath=" + str(folder / "obj") + os.sep,
                   "/p:BaseIntermediateOutputPath=" + str(folder / "obj") + os.sep] + (extra or [])
        with (folder / "build.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)

    def build_core(project: str, folder: Path, extra: list[str] | None = None) -> None:
        folder.mkdir(parents=True)
        command = ["dotnet", "build", str(ROOT / project), "--configuration", "Release", "--output", str(folder / "bin"),
                   "/p:BaseIntermediateOutputPath=" + str(folder / "obj") + os.sep] + (extra or [])
        with (folder / "build.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)

    if framework_required:
        build("src/adapter/ClassifierRunner.csproj", output / "runner")
    if any(mapping.get("runtime") == "net8.0" for mapping in selected):
        build_core("src/adapter/CoreRunner.csproj", output / "core-runner")
    for mapping in mappings:
        if args.case not in ("all", mapping["id"]):
            continue
        case = next(item for item in cases if item["id"] == mapping["id"])
        result = {"id": mapping["id"], "source_sha256": sha256(ROOT / mapping["source"]), "point_cloud_sha256": sha256(ROOT / mapping["point_cloud"])}
        report["cases"].append(result)
        if result["source_sha256"] != mapping["source_sha256"] or result["point_cloud_sha256"] != mapping["point_cloud_sha256"]:
            result["status"] = "blocked-source-version-mismatch"
            save()
            continue
        folder = output / mapping["id"]
        runtime = mapping.get("runtime", "net48")
        result["runtime_target"] = runtime
        if runtime == "net8.0":
            build_core("src/adapter/CoreClassifier.csproj", folder / "classifier", ["/p:LegacyAlgorithm=" + str(ROOT / mapping["source"])])
            runner = ["dotnet", str(output / "core-runner/bin/CoreClassifierRunner.dll"), str(folder / "classifier/bin/CoreResearchClassifier.dll")]
        else:
            build("src/adapter/ClassifierLibrary.csproj", folder / "classifier", ["/p:LegacyAlgorithm=" + str(ROOT / mapping["source"])])
            runner = [str(output / "runner/bin/ClassifierRunner.exe"), str(folder / "classifier/bin/ResearchClassifier.dll")]
        raw_result = folder / "initial.csv"
        with (folder / "classifier.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(runner + [str(ROOT / mapping["point_cloud"]), str(raw_result)], cwd=folder, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        result["classifier_exit_code"] = process.returncode
        if process.returncode or not raw_result.exists():
            result["status"] = "classification-execution-failed"
            save()
            continue
        result["initial_output_sha256"] = sha256(raw_result)
        result["expected_initial_sha256"] = case["recorded_input_sha256"]
        result["initial_bytes_match"] = sha256(raw_result) == case["recorded_input_sha256"]
        result["initial_comparison"] = compare_csv(raw_result, ROOT / case["input"])
        if not result["initial_comparison"]["parsed_exact"]:
            result["status"] = "initial-data-mismatch"
            print(mapping["id"] + ": initial data differs; no algorithm changes attempted", flush=True)
            save()
            continue
        with (folder / "inference.log").open("w", encoding="utf-8") as log:
            inference = subprocess.run([sys.executable, str(ROOT / case["entrypoint"]), "--result", str(raw_result), "--output-dir", str(folder / "inference")], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        result["inference_exit_code"] = inference.returncode
        if inference.returncode:
            result["status"] = "inference-execution-failed"
        else:
            checks = []
            for expected in case["output_checks"]:
                p = folder / "inference" / expected["filename"]
                checks.append({"filename": expected["filename"], "sha256": sha256(p) if p.exists() else None, "matches": p.exists() and sha256(p) == expected["recorded_sha256"]})
            result["outputs"] = checks
            result["status"] = "pass" if all(check["matches"] for check in checks) else "output-hash-mismatch"
        print(mapping["id"] + ": " + result["status"], flush=True)
        save()
    report["status"] = "pass" if report["cases"] and all(item["status"] == "pass" for item in report["cases"]) else "partial-or-failed"
    save()
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
