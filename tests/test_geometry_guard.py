"""Outer-policy fixtures; simulated solver outcomes are not research results."""
from pathlib import Path
import json
import hashlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import geometry_guard as guard
from geometry_fixtures import circle_fixture


class GuardedCircleContracts(unittest.TestCase):
    def setUp(self):
        self.points,_=circle_fixture("arc_360")

    def assert_not_called(self,values,status):
        with patch.object(guard,"_observe_solver") as invoke:
            report=guard.guarded_circle_fit(values)
        self.assertEqual(report["status"],status)
        self.assertFalse(report["solver_called"])
        self.assertIsNone(report["estimate"])
        invoke.assert_not_called()
        json.dumps(report,allow_nan=False)

    def test_analytic_circle_both_sources_preserve_unverified_estimate(self):
        for name in guard.SOURCES:
            with self.subTest(name=name):
                report=guard.guarded_circle_fit(self.points,name)
                self.assertEqual(report["status"],"step_threshold_met")
                np.testing.assert_allclose(report["estimate"]["center"],[2.,-3.],atol=1e-6,rtol=0)
                self.assertLessEqual(abs(report["estimate"]["radius"]-10),1e-6)
                self.assertFalse(report["verification"]["parameters_verified"])
                self.assertEqual(report["source"]["iteration_limit"],100)
                self.assertEqual(report["source"]["step_threshold"],1e-13)

    def test_ten_degree_arc_preserves_original_return(self):
        points,_=circle_fixture("arc_10")
        module,_=guard._load_original("stepped")
        x,y,radius,_,_=module.nonlinear_circle(points)
        report=guard.guarded_circle_fit(points)
        self.assertEqual(report["status"],"step_threshold_met")
        np.testing.assert_allclose(report["estimate"]["center"],[x,y],atol=1e-12,rtol=0)
        self.assertAlmostEqual(report["estimate"]["radius"],radius,places=12)

    def test_input_values_and_order_are_not_modified(self):
        before=self.points.copy();guard.guarded_circle_fit(self.points)
        np.testing.assert_array_equal(before,self.points)

    def test_wrong_shapes_do_not_invoke_solver(self):
        for value in [3,[],[1.,2.],np.zeros((4,3)),np.zeros((2,2,2))]:
            with self.subTest(shape=np.shape(value)):self.assert_not_called(value,"invalid_input")

    def test_nonreal_types_do_not_invoke_solver(self):
        for value in [np.ones((3,2),dtype=bool),np.ones((3,2),dtype=complex),np.array([["1","2"]]*3),np.ones((3,2),dtype=object)]:
            with self.subTest(dtype=value.dtype):self.assert_not_called(value,"invalid_input")

    def test_nonfinite_coordinates_do_not_invoke_solver(self):
        for value in [np.nan,np.inf,-np.inf]:
            points=self.points.copy();points[0,0]=value
            with self.subTest(value=value):self.assert_not_called(points,"invalid_input")

    def test_initializer_overflow_is_rejected_before_solver(self):
        self.assert_not_called(np.asarray([[1e200,0],[0,1e200],[-1e200,0]]),"invalid_input")

    def test_fewer_than_three_points_is_insufficient_support(self):
        for n in [0,1,2]:
            with self.subTest(n=n):self.assert_not_called(self.points[:n],"insufficient_support")

    def test_repeated_points_are_insufficient_support(self):
        self.assert_not_called(np.tile([2.,-3.],(64,1)),"insufficient_support")

    def test_collinear_input_is_insufficient_support(self):
        points,_=circle_fixture("collinear")
        self.assert_not_called(points,"insufficient_support")

    def test_duplicates_with_sufficient_support_are_not_removed(self):
        values=np.r_[self.points,self.points[:3]]
        report=guard.guarded_circle_fit(values)
        self.assertEqual(report["input"]["points"],67)
        self.assertEqual(report["input"]["distinct_points"],64)
        self.assertEqual(report["status"],"step_threshold_met")

    def test_short_arcs_use_observed_status_not_an_angle_cutoff(self):
        for name in ["arc_0.001","arc_0.00001"]:
            report=guard.guarded_circle_fit(circle_fixture(name)[0])
            self.assertFalse(report["numeric_support"]["condition_number_used_as_cutoff"])
            if report["numeric_support"]["initializer_rank"]<3:
                self.assertEqual(report["status"],"insufficient_support")
                self.assertFalse(report["solver_called"])
            elif report["convergence"]["step_threshold_met"] is not True:
                self.assertIsNone(report["estimate"])
            self.assertFalse(report["verification"]["parameters_verified"])

    def policy_report(self,step=1e-14,iterations=1,radius=10.,extra=None):
        observation={"called":True,"returned":(2.,-3.,radius,np.zeros(64),iterations),"last_step_norm":step,"warnings":[]}
        observation.update(extra or {})
        with patch.object(guard,"_observe_solver",return_value=observation):
            return guard.guarded_circle_fit(self.points)

    def test_iteration_limit_without_step_threshold_has_no_estimate(self):
        report=self.policy_report(step=2e-6,iterations=100)
        self.assertEqual(report["status"],"iteration_limit_without_step_threshold")
        self.assertFalse(report["convergence"]["step_threshold_met"])
        self.assertIsNone(report["estimate"])
        self.assertEqual(report["raw_result"]["radius"],10.)

    def test_step_threshold_met_on_iteration_100_is_not_called_nonconvergent(self):
        report=self.policy_report(iterations=100)
        self.assertEqual(report["status"],"step_threshold_met")
        self.assertIsNotNone(report["estimate"])

    def test_missing_step_observation_is_not_guessed_from_iteration_count(self):
        report=self.policy_report(step=None)
        self.assertEqual(report["status"],"stop_observation_unavailable")
        self.assertIsNone(report["estimate"])
        self.assertIsNone(report["convergence"]["step_threshold_met"])

    def test_observation_error_does_not_qualify_estimate(self):
        report=self.policy_report(extra={"observation_error":"fixture-error"})
        self.assertEqual(report["status"],"stop_observation_unavailable")
        self.assertIsNone(report["estimate"])

    def test_nonfinite_step_is_not_reported_as_convergence(self):
        report=self.policy_report(step=float('nan'))
        self.assertEqual(report["status"],"stop_observation_unavailable")
        json.dumps(report,allow_nan=False)

    def test_small_residual_does_not_verify_radius(self):
        report=self.policy_report(radius=7.)
        self.assertEqual(report["raw_result"]["residual_max"],0.)
        self.assertFalse(report["verification"]["parameters_verified"])

    def test_invalid_solver_result_has_no_estimate_and_is_strict_json(self):
        for radius in [0.,-1.,float('inf'),float('nan')]:
            with self.subTest(radius=radius):
                report=self.policy_report(radius=radius)
                self.assertEqual(report["status"],"invalid_solver_result")
                self.assertIsNone(report["estimate"])
                json.dumps(report,allow_nan=False)

    def test_solver_exception_restores_trace(self):
        def failing(values):raise np.linalg.LinAlgError("software fixture")
        contract={"iteration_limit":100,"step_threshold":1e-13}
        before=sys.gettrace()
        with patch.object(guard,"_load_original",return_value=(types.SimpleNamespace(nonlinear_circle=failing),contract)):
            report=guard.guarded_circle_fit(self.points)
        self.assertEqual(report["status"],"solver_exception")
        self.assertIs(sys.gettrace(),before)

    def test_existing_trace_is_not_overwritten(self):
        def existing(frame,event,arg):return existing
        before=sys.gettrace()
        try:
            sys.settrace(existing)
            report=guard.guarded_circle_fit(self.points)
            self.assertIs(sys.gettrace(),existing)
        finally:sys.settrace(before)
        self.assertEqual(report["status"],"stop_observation_unavailable")
        self.assertFalse(report["solver_called"])

    def test_source_drift_is_blocked_before_execution(self):
        relative,pinned=guard.SOURCES['stepped']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/relative;source.parent.mkdir(parents=True)
            source.write_text("raise AssertionError('must not execute drifted code')",encoding='utf-8')
            (root/'provenance').mkdir();(root/'provenance/copied-sources.json').write_text(json.dumps([{'path':relative,'sha256':pinned}]),encoding='utf-8')
            with patch.object(guard,'ROOT',root),patch.object(guard,'_observe_solver') as invoke:
                report=guard.guarded_circle_fit(self.points)
        self.assertEqual(report['status'],'blocked_source_version');invoke.assert_not_called()

    def catalog_report(self,payload):
        relative,_=guard.SOURCES['stepped']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/relative;source.parent.mkdir(parents=True)
            source.write_bytes((ROOT/relative).read_bytes())
            (root/'provenance').mkdir();(root/'provenance/copied-sources.json').write_bytes(payload)
            with patch.object(guard,'ROOT',root),patch.object(guard,'_observe_solver') as invoke:
                report=guard.guarded_circle_fit(self.points)
            invoke.assert_not_called()
        self.assertEqual(report['status'],'blocked_source_version')
        self.assertFalse(report['solver_called']);self.assertIsNone(report['estimate'])
        json.dumps(report,allow_nan=False)
        return report

    def test_malformed_catalog_structure_is_blocked_without_solver(self):
        path,pinned=guard.SOURCES['stepped']
        for value in [None,{},[17],[{}],[{'path':[], 'sha256':pinned}],
                      [{'path':'', 'sha256':pinned}],[{'path':path,'sha256':None}],
                      [{'path':path,'sha256':'g'*64}]]:
            with self.subTest(catalog=value):self.catalog_report(json.dumps(value).encode('utf-8'))

    def test_malformed_catalog_json_is_blocked_without_solver(self):
        self.catalog_report(b'[{broken JSON')

    def test_duplicate_catalog_paths_are_blocked_without_solver(self):
        path,pinned=guard.SOURCES['stepped'];record={'path':path,'sha256':pinned}
        self.catalog_report(json.dumps([record,record]).encode('utf-8'))


class CircleCliContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.source=self.folder/'input.csv';self.output=self.folder/'report.json'

    def run_cli(self):
        return subprocess.run([sys.executable,str(ROOT/'tools/check-circle-fit.py'),'--input',str(self.source),'--output',str(self.output)],capture_output=True,text=True,encoding='utf-8')

    def test_valid_uv_csv_returns_unverified_estimate(self):
        np.savetxt(self.source,circle_fixture('arc_360')[0],delimiter=',',header='U,V',comments='',fmt='%.17g')
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(self.output.read_text(encoding='utf-8'));self.assertEqual(report['status'],'step_threshold_met');self.assertFalse(report['verification']['parameters_verified'])

    def test_xyz_header_is_rejected_without_guessing_projection(self):
        self.source.write_text('X,Y,Z\n1,2,3\n',encoding='utf-8');self.assertEqual(self.run_cli().returncode,2)
        report=json.loads(self.output.read_text(encoding='utf-8'));self.assertFalse(report['solver_called'])

    def test_malformed_row_is_reported_before_fitting(self):
        self.source.write_text('U,V\n1,2,3\n',encoding='utf-8');self.assertEqual(self.run_cli().returncode,2)
        self.assertEqual(json.loads(self.output.read_text(encoding='utf-8'))['reason'],'csv_input_error')

    def test_non_numeric_row_is_reported_before_fitting(self):
        self.source.write_text('U,V\nhello,2\n',encoding='utf-8');self.assertEqual(self.run_cli().returncode,2)

    def test_nonfinite_csv_is_rejected(self):
        self.source.write_text('U,V\nNaN,2\n1,0\n0,1\n',encoding='utf-8');self.assertEqual(self.run_cli().returncode,2)
        self.assertEqual(json.loads(self.output.read_text(encoding='utf-8'))['reason'],'nonfinite_coordinates')

    def test_existing_report_is_preserved(self):
        self.output.write_bytes(b'keep prior report');self.assertNotEqual(self.run_cli().returncode,0)
        self.assertEqual(self.output.read_bytes(),b'keep prior report')

    def assert_common_fields(self,report):
        required={'schema_version','implementation','status','reason','solver_called','estimate','raw_result',
                  'input_csv_sha256','convergence','verification','runtime'}
        self.assertTrue(required<=report.keys())
        self.assertEqual(report['schema_version'],'1');self.assertEqual(report['implementation'],'stepped')
        self.assertIsNone(report['estimate']);self.assertIsNone(report['raw_result'])
        self.assertFalse(report['solver_called']);self.assertFalse(report['verification']['parameters_verified'])
        self.assertIsNone(report['convergence']['step_threshold_met'])
        self.assertTrue(report['runtime']['python']);self.assertTrue(report['runtime']['numpy'])
        self.assertTrue(report['verification']['reason'])

    def test_csv_and_numeric_failures_share_common_report_fields(self):
        for name,text in [('bad_header','X,Y,Z\n1,2,3\n'),('nonfinite','U,V\nNaN,2\n1,0\n0,1\n')]:
            with self.subTest(name=name):
                self.output=self.folder/(name+'.json');self.source.write_bytes(text.encode('utf-8'))
                self.assertEqual(self.run_cli().returncode,2)
                self.assert_common_fields(json.loads(self.output.read_bytes()))

    def test_unreadable_input_has_null_digest_and_common_report(self):
        self.assertEqual(self.run_cli().returncode,2)
        report=json.loads(self.output.read_bytes());self.assert_common_fields(report)
        self.assertIsNone(report['input_csv_sha256'])

    def test_parse_failure_binds_the_bytes_that_were_read(self):
        raw=b'U,V\nnot-a-number,2\n';self.source.write_bytes(raw)
        self.assertEqual(self.run_cli().returncode,2)
        report=json.loads(self.output.read_bytes());self.assert_common_fields(report)
        self.assertEqual(report['input_csv_sha256'],hashlib.sha256(raw).hexdigest())
