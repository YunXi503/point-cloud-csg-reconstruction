"""Isolated read-only calls to recorded methods for engineering measurements."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time
import warnings

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from geometry_fixtures import surface_fixture, circle_fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tools"))


def array_hash(value, dtype):
    return hashlib.sha256(np.asarray(value, dtype=dtype).tobytes(order="C")).hexdigest()


def safe(value):
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else str(float(value))
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def model_summary(model):
    if model is None:
        return {"selection": "rejected-with-none"}
    geometry = model["geometry"]
    active = np.r_[model["center"], model["normal"] if geometry == "plane" else model["axis"]]
    if geometry == "cylinder":
        active = np.r_[active, model["radius"], model["axis_min"], model["axis_max"]]
    return safe({"geometry": geometry, "center": model["center"], "direction": model["normal"] if geometry == "plane" else model["axis"],
                 "radius": model["radius"] if geometry == "cylinder" else None,
                 "residual_max": np.max(model["residual"]), "alignment_min": np.min(model["alignment"]),
                 "iterations": model["iterations"], "active_geometry_finite": bool(np.isfinite(active).all())})


def observe(call):
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            value = call()
            result = {"outcome": "returned", "result": value}
        except Exception as error:
            result = {"outcome": "exception", "exception_type": type(error).__name__, "message": str(error)}
        result["warnings"] = [{"category": w.category.__name__, "message": str(w.message)} for w in captured]
    return safe(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["identity", "scale-count", "scale", "surface", "circle"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int)
    parser.add_argument("--module", choices=["stepped", "lbracket"])
    parser.add_argument("--fixture")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve previous result; choose a new output file.")
    data = {"pid": os.getpid(), "operation": args.operation}
    if args.operation == "identity":
        packages = {}
        for line in (ROOT / "requirements.lock.txt").read_text().splitlines():
            if "==" in line and not line.startswith("#"):
                name, expected = line.split("==")
                packages[name] = {"expected": expected, "actual": importlib.metadata.version(name)}
        data.update(prefix=sys.prefix, python=sys.version, packages=packages)
    elif args.operation.startswith("scale"):
        method = importlib.import_module("infer_lbracket_chapter3_method")
        cases = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
        case = next(c for c in cases if c["id"] == "l-bracket")
        frame = pd.read_csv(ROOT / case["input"])
        if args.count not in [1000, 2500, 5000, 10000]:
            parser.error("Only predeclared existing-data subset sizes are supported.")
        indices = np.sort(np.random.default_rng(42).permutation(len(frame))[:args.count])
        points = frame[["X", "Y", "Z"]].to_numpy(float)[indices]
        normals = frame[["NX", "NY", "NZ"]].to_numpy(float)[indices]
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
        data.update(n=len(indices), seed=42, source=case["input"], source_sha256=hashlib.sha256((ROOT/case["input"]).read_bytes()).hexdigest(),
                    indices_sha256=array_hash(indices, "<i8"), points_sha256=array_hash(points, "<f8"), normals_sha256=array_hash(normals, "<f8"),
                    parameters={"distance_mm": method.DISTANCE_THRESHOLD_MM, "normal_dot": method.NORMAL_THRESHOLD})
        if args.operation == "scale-count":
            data["distance_pairs"] = len(cKDTree(points).query_pairs(method.DISTANCE_THRESHOLD_MM))
        else:
            started = time.perf_counter_ns()
            labels = method.region_growing(points, normals)
            data["function_seconds"] = (time.perf_counter_ns() - started) / 1e9
            data.update(components=len(set(labels.tolist())), labels_sha256=array_hash(labels, "<i8"))
    else:
        name = "infer_stepped_cylinder_chapter3_method" if args.module == "stepped" else "correct_stepped_cylinder_nls_v2"
        method = importlib.import_module(name)
        data.update(module=name, fixture=args.fixture, nonfinite_encoding="Nonfinite observed floats are strings, never fabricated numeric values")
        if args.operation == "surface":
            points, normals = surface_fixture(args.fixture)
            rank = int(np.linalg.matrix_rank(points - points.mean(axis=0))) if len(points) and np.isfinite(points).all() else None
            data.update(points=len(points), position_rank=rank, points_sha256=array_hash(points, "<f8"), normals_sha256=array_hash(normals, "<f8"))
            data["fit_plane"] = observe(lambda: model_summary(method.fit_plane(points, normals)))
            data["fit_cylinder"] = observe(lambda: model_summary(method.fit_cylinder(points, normals)))
            if args.module == "stepped":
                data["surface_selector"] = observe(lambda: model_summary(method.fit_single_surface(points, normals)))
            else:
                selector = importlib.import_module("infer_lbracket_chapter3_method")
                data["surface_selector"] = observe(lambda: model_summary(selector.fit_component(np.arange(len(points)), points, normals)))
        else:
            values, truth = circle_fixture(args.fixture)
            trace_result = {}
            def trace(frame, event, arg):
                if frame.f_code is method.nonlinear_circle.__code__:
                    if event == "return" and "step" in frame.f_locals:
                        trace_result["last_step_norm"] = float(np.linalg.norm(frame.f_locals["step"]))
                    return trace
                return None
            def run_circle():
                old = sys.gettrace()
                sys.settrace(trace)
                try:
                    x, y, radius, residual, iterations = method.nonlinear_circle(values)
                finally:
                    sys.settrace(old)
                step = trace_result.get("last_step_norm")
                return {"center": [x, y], "radius": radius, "residual_max": float(np.abs(residual).max()), "iterations": iterations,
                        "last_step_norm": step, "recorded_step_threshold_met": step <= 1e-13 if step is not None else None,
                        "reached_iteration_limit": iterations == 100,
                        "radius_error": abs(radius-truth["radius"]) if truth else None,
                        "center_error": float(np.linalg.norm(np.asarray([x,y])-truth["center"])) if truth else None}
            data.update(values_sha256=array_hash(values, "<f8"), analytic_truth=truth, solver=observe(run_circle))
    args.output.write_text(json.dumps(safe(data), ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
