"""Optional outer contract for two pinned circle solvers; never certifies accuracy."""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import types
import warnings

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "stepped": ("research/tools/infer_stepped_cylinder_chapter3_method.py", "1bd6365fec4d056b991293c2f2a7d839e194349bc596c1705b482a1a36f2645c"),
    "lbracket": ("research/tools/correct_stepped_cylinder_nls_v2.py", "a9ad922f812d21c974bdbf6e20c2d0d79352a15992551f221b292d2fe22dda6d"),
}


class SourceContractError(RuntimeError):
    pass


def new_circle_report(implementation="stepped"):
    """Common schema for every written CLI/API report, including parse errors."""
    return {"schema_version":"1","implementation":implementation,"status":"invalid_input","reason":None,
            "solver_called":False,"estimate":None,"raw_result":None,"input_csv_sha256":None,
            "convergence":{"status":"not_observed","step_threshold_met":None},
            "verification":{"status":"not_assessed","parameters_verified":False,
                            "reason":"No independent parameter reference or calibrated uncertainty bound was supplied."},
            "runtime":{"python":sys.version.split()[0],"numpy":np.__version__}}


def _safe(value):
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else str(float(value))
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _load_original(implementation):
    path, pinned = SOURCES[implementation]
    raw = (ROOT/path).read_bytes()
    records = json.loads((ROOT/"provenance/copied-sources.json").read_text(encoding="utf-8"))
    if not isinstance(records,list):
        raise SourceContractError("The source catalog must be a list of records.")
    catalog = {}
    for record in records:
        if not isinstance(record,dict):
            raise SourceContractError("Each source catalog record must be an object.")
        recorded_path, digest = record.get("path"), record.get("sha256")
        if not isinstance(recorded_path,str) or not recorded_path.strip():
            raise SourceContractError("Each source record must have a nonempty path.")
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise SourceContractError("Each source record must have a lowercase SHA-256 digest.")
        if recorded_path in catalog:
            raise SourceContractError("Duplicate paths make the source catalog ambiguous.")
        catalog[recorded_path] = digest
    if hashlib.sha256(raw).hexdigest() != pinned or catalog.get(path) != pinned:
        raise SourceContractError("The original source differs from the reviewed v0.1.6 source.")
    text = raw.decode("utf-8-sig")
    tree = ast.parse(text)
    function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="nonlinear_circle")
    ranges = [n.iter for n in ast.walk(function) if isinstance(n,ast.For) and isinstance(n.iter,ast.Call) and isinstance(n.iter.func,ast.Name) and n.iter.func.id=="range"]
    stops = [n.test for n in ast.walk(function) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare)
             and ast.unparse(n.test.left)=="float(np.linalg.norm(step))" and len(n.test.ops)==1 and isinstance(n.test.ops[0],ast.LtE)
             and any(isinstance(b,ast.Break) for b in n.body)]
    if len(ranges)!=1 or len(ranges[0].args)!=2 or len(stops)!=1:
        raise SourceContractError("The recorded stopping contract could not be read.")
    first,last = [ast.literal_eval(a) for a in ranges[0].args]
    threshold = float(ast.literal_eval(stops[0].comparators[0]))
    if first!=1 or last-first!=100 or threshold!=1e-13:
        raise SourceContractError("The stopping contract differs from the reviewed source.")
    module = types.ModuleType("_guarded_original_"+implementation)
    module.__file__ = str(ROOT/path)
    exec(compile(text,str(ROOT/path),"exec"),module.__dict__)
    return module, {"path":path,"sha256":pinned,"iteration_limit":last-first,"step_threshold":threshold}


def _observe_solver(function, values):
    previous = sys.gettrace()
    if previous is not None:
        return {"called":False,"unavailable_reason":"existing_trace"}
    observation = {"called":True,"last_step_norm":None,"observation_error":None}
    def trace(frame,event,arg):
        if frame.f_code is function.__code__:
            if event=="return":
                try:
                    if "step" in frame.f_locals:
                        observation["last_step_norm"] = float(np.linalg.norm(frame.f_locals["step"]))
                except Exception as error:
                    observation["observation_error"] = type(error).__name__
            return trace
        return None
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            sys.settrace(trace)
            observation["returned"] = function(values)
        except Exception as error:
            observation["exception"] = {"type":type(error).__name__,"message":str(error)}
        finally:
            sys.settrace(previous)
        observation["warnings"] = [{"category":w.category.__name__,"message":str(w.message)} for w in captured]
    return observation


def guarded_circle_fit(values, implementation="stepped"):
    """Return status + unverified estimate; source and original parameters stay fixed.

    Only the original step stopping condition can qualify an estimate. Rank is
    the original initializer's float64 lstsq rank, not a physical accuracy test.
    """
    result = new_circle_report(implementation)
    def finish(status, reason=None):
        result["status"] = status
        if reason: result["reason"] = reason
        return _safe(result)
    if implementation not in SOURCES:
        return finish("invalid_input","unknown_implementation")
    try:
        raw = np.asarray(values)
        if raw.ndim!=2 or raw.shape[1]!=2:
            return finish("invalid_input","expected_N_by_2")
        if raw.dtype.kind not in "iuf":
            return finish("invalid_input","expected_real_numeric_values")
        with np.errstate(over="ignore",invalid="ignore"):
            points = raw.astype(np.float64,copy=True)
        result["input"] = {"points":len(points),"computation_dtype":"float64"}
        if not np.isfinite(points).all():
            return finish("invalid_input","nonfinite_coordinates")
        if len(points)<3:
            return finish("insufficient_support","at_least_three_points_required")
        unique = len(np.unique(points,axis=0))
        result["input"]["distinct_points"] = unique
        result["input"]["array_sha256"] = hashlib.sha256(points.astype("<f8",copy=False).tobytes()).hexdigest()
        if unique<3:
            return finish("insufficient_support","at_least_three_distinct_points_required")
        with np.errstate(over="ignore",invalid="ignore"):
            matrix = np.column_stack((2*points[:,0],2*points[:,1],np.ones(len(points))))
            rhs = points[:,0]*points[:,0]+points[:,1]*points[:,1]
        if not np.isfinite(matrix).all() or not np.isfinite(rhs).all():
            return finish("invalid_input","initializer_arithmetic_nonfinite")
        _,_,rank,singular = np.linalg.lstsq(matrix,rhs,rcond=None)
        condition = float(singular[0]/singular[-1]) if singular[-1]>0 else None
        result["numeric_support"] = {"initializer_rank":int(rank),"required_rank":3,"singular_values":singular,
                                     "condition_number":condition,"condition_number_used_as_cutoff":False,
                                     "rank_rule":"original initializer basis and numpy.linalg.lstsq(rcond=None)"}
        if rank<3:
            return finish("insufficient_support","initializer_numerical_rank_below_three")
    except (TypeError,ValueError,OverflowError,np.linalg.LinAlgError) as error:
        result["input_error"] = {"type":type(error).__name__,"message":str(error)}
        return finish("invalid_input","input_validation_error")
    try:
        module,contract = _load_original(implementation)
    except (OSError,ValueError,KeyError,StopIteration,SourceContractError) as error:
        result["source_error"] = {"type":type(error).__name__,"message":str(error)}
        return finish("blocked_source_version","source_or_stopping_contract_not_verified")
    result["source"] = contract
    observed = _observe_solver(module.nonlinear_circle,points)
    result["solver_called"] = observed["called"]
    if not observed["called"]:
        return finish("stop_observation_unavailable",observed["unavailable_reason"])
    result["warnings"] = observed.get("warnings",[])
    if "exception" in observed:
        result["solver_error"] = observed["exception"]
        return finish("solver_exception","original_solver_raised")
    try:
        x,y,radius,residual,iterations = observed["returned"]
        residual = np.asarray(residual)
        if residual.ndim!=1 or len(residual)!=len(points):
            return finish("invalid_solver_result","residual_shape_mismatch")
        result["raw_result"] = {"center":[x,y],"radius":radius,"residual_max":np.max(np.abs(residual)),"iterations":iterations}
        finite = np.isfinite(np.r_[x,y,radius,residual]).all()
        if not finite or radius<=0:
            return finish("invalid_solver_result","nonfinite_or_nonpositive_geometry")
        if isinstance(iterations,(bool,np.bool_)) or not isinstance(iterations,(int,np.integer)) or not 1<=iterations<=contract["iteration_limit"]:
            return finish("invalid_solver_result","iteration_count_outside_recorded_contract")
        step = observed.get("last_step_norm")
        result["convergence"].update(iterations=iterations,last_step_norm=step,step_threshold=contract["step_threshold"],iteration_limit=contract["iteration_limit"],observation_error=observed.get("observation_error"))
        if step is None or not math.isfinite(step) or step<0 or observed.get("observation_error"):
            return finish("stop_observation_unavailable","last_step_not_reliably_observed")
        met = step<=contract["step_threshold"]
        result["convergence"]["step_threshold_met"] = met
        if met:
            result["convergence"]["status"] = "recorded_step_threshold_met"
            result["estimate"] = {"center":[x,y],"radius":radius}
            return finish("step_threshold_met")
        status = "iteration_limit_without_step_threshold" if iterations==contract["iteration_limit"] else "stop_condition_not_met"
        result["convergence"]["status"] = status
        return finish(status)
    except (TypeError,ValueError,OverflowError) as error:
        result["solver_error"] = {"type":type(error).__name__,"message":str(error)}
        return finish("invalid_solver_result","return_contract_not_satisfied")
