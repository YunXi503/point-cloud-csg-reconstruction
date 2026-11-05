"""Replay all twelve public circle CLI cases without changing solver parameters."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
import io
import json
import math
import subprocess
import sys

import numpy as np
from geometry_guard import SOURCES

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='examples/guarded-circle/manifest.json'
MANIFEST_SHA256='3d1578db9e6d1a7d0b087902ae39bb4a4a6c9efc1169a267be39547096a2f5a6'
FIXTURES={'arc_360','arc_10','arc_0.001','arc_0.00001','collinear','coincident'}
COMMON={'schema_version','implementation','status','reason','solver_called','estimate','raw_result',
        'input_csv_sha256','convergence','verification','runtime'}


class ReplayContractError(ValueError):
    pass


def sha(raw):return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def invalid(value):raise ReplayContractError('Non-standard JSON constant: '+value)
    return json.loads(raw,parse_constant=invalid)


def read_fixture(entry,root=ROOT):
    name=Path(entry['path']).stem
    if name not in FIXTURES or entry['path']!='examples/guarded-circle/'+name+'.csv':
        raise ReplayContractError('Unexpected fixture path')
    raw=(root/entry['path']).read_bytes()
    if sha(raw)!=entry['sha256']:raise ReplayContractError('Fixture CSV hash mismatch: '+name)
    if raw.splitlines()[0]!=b'U,V':raise ReplayContractError('Fixture header mismatch')
    points=np.loadtxt(io.BytesIO(raw),delimiter=',',skiprows=1)
    if points.shape!=(entry['points'],2) or not np.isfinite(points).all():raise ReplayContractError('Fixture shape or finite-value mismatch')
    array_sha=sha(points.astype('<f8',copy=False).tobytes())
    if array_sha!=entry['array_sha256']:raise ReplayContractError('Fixture array hash mismatch: '+name)
    matrix=np.column_stack((2*points[:,0],2*points[:,1],np.ones(len(points))))
    rhs=points[:,0]**2+points[:,1]**2
    rank=int(np.linalg.lstsq(matrix,rhs,rcond=None)[2])
    return {'name':name,'points':len(points),'distinct_points':len(np.unique(points,axis=0)),
            'rank':rank,'array_sha256':array_sha,'csv_sha256':sha(raw),'truth':entry['analytic_truth']}


def validate_report(report,exit_code,implementation,support):
    """Check current numerical observations, not a fixed cross-CPU status count."""
    errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    if not isinstance(report,dict) or not COMMON<=report.keys():return ['missing_common_report_fields']
    if any(not isinstance(report[key],dict) for key in ('convergence','verification','runtime')) or any(key in report and not isinstance(report[key],dict) for key in ('input','numeric_support','source')):
        return ['invalid_report_section_types']
    require(report['schema_version']=='1','schema_version')
    require(report['implementation']==implementation,'implementation')
    require(report['input_csv_sha256']==support['csv_sha256'],'input_csv_sha256')
    require(report['verification'].get('parameters_verified') is False,'parameter_accuracy_must_remain_unverified')
    require(report['verification'].get('status')=='not_assessed','verification_status')
    require(bool(report['verification'].get('reason')),'verification_reason')
    require(bool(report['runtime'].get('python')) and bool(report['runtime'].get('numpy')),'runtime')
    require(report.get('input',{}).get('array_sha256')==support['array_sha256'],'input_array_sha256')
    require(report.get('input',{}).get('points')==support['points'],'point_count')
    require(report.get('input',{}).get('distinct_points')==support['distinct_points'],'distinct_point_count')
    convergence=report['convergence']
    if support['distinct_points']<3 or support['rank']<3:
        require(report['status']=='insufficient_support' and exit_code==2,'unsupported_input_status_or_exit')
        require(report['solver_called'] is False,'unsupported_input_called_solver')
        require(report['estimate'] is None and report['raw_result'] is None,'unsupported_input_has_geometry')
        require(convergence.get('step_threshold_met') is None,'unsupported_input_claimed_stop')
        require(convergence.get('status')=='not_observed','unsupported_input_observation_status')
        expected_reason='at_least_three_distinct_points_required' if support['distinct_points']<3 else 'initializer_numerical_rank_below_three'
        require(report['reason']==expected_reason,'unsupported_input_reason')
        if support['distinct_points']>=3:require(report.get('numeric_support',{}).get('initializer_rank')==support['rank'],'initializer_rank')
        return errors
    require(report['solver_called'] is True,'supported_fixture_solver_not_called')
    require(report.get('numeric_support',{}).get('initializer_rank')==support['rank'],'initializer_rank')
    require(report.get('source',{}).get('path')==SOURCES[implementation][0] and report.get('source',{}).get('sha256')==SOURCES[implementation][1],'original_source_binding')
    require(convergence.get('step_threshold')==1e-13 and convergence.get('iteration_limit')==100,'original_stopping_parameters')
    raw=report['raw_result'];step=convergence.get('last_step_norm');iterations=convergence.get('iterations')
    if not isinstance(raw,dict):return errors+['missing_original_return']
    if not isinstance(step,(int,float)) or isinstance(step,bool) or not math.isfinite(step) or step<0:return errors+['unreliable_step_observation']
    if not isinstance(iterations,int) or isinstance(iterations,bool) or not 1<=iterations<=100:return errors+['invalid_iteration_count']
    try:
        require(len(raw['center'])==2 and all(math.isfinite(x) for x in raw['center']),'invalid_center')
        require(math.isfinite(raw['radius']) and raw['radius']>0 and math.isfinite(raw['residual_max']),'invalid_raw_geometry')
    except (KeyError,TypeError,ValueError):return errors+['invalid_original_return']
    require(raw.get('iterations')==iterations,'iteration_count_mismatch')
    require(convergence.get('observation_error') is None,'observation_error')
    met=step<=1e-13
    require(convergence.get('step_threshold_met') is met,'step_flag_mismatch')
    if met:
        require(report['status']=='step_threshold_met' and exit_code==0,'met_status_or_exit')
        require(convergence.get('status')=='recorded_step_threshold_met','met_convergence_status')
        require(report['estimate']=={'center':raw['center'],'radius':raw['radius']},'estimate_changed_original_parameters')
    else:
        expected='iteration_limit_without_step_threshold' if iterations==100 else 'stop_condition_not_met'
        require(report['status']==expected and exit_code==3,'unmet_status_or_exit')
        require(convergence.get('status')==expected,'unmet_convergence_status')
        require(report['estimate'] is None,'unmet_stop_has_estimate')
    if support['name'] in {'arc_360','arc_10'}:
        truth=support['truth']
        require(met,'well_supported_fixture_did_not_meet_stop')
        require(abs(raw['radius']-truth['radius'])<=1e-6 and np.linalg.norm(np.asarray(raw['center'])-truth['center'])<=1e-6,'existing_analytic_fixture_accuracy')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():parser.error('Output already exists; preserve it and choose a new directory.')
    args.output_dir.mkdir(parents=True,exist_ok=False)
    result={'schema_version':'1','status':'running','scope':'Twelve CLI engineering replays; no research parameter changes or general accuracy claim.',
            'runtime':{'python':sys.version,'numpy':np.__version__},'records':[],
            'bindings':[{'path':p,'sha256':sha((ROOT/p).read_bytes())} for p in ['tools/geometry_guard.py','tools/check-circle-fit.py','tools/verify-circle-replays.py',MANIFEST]]}
    def save():
        (args.output_dir/'circle-replay-results.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
    save()
    try:
        raw=(ROOT/MANIFEST).read_bytes()
        if sha(raw)!=MANIFEST_SHA256:raise ReplayContractError('Public v0.1.7 fixture manifest changed')
        catalog=strict_json(raw);entries=catalog['fixtures']
        if len(entries)!=6 or {Path(e['path']).stem for e in entries}!=FIXTURES:raise ReplayContractError('Expected all six distinct public fixtures')
        if sha((ROOT/catalog['generator']).read_bytes())!=catalog['generator_sha256']:raise ReplayContractError('Original fixture generator changed')
        for entry in entries:
            support=read_fixture(entry)
            for implementation in SOURCES:
                name=implementation+'-'+support['name'];target=args.output_dir/(name+'.json')
                command=[sys.executable,str(ROOT/'tools/check-circle-fit.py'),'--input',str(ROOT/entry['path']),'--implementation',implementation,'--output',str(target.resolve())]
                with (args.output_dir/(name+'.stdout.log')).open('w',encoding='utf-8') as stdout,(args.output_dir/(name+'.stderr.log')).open('w',encoding='utf-8') as stderr:
                    run=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,check=False)
                report=strict_json(target.read_bytes())
                errors=validate_report(report,run.returncode,implementation,support)
                item={'implementation':implementation,'fixture':support['name'],'support':support,'exit_code':run.returncode,'report':report,'checks':'pass' if not errors else 'failed','errors':errors}
                result['records'].append(item);save()
                label=report.get('status','missing') if isinstance(report,dict) else 'invalid_report'
                print(name+': '+item['checks']+' ('+str(label)+')',flush=True)
                if errors:raise ReplayContractError('; '.join(errors))
        result['status']='pass' if len(result['records'])==12 else 'failed'
        result['status_counts']=dict(Counter(r['report']['status'] for r in result['records']))
    except (OSError,ValueError,KeyError,TypeError) as error:
        result['status']='failed';result['error']={'type':type(error).__name__,'message':str(error)}
    save()
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
