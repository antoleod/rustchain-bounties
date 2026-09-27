# SPDX-License-Identifier: MIT
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ACTION_PATH = Path(__file__).parents[1] / ".github" / "actions" / "bcos-scan" / "main.py"
SPEC = importlib.util.spec_from_file_location("bcos_action", ACTION_PATH)
bcos_action = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(bcos_action)


def sample_report(tier_met=True):
    return {
        "trust_score": 75,
        "cert_id": "BCOS-1234abcd",
        "tier": "L1",
        "tier_met": tier_met,
        "score_breakdown": {"license_compliance": 20, "test_evidence": 10},
    }


class BCOSActionTests(unittest.TestCase):
    def test_run_engine_accepts_tier_miss_report(self):
        completed = mock.Mock(returncode=1, stdout=json.dumps(sample_report(False)), stderr="")
        with mock.patch.object(bcos_action.subprocess, "run", return_value=completed) as run:
            report = bcos_action.run_engine(Path("engine.py"), "/repo", "L1", "alice")
        self.assertFalse(report["tier_met"])
        self.assertIn("--reviewer", run.call_args.args[0])

    def test_comment_contains_badge_breakdown_and_certificate(self):
        body = bcos_action.report_comment(sample_report())
        self.assertIn(bcos_action.COMMENT_MARKER, body)
        self.assertIn("img.shields.io/badge/BCOS-75%2F100-yellow", body)
        self.assertIn("License Compliance", body)
        self.assertIn("BCOS-1234abcd", body)

    def test_comment_is_updated_instead_of_duplicated(self):
        event = {
            "repository": {"full_name": "owner/repo"},
            "pull_request": {"number": 7},
        }
        existing = [{"body": bcos_action.COMMENT_MARKER, "url": "https://api/comments/1"}]
        with mock.patch.object(bcos_action, "request_json", side_effect=[existing, {}]) as request:
            bcos_action.post_pr_comment(sample_report(), event, "token")
        self.assertEqual("PATCH", request.call_args_list[1].kwargs["method"])

    def test_attestation_is_only_anchored_for_a_confirmed_merge(self):
        open_event = {"action": "opened", "pull_request": {"merged": False}}
        merged_event = {
            "action": "closed",
            "repository": {"full_name": "owner/repo"},
            "pull_request": {"number": 7, "merged": True, "merge_commit_sha": "abc"},
        }
        with mock.patch.object(bcos_action, "request_json") as request:
            bcos_action.anchor_if_merged(sample_report(), open_event, "https://node.example")
            request.assert_not_called()
            bcos_action.anchor_if_merged(sample_report(False), merged_event, "https://node.example")
            request.assert_not_called()
            bcos_action.anchor_if_merged(sample_report(), merged_event, "https://node.example/")
        self.assertEqual("https://node.example/attest", request.call_args.args[0])
        self.assertEqual("abc", request.call_args.kwargs["payload"]["merged_commit"])

    def test_main_runs_scan_writes_outputs_and_reports_tier_miss(self):
        event = {"repository": {"full_name": "owner/repo"}}
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            output_path = Path(directory) / "output.txt"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            environment = {
                "INPUT_TIER": "L1",
                "INPUT_REVIEWER": "alice",
                "INPUT_NODE_URL": "https://node.example",
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_OUTPUT": str(output_path),
                "GITHUB_WORKSPACE": directory,
            }
            with mock.patch.dict(bcos_action.os.environ, environment, clear=True), mock.patch.object(
                bcos_action, "download_engine"
            ), mock.patch.object(bcos_action, "run_engine", return_value=sample_report(False)):
                result = bcos_action.main()
            outputs = output_path.read_text(encoding="utf-8")
        self.assertEqual(1, result)
        self.assertIn("trust_score=75", outputs)
        self.assertIn("cert_id=BCOS-1234abcd", outputs)
        self.assertIn("tier_met=false", outputs)


if __name__ == "__main__":
    unittest.main()
