"""Run unchanged inference entrypoints and compare their recorded core outputs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["all", "stepped-cylinder", "l-bracket", "model-a", "blind-hole-hex-base"], default="all")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        parser.error("Output directory already exists; choose a new run directory.")
    output.mkdir(parents=True)
    cases = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
    selected = [case for case in cases if args.case in ("all", case["id"])]
    packages = {}
    for name in ["numpy", "pandas", "scipy", "matplotlib", "Pillow"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {"schema_version": "1", "scope": "unchanged inference output reproduction; no new accuracy claim",
              "python_version": sys.version, "packages": packages, "cases": [], "status": "running"}
    report_path = output / "reproduction-results.json"

    def save() -> None:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    shared = next(case for case in cases if case["id"] == "stepped-cylinder")
    report["shared_geometry_program"] = {
        "expected_sha256": shared["recorded_program_sha256"],
        "actual_sha256": sha256(ROOT / shared["entrypoint"]),
    }
    if report["shared_geometry_program"]["expected_sha256"] != report["shared_geometry_program"]["actual_sha256"]:
        report["status"] = "blocked-shared-program-version-mismatch"
        save()
        return 2
    save()
    for case in selected:
        item = {"id": case["id"], "recorded_input_sha256": case["recorded_input_sha256"],
                "actual_input_sha256": sha256(ROOT / case["input"]),
                "recorded_program_sha256": case["recorded_program_sha256"],
                "actual_program_sha256": sha256(ROOT / case["entrypoint"])}
        report["cases"].append(item)
        if item["actual_input_sha256"] != item["recorded_input_sha256"]:
            item["status"] = "blocked-input-version-mismatch"
            print(case["id"] + ": blocked; input does not match historical record", flush=True)
            save()
            continue
        if item["actual_program_sha256"] != item["recorded_program_sha256"]:
            item["status"] = "blocked-program-version-mismatch"
            report["status"] = "failed"
            save()
            return 1
        case_dir = output / case["id"]
        command = [sys.executable, str(ROOT / case["entrypoint"]), "--result", str(ROOT / case["input"]), "--output-dir", str(case_dir)]
        print(case["id"] + ": running unchanged inference", flush=True)
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        with (output / (case["id"] + ".stdout.log")).open("w", encoding="utf-8") as stdout, (output / (case["id"] + ".stderr.log")).open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr, check=False)
        item["exit_code"] = completed.returncode
        if completed.returncode:
            item["status"] = "execution-failed"
            report["status"] = "failed"
            print(case["id"] + ": execution failed; stopping for diagnosis", flush=True)
            save()
            return 1
        checks = []
        for recorded in case["output_checks"]:
            target = case_dir / recorded["filename"]
            actual = sha256(target) if target.exists() else None
            checks.append({"filename": recorded["filename"], "expected_sha256": recorded["recorded_sha256"],
                           "actual_sha256": actual, "matches": actual == recorded["recorded_sha256"]})
        item["outputs"] = checks
        item["status"] = "pass" if checks and all(check["matches"] for check in checks) else "output-hash-mismatch"
        print(case["id"] + ": " + item["status"] + " " + str(sum(check["matches"] for check in checks)) + "/" + str(len(checks)), flush=True)
        save()
    report["status"] = "pass-with-blocked-input" if any(case["status"].startswith("blocked") for case in report["cases"]) else "pass"
    if any(case["status"] == "output-hash-mismatch" for case in report["cases"]):
        report["status"] = "failed"
    save()
    if report["status"] == "failed":
        return 1
    return 2 if report["status"] == "pass-with-blocked-input" else 0


if __name__ == "__main__":
    raise SystemExit(main())
