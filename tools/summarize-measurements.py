"""Derive descriptive statistics from preserved engineering measurements."""
from pathlib import Path
from statistics import median
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def stats(values):
    return {"n":len(values),"min":min(values),"median":median(values),"max":max(values)}


def write_csv(path, rows):
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)


def main():
    source=ROOT/"validation/2026-11-05/measurement-results.json"
    data=json.loads(source.read_text(encoding="utf-8"))
    if data["status"]!="completed":raise ValueError("Collection is incomplete.")
    destination=ROOT/"validation/2026-11-05/measurement-summary.json"
    if destination.exists():raise FileExistsError("Preserve previous statistics; create a new version.")
    stage_rows=[];stages=[]
    for run in data["stage_runs"]:
        if not run["valid_measurement"]:raise ValueError("Do not omit invalid observations silently.")
        stage_rows.append({"phase":run["phase"],"case":run["case"],"repeat":run["repeat"],"wall_seconds":run["metrics"]["wall_seconds"],"peak_working_set_bytes":run["metrics"]["peak_working_set_bytes"]})
    for phase,case in dict.fromkeys((r["phase"],r["case"]) for r in stage_rows):
        rows=[r for r in stage_rows if r["phase"]==phase and r["case"]==case]
        stages.append({"phase":phase,"case":case,"wall_seconds":stats([r["wall_seconds"] for r in rows]),"peak_working_set_mib":stats([r["peak_working_set_bytes"]/1048576 for r in rows])})
    scale_rows=[];scales=[]
    for run in data["scale_runs"]:
        o=run["observation"];scale_rows.append({"n":o["n"],"repeat":run["repeat"],"function_seconds":o["function_seconds"],"process_seconds":run["metrics"]["wall_seconds"],"peak_working_set_bytes":run["metrics"]["peak_working_set_bytes"],"components":o["components"],"indices_sha256":o["indices_sha256"],"labels_sha256":o["labels_sha256"]})
    for n in dict.fromkeys(r["n"] for r in scale_rows):
        runs=[r for r in data["scale_runs"] if r["observation"]["n"]==n];observations=[r["observation"] for r in runs]
        counted=next(r["observation"] for r in data["scale_counts"] if r["observation"]["n"]==n)
        for field in ["indices_sha256","points_sha256","normals_sha256"]:
            if len({o[field] for o in observations} | {counted[field]})!=1:raise ValueError("Scale inputs differ: "+field)
        if len({o["labels_sha256"] for o in observations})!=1:raise ValueError("Repeated partition labels differ.")
        scales.append({"n":n,"distance_pairs":counted["distance_pairs"],"components":observations[0]["components"],
                       "function_ms":stats([o["function_seconds"]*1000 for o in observations]),
                       "process_seconds":stats([r["metrics"]["wall_seconds"] for r in runs]),
                       "peak_working_set_mib":stats([r["metrics"]["peak_working_set_bytes"]/1048576 for r in runs]),
                       "repeated_inputs_and_labels_identical":True})
    surface_rows=[]
    for run in data["surface_diagnostics"]:
        o=run["observation"];s=o["surface_selector"];v=s.get("result",{})
        surface_rows.append({"module":o["module"],"fixture":o["fixture"],"points":o["points"],"position_rank":o["position_rank"],"selector_outcome":s["outcome"],"geometry":v.get("geometry"),"selection":v.get("selection"),"exception_type":s.get("exception_type"),"radius":v.get("radius"),"residual_max":v.get("residual_max")})
    circle_rows=[]
    for run in data["circle_diagnostics"]:
        o=run["observation"];s=o["solver"];v=s.get("result",{})
        circle_rows.append({"module":o["module"],"fixture":o["fixture"],"outcome":s["outcome"],**{k:v.get(k) for k in ["radius","iterations","last_step_norm","recorded_step_threshold_met","reached_iteration_limit","radius_error","center_error","residual_max"]}})
    report={"date":"2026-11-05","scope":"Descriptive min/median/max, three repetitions; not confidence intervals or a method superiority claim",
            "source":"validation/2026-11-05/measurement-results.json","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "summary_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"stage_runs":len(stage_rows),"output_hash_checks":sum(len(r["outputs"]) for r in data["stage_runs"]),
            "stages":stages,"scale_runs":len(scale_rows),"scales":scales,"surface_diagnostics":len(surface_rows),"circle_diagnostics":len(circle_rows),
            "circle_limit_without_step_threshold":sum(r["reached_iteration_limit"] is True and r["recorded_step_threshold_met"] is False for r in circle_rows),
            "surface_selector_exceptions":sum(r["selector_outcome"]=="exception" for r in surface_rows),
            "characterization_is_not_all_inputs_accepted_or_correct":True}
    for name,rows in [("measurement-stage-runs.csv",stage_rows),("measurement-scale-runs.csv",scale_rows),("geometry-surface-observations.csv",surface_rows),("geometry-circle-observations.csv",circle_rows)]:
        write_csv(destination.parent/name,rows)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"stage_runs":len(stage_rows),"scale_runs":len(scale_rows),"surfaces":len(surface_rows),"circles":len(circle_rows),"iteration_limit_without_step_threshold":report["circle_limit_without_step_threshold"]}))


if __name__=="__main__":main()
