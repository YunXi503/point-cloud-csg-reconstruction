"""Verify that CI replay checks reject misleading or mismatched reports."""
from pathlib import Path
import copy
import importlib.util
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import geometry_guard as guard
from geometry_fixtures import circle_fixture
spec=importlib.util.spec_from_file_location('circle_replays',ROOT/'tools/verify-circle-replays.py')
replays=importlib.util.module_from_spec(spec);spec.loader.exec_module(replays)


class CircleReplayChecks(unittest.TestCase):
    def setUp(self):
        self.entry=json.loads((ROOT/replays.MANIFEST).read_bytes())['fixtures'][0]
        self.support=replays.read_fixture(self.entry)
        self.report=guard.guarded_circle_fit(circle_fixture('arc_360')[0])
        self.report['input_csv_sha256']=self.support['csv_sha256']

    def errors(self,report=None,exit_code=0):
        return replays.validate_report(self.report if report is None else report,exit_code,'stepped',self.support)

    def test_valid_actual_report_is_accepted(self):
        self.assertEqual(self.errors(),[])

    def test_missing_common_field_is_rejected(self):
        report=copy.deepcopy(self.report);del report['runtime']
        for value in [report,[],None]:
            with self.subTest(report=value):
                self.assertIn('missing_common_report_fields',replays.validate_report(value,0,'stepped',self.support))

    def test_invalid_section_types_are_structurally_rejected(self):
        for key in ('verification','runtime','convergence','input','source','numeric_support'):
            with self.subTest(section=key):
                report=copy.deepcopy(self.report);report[key]=None
                self.assertIn('invalid_report_section_types',self.errors(report))

    def test_parameter_accuracy_claim_is_rejected(self):
        report=copy.deepcopy(self.report);report['verification']['parameters_verified']=True
        self.assertIn('parameter_accuracy_must_remain_unverified',self.errors(report))

    def test_exit_code_disagreement_is_rejected(self):
        self.assertIn('met_status_or_exit',self.errors(exit_code=3))

    def test_estimate_after_unmet_stop_is_rejected(self):
        report=copy.deepcopy(self.report);report['convergence'].update(last_step_norm=2e-6,iterations=100,step_threshold_met=False,status='iteration_limit_without_step_threshold')
        report['raw_result']['iterations']=100;report['status']='iteration_limit_without_step_threshold'
        self.assertIn('unmet_stop_has_estimate',self.errors(report,exit_code=3))

    def test_changed_fixture_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/self.entry['path'];target.parent.mkdir(parents=True)
            target.write_bytes((ROOT/self.entry['path']).read_bytes()+b'\n')
            with self.assertRaises(replays.ReplayContractError):replays.read_fixture(self.entry,root)

    def test_nonstandard_json_nan_is_rejected(self):
        with self.assertRaises(replays.ReplayContractError):replays.strict_json('{"value": NaN}')
