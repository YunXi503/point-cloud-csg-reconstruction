"""Fit explicit U,V coordinates through an optional guarded original solver."""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json

from geometry_guard import guarded_circle_fit, new_circle_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--implementation",choices=["stepped","lbracket"],default="stepped")
    args=parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; preserve it and choose a new report.")
    raw=None
    try:
        values=[]
        raw=args.input.read_bytes()
        with io.StringIO(raw.decode("utf-8-sig"),newline="") as stream:
            reader=csv.reader(stream)
            if next(reader,None)!=["U","V"]:
                raise ValueError("Expected exactly U,V; no 3D projection or axis is inferred.")
            for index,row in enumerate(reader,2):
                if len(row)!=2:
                    raise ValueError("Expected two columns at row "+str(index))
                try: values.append([float(row[0]),float(row[1])])
                except ValueError: raise ValueError("Non-numeric value at row "+str(index)) from None
        report=guarded_circle_fit(values,args.implementation)
    except (OSError,UnicodeError,ValueError,csv.Error) as error:
        report=new_circle_report(args.implementation)
        report.update(reason="csv_input_error",input_error={"type":type(error).__name__,"message":str(error)})
    report["input_csv_sha256"]=hashlib.sha256(raw).hexdigest() if raw is not None else None
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write("\n")
    print(report["status"]+"; parameter accuracy remains unverified")
    if report["status"]=="step_threshold_met":return 0
    return 3 if report["status"] in {"iteration_limit_without_step_threshold","stop_condition_not_met"} else 2


if __name__=="__main__":raise SystemExit(main())
