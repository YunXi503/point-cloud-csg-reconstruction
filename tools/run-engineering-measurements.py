"""Measure preserved case stages and characterize unchanged geometry functions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from geometry_fixtures import SURFACE_FIXTURES, CIRCLE_FIXTURES
from inference_sources import check_inference_programs
from process_metrics import measure_process

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if os.name != "nt" or sys.version_info[:3] != (3, 14, 2):
        parser.error("Use the recorded Windows / Python 3.14.2 environment.")
    if out.exists() or not out.is_relative_to(ROOT / "runs"):
        parser.error("Choose a new directory below this repository's runs/.")
    cases = read(ROOT / "examples/cases.json")
    mappings = read(ROOT / "examples/segmentation.json")
    copied = read(ROOT / "provenance/copied-sources.json")
    def source_guard():
        for source in copied:
            if sha(ROOT / source["path"]) != source["sha256"]:
                raise RuntimeError("Protected source drift: " + source["path"])
        if not all(p["matches"] for p in check_inference_programs(ROOT, cases)):
            raise RuntimeError("Inference preflight did not pass.")
    source_guard()
    out.mkdir(parents=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    tools = ["run-engineering-measurements.py", "measurement_worker.py", "process_metrics.py", "geometry_fixtures.py"]
    report = {"schema_version": "1", "date": "2026-11-05", "timezone": "Asia/Taipei", "status": "running",
              "scope": "Engineering measurements / analytic fixtures, not thesis experiments or accuracy generalization",
              "research_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "protocol": {"path": "docs/measurement-protocol.md", "sha256": sha(ROOT / "docs/measurement-protocol.md")},
              "tool_sources": [{"path": "tools/"+name, "sha256": sha(ROOT/"tools"/name)} for name in tools],
              "case_binding_files": [{"path": p,"sha256": sha(ROOT/p)} for p in ["examples/cases.json","examples/segmentation.json"]],
              "protected_sources": len(copied), "sources_verified_before": True,
              "runtime": {"python": sys.version, "platform": platform.platform(), "threads_environment": {n: os.environ.get(n) for n in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]}},
              "stage_runs": [], "scale_counts": [], "scale_runs": [], "surface_diagnostics": [], "circle_diagnostics": []}
    report_path = out / "measurement-results.json"
    def save():
        write(report_path, report)
    def rel(p):
        return p.relative_to(ROOT).as_posix()
    def measured(command, folder, timeout=120):
        folder.mkdir(parents=True)
        result = measure_process(command, folder, folder/"stdout.log", folder/"stderr.log", timeout, env)
        result.update(stdout=rel(folder/"stdout.log"), stderr=rel(folder/"stderr.log"))
        return result
    def worker(operation, folder, extra=None):
        output = folder / "observation.json"
        metrics = measured([sys.executable, str(ROOT/"tools/measurement_worker.py"), operation, "--output", str(output), *(extra or [])], folder, 30)
        if metrics["returncode"] or metrics["timed_out"] or metrics["memory_error"] or not output.exists():
            save()
            raise RuntimeError("Measurement worker failed; inspect " + rel(folder))
        value = read(output)
        if value["pid"] != metrics["pid"]:
            raise RuntimeError("Wrong process measured: Python PID differs from Popen PID.")
        return {"metrics": metrics, "observation": value}
    identity = worker("identity", out/"identity")
    actual = identity["observation"]
    if Path(actual["prefix"]).resolve() != Path(sys.prefix).resolve() or not all(v["expected"]==v["actual"] for v in actual["packages"].values()):
        raise RuntimeError("Direct runtime did not preserve the locked virtual environment.")
    report["runtime"].update(packages=actual["packages"], prefix_matches=True, pid_matches=True, identity_metrics=identity["metrics"])
    probe_code = "import json,os,sys\nb=bytearray(64*1024*1024)\nfor i in range(0,len(b),4096): b[i]=1\nprint(json.dumps({'pid':os.getpid(),'prefix':sys.prefix,'allocated_bytes':len(b)}))"
    probe = measured([sys.executable, "-c", probe_code], out/"allocation-probe", 30)
    probe_data = json.loads((out/"allocation-probe/stdout.log").read_text(encoding="utf-8"))
    probe.update(pid_matches=probe_data["pid"]==probe["pid"], prefix_matches=Path(probe_data["prefix"])==Path(sys.prefix), allocated_bytes=probe_data["allocated_bytes"])
    if not probe["pid_matches"] or not probe["prefix_matches"] or probe["memory_error"] or probe["peak_working_set_bytes"] < 64*1024*1024:
        raise RuntimeError("Memory collector did not pass the allocation / identity probe.")
    report["memory_collector_probe"] = probe
    hardware_command = "$measuredOs=Get-CimInstance Win32_OperatingSystem; $measuredCpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); $measuredMachine=Get-CimInstance Win32_ComputerSystem; [pscustomobject]@{processors=$measuredCpu;physical_memory_bytes=$measuredMachine.TotalPhysicalMemory;os=$measuredOs.Caption;version=$measuredOs.Version;build=$measuredOs.BuildNumber} | ConvertTo-Json -Depth 5"
    report["hardware"] = json.loads(subprocess.check_output(["pwsh", "-NoProfile", "-Command", hardware_command], text=True, encoding="utf-8"))
    save()
    print("Identity, package and native-memory probes passed; preparing unchanged C# builds", flush=True)
    prepared = out / "prepared"
    with (out/"preparation.log").open("w",encoding="utf-8") as log:
        subprocess.run([sys.executable, str(ROOT/"tools/run-from-point-cloud.py"), "--case", "all", "--output-dir", str(prepared)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    baseline = read(prepared/"pipeline-results.json")
    if baseline["status"] != "pass" or not all(c["initial_bytes_match"] for c in baseline["cases"]):
        raise RuntimeError("Preparation did not reproduce the original outputs exactly.")
    report["preparation"] = {"included_in_stage_timing": False, "status": baseline["status"], "pipeline_report_sha256": sha(prepared/"pipeline-results.json")}
    report["compiled_artifacts"] = []
    for p in sorted(prepared.rglob("*.dll")) + sorted(prepared.rglob("ClassifierRunner.exe")):
        if "/bin/" in p.as_posix() and p.name in {"CoreClassifierRunner.dll", "CoreResearchClassifier.dll", "ResearchClassifier.dll", "ClassifierRunner.exe"}:
            report["compiled_artifacts"].append({"path": rel(p), "sha256": sha(p)})
    for repeat in range(1, 4):
        for phase in ["csharp-classification", "python-inference"]:
            for case, mapping in zip(cases, mappings):
                if case["id"] != mapping["id"]:
                    raise RuntimeError("Case/source ordering differs; do not infer a mapping.")
                folder = out / phase / case["id"] / str(repeat)
                if phase == "csharp-classification":
                    if mapping["runtime"] == "net8.0":
                        command = ["dotnet", str(prepared/"core-runner/bin/CoreClassifierRunner.dll"), str(prepared/case["id"]/"classifier/bin/CoreResearchClassifier.dll")]
                    else:
                        command = [str(prepared/"runner/bin/ClassifierRunner.exe"), str(prepared/case["id"]/"classifier/bin/ResearchClassifier.dll")]
                    command += [str(ROOT/mapping["point_cloud"]), str(folder/"initial.csv")]
                else:
                    command = [sys.executable, str(ROOT/case["entrypoint"]), "--result", str(ROOT/case["input"]), "--output-dir", str(folder/"inference")]
                metrics = measured(command, folder)
                expected = [{"filename": "initial.csv", "recorded_sha256": case["recorded_input_sha256"]}] if phase == "csharp-classification" else case["output_checks"]
                checks = []
                for original in expected:
                    target = folder/original["filename"] if phase == "csharp-classification" else folder/"inference"/original["filename"]
                    observed = sha(target) if target.exists() else None
                    checks.append({"filename": original["filename"], "expected_sha256": original["recorded_sha256"], "actual_sha256": observed, "matches": observed==original["recorded_sha256"]})
                valid = metrics["returncode"]==0 and not metrics["timed_out"] and not metrics["memory_error"] and all(c["matches"] for c in checks)
                runtime_line = next((line for line in (folder/"stdout.log").read_text(encoding="utf-8").splitlines() if line.startswith("Runtime: ")), None)
                report["stage_runs"].append({"phase": phase, "case": case["id"], "repeat": repeat, "metrics": metrics, "outputs": checks, "valid_measurement": valid,
                                             "runtime_target": mapping["runtime"] if phase=="csharp-classification" else "Python 3.14.2", "observed_runtime_line": runtime_line})
                save()
                print(f"{phase} {case['id']} repetition {repeat}: {'verified' if valid else 'INVALID'}",flush=True)
                if not valid:
                    raise RuntimeError("Invalid measurement; preserve and diagnose the current record.")
    for n in [1000, 2500, 5000, 10000]:
        report["scale_counts"].append(worker("scale-count", out/"scale-count"/str(n), ["--count",str(n)]))
        for repeat in range(1,4):
            observation = worker("scale", out/"scale"/str(n)/str(repeat), ["--count",str(n)])
            observation["repeat"] = repeat
            report["scale_runs"].append(observation)
            save()
        print(f"region_growing N={n}: three fresh-process measurements saved",flush=True)
    for module in ["stepped", "lbracket"]:
        for name in SURFACE_FIXTURES:
            report["surface_diagnostics"].append(worker("surface", out/"surface"/module/name, ["--module",module,"--fixture",name]))
            save()
        for name in CIRCLE_FIXTURES:
            report["circle_diagnostics"].append(worker("circle", out/"circle"/module/name, ["--module",module,"--fixture",name]))
            save()
        print(module+": surface and convergence observations saved",flush=True)
    lbracket = next(c for c in cases if c["id"]=="l-bracket")
    contract = out / "full-size-contract"
    contract.mkdir()
    with (ROOT/lbracket["input"]).open(encoding="utf-8-sig",newline="") as stream:
        sample = list(csv.reader(stream))[:5001]
    with (contract/"input-5000.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        csv.writer(stream,lineterminator="\n").writerows(sample)
    result = measure_process([sys.executable,str(ROOT/lbracket["entrypoint"]),"--result",str(contract/"input-5000.csv"),"--output-dir",str(contract/"result")],contract,contract/"stdout.log",contract/"stderr.log",30,env)
    error = (contract/"stderr.log").read_text(encoding="utf-8")
    report["full_pipeline_size_contract"] = {"input_rows":5000,"input_sha256":sha(contract/"input-5000.csv"),"metrics":result,"expected_rejection_observed":result["returncode"]!=0 and "rows=5000" in error,"last_error_line":error.strip().splitlines()[-1] if error.strip() else None}
    source_guard()
    report.update(sources_verified_after=True,status="completed")
    save()
    print("Measurement collection completed; diagnostics require separate interpretation: "+rel(report_path),flush=True)


if __name__ == "__main__":
    main()
