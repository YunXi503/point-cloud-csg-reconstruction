"""Plot observed function timing and process peak working sets; no fitted curve."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"assets/measurements")
    args=parser.parse_args();out=args.output_dir.resolve()
    if out.exists():parser.error("Choose a new output directory; preserve the earlier rendering.")
    source=ROOT/"validation/2026-11-05/measurement-summary.json";data=json.loads(source.read_text(encoding="utf-8"))
    out.mkdir(parents=True)
    rows=[{"n":r["n"],"function_ms_min":r["function_ms"]["min"],"function_ms_median":r["function_ms"]["median"],"function_ms_max":r["function_ms"]["max"],
           "working_set_mib_min":r["peak_working_set_mib"]["min"],"working_set_mib_median":r["peak_working_set_mib"]["median"],"working_set_mib_max":r["peak_working_set_mib"]["max"]} for r in data["scales"]]
    with (out/"scale-data.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
    manifest={"data_kind":"Measured runtime observations on existing STL-derived point subsets, not mock/planning data", "source":source.relative_to(ROOT).as_posix(),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
              "script":"tools/render-measurements.py","script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"data_file":"scale-data.csv","data_sha256":hashlib.sha256((out/"scale-data.csv").read_bytes()).hexdigest(),"error_bars":"observed min/max of three repetitions; not confidence intervals","outputs":[]}
    (out/"data-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"svg.hashsalt":"recorded-scale-20261105"})
    fig,axes=plt.subplots(1,2,figsize=(7.2,3.4));fig.subplots_adjust(left=.10,right=.98,bottom=.27,top=.80,wspace=.38)
    x=np.asarray([r["n"] for r in rows])
    for ax,prefix,color,label in [(axes[0],"function_ms","#0077BB","Function time (ms)"),(axes[1],"working_set_mib","#EE7733","Process peak working set (MiB)")]:
        mid=np.asarray([r[prefix+"_median"] for r in rows]);lo=np.asarray([r[prefix+"_min"] for r in rows]);hi=np.asarray([r[prefix+"_max"] for r in rows])
        ax.errorbar(x,mid,yerr=[mid-lo,hi-mid],color=color,marker="o",capsize=3,linewidth=1.5)
        ax.set(xlabel="Subset point count N",ylabel=label,ylim=(0,float(hi.max())*1.15));ax.set_xticks([1000,5000,10000]);ax.grid(alpha=.18)
    fig.suptitle("L-Bracket region_growing: fixed 2.0 mm / 0.93",fontsize=11,y=.96)
    fig.text(.10,.10,"Three fresh processes per N; error bars = observed min/max.",fontsize=8)
    fig.text(.10,.045,"Working set includes imports and loading the original 10,000-row CSV.",fontsize=8)
    fig.savefig(out/"scaling.png",dpi=450,metadata={"Software":"Matplotlib"})
    fig.savefig(out/"scaling.svg",metadata={"Date":None})
    plt.close(fig)
    manifest["outputs"]=[{"path":name,"sha256":hashlib.sha256((out/name).read_bytes()).hexdigest()} for name in ["scaling.png","scaling.svg"]]
    (out/"data-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(manifest))


if __name__=="__main__":main()
