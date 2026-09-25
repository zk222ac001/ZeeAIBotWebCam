"""Offline tests: no Raspberry Pi, motor SDK, or real microphone/camera is used."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import which
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/classroom_pilot_check.py"
SPEC = importlib.util.spec_from_file_location("classroom_pilot_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def payloads():
    return {
        "safety": {"state": "idle", "motion_active": False, "motion_enabled": True,
                   "watchdog_running": True},
        "conference": {"running": True, "active_sessions": 1, "auth_required": False,
                       "publish_video": True, "publish_audio": True,
                       "remote_audio_playback": True,
                       "sessions": [{"session_id": "DO_NOT_LOG", "connection_state": "connected"}]},
        "camera": {"connected": True, "running": True, "sequence": 1, "people_count": 2},
        "audio": {"connected": True, "running": True, "sequence": 2,
                  "speech_state": "speaking", "speech_active": True,
                  "doa_degrees_raw": 108.32, "doa_degrees": 0.0},
        "speaker": {"state": "speaker_selected", "sequence": 3, "speaker_id": "DO_NOT_LOG",
                    "candidate_index": 0, "center": {"x": 0.5, "y": 0.5},
                    "confidence": 0.8, "camera_angle_degrees": 0.0,
                    "doa_degrees": 0.0, "angular_error_degrees": 0.0},
        "tracking": {"state": "tracking", "sequence": 4, "target_id": "DO_NOT_LOG",
                     "in_dead_zone": True, "error": {"x": 0.0, "y": 0.0}},
        "pan_tilt": {"state": "centered", "sequence": 5, "mode": "execute",
                     "pan": {"planned_pulse": 1500, "minimum": 1350, "maximum": 1650},
                     "tilt": {"planned_pulse": 1500, "minimum": 1350, "maximum": 1650},
                     "execution": {"executed": True, "last_error": ""}},
    }


def values():
    return {name: pilot.project(name, data) for name, data in payloads().items()}


class PilotTests(unittest.TestCase):
    def test_healthy_snapshot_is_not_overall_pass(self):
        data = values()
        self.assertEqual(pilot.assess(data, {}, "speaker_switch"), [])
        record = {"elapsed_s": 0.0, "span_s": 0.1, "phase": "speaker_switch", "flags": []}
        report = pilot.make_report([record], 600, 600, "duration_complete", 2)
        self.assertEqual(report["result"], "NO_TELEMETRY_ALERTS")
        self.assertTrue(all(v == "NOT_TESTED" for v in report["manual_checks"].values()))

    def test_projection_drops_credentials_and_identity(self):
        data = payloads()
        for block in data.values():
            block.update({"token": "SECRET", "message": "SECRET", "sdp": "SECRET"})
        data["pan_tilt"]["execution"]["last_error"] = "SECRET"
        encoded = json.dumps({n: pilot.project(n, p) for n, p in data.items()})
        self.assertNotIn("SECRET", encoded)
        self.assertNotIn("DO_NOT_LOG", encoded)
        self.assertTrue(pilot.project("pan_tilt", data["pan_tilt"])["execution_error"])

    def test_nonfinite_values_are_not_logged(self):
        data = payloads()["audio"]
        data["doa_degrees"] = float("nan")
        data["doa_degrees_raw"] = float("inf")
        clean = pilot.project("audio", data)
        self.assertIsNone(clean["doa_degrees"])
        self.assertIsNone(clean["doa_degrees_raw"])
        json.dumps(clean, allow_nan=False)

    def test_missing_and_malformed_fields_do_not_crash(self):
        clean = pilot.project("pan_tilt", {"pan": [], "execution": None})
        self.assertIsNone(clean["pan"])
        self.assertIn("pan:range_unavailable", pilot.assess({}, {}, "speaker_switch"))

    def test_connected_configuration_alone_is_insufficient(self):
        data = values()
        data["conference"]["connected_sessions"] = 0
        self.assertIn("conference:no_connected_session", pilot.assess(data, {}, "speaker_switch"))

    def test_expected_reconnect_gap_is_not_connection_failure(self):
        data = values()
        data["conference"]["connected_sessions"] = 0
        self.assertNotIn("conference:no_connected_session", pilot.assess(data, {}, "reconnect"))

    def test_motion_is_reported(self):
        data = values()
        data["safety"]["motion_active"] = True
        self.assertIn("safety:motion_active", pilot.assess(data, {}, "speaker_switch"))

    def test_missing_motion_state_is_not_assumed_safe(self):
        data = values()
        data["safety"].pop("motion_active")
        self.assertIn("safety:motion_state_unknown", pilot.assess(data, {}, "speaker_switch"))

    def test_read_sample_stops_after_unknown_safety(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get(self, name):
                self.calls.append(name)
                return {}
        client = Client()
        pilot.read_sample(client)
        self.assertEqual(client.calls, ["safety"])

    def test_limits_are_review_observations(self):
        data = values()
        data["pan_tilt"]["pan"] = 1650
        data["pan_tilt"]["tilt"] = 1700
        flags = pilot.assess(data, {}, "speaker_switch")
        self.assertIn("pan:at_configured_limit", flags)
        self.assertIn("tilt:outside_configured_range", flags)

    def test_idle_heartbeat_does_not_need_control_lease(self):
        data = values()
        data["safety"]["heartbeat_fresh"] = False
        self.assertEqual(pilot.assess(data, {}, "speaker_switch"), [])

    def test_remote_selection_is_review_not_echo_claim(self):
        flags = pilot.assess(values(), {}, "remote_only")
        self.assertIn("speaker:selected_during_remote_only_REVIEW", flags)
        self.assertNotIn("echo_detected", " ".join(flags))

    def test_sequences_do_not_advance_from_polling_alone(self):
        tracker = pilot.SequenceWatch()
        tracker.check(values(), 0, 5)
        self.assertIn("camera:sequence_not_advancing", tracker.check(values(), 6, 5))
        data = values()
        data["camera"]["sequence"] = 2
        self.assertNotIn("camera:sequence_not_advancing", tracker.check(data, 7, 5))

    def test_reset_and_unknown_sequence_are_reported(self):
        tracker = pilot.SequenceWatch()
        tracker.check(values(), 0, 5)
        data = values()
        data["camera"]["sequence"] = 0
        data["audio"]["sequence"] = None
        flags = tracker.check(data, 1, 5)
        self.assertIn("camera:sequence_reset", flags)
        self.assertIn("audio:sequence_unavailable", flags)

    def test_partial_run_marked_incomplete(self):
        report = pilot.make_report([], 600, 2, "interrupted", 2)
        self.assertEqual(report["result"], "INCOMPLETE")

    def test_phases(self):
        self.assertEqual(pilot.phase_at(0, 600)[0], "speaker_switch")
        self.assertEqual(pilot.phase_at(240, 600)[0], "remote_only")
        self.assertEqual(pilot.phase_at(600, 600)[0], "reconnect")

    def test_invalid_origins_rejected_before_network(self):
        for url in ("http://localhost", "https://user:pw@host", "https://host/api/safety",
                    "https://host?token=x", "https://host#test"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                pilot.StatusClient(url, Path("not-used.crt"))

    def test_redirects_are_not_followed(self):
        handler = pilot.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://other"))

    def test_unknown_paths_rejected(self):
        client = pilot.StatusClient.__new__(pilot.StatusClient)
        with self.assertRaises(KeyError):
            client.get("/api/control/motion")

    def test_report_files_and_no_claim_of_pass(self):
        report = pilot.make_report([], 600, 1, "interrupted", 2)
        with tempfile.TemporaryDirectory() as temp:
            pilot.write_reports(Path(temp), report)
            md = (Path(temp) / "report.md").read_text()
            self.assertIn("Human checks - NOT TESTED", md)
            self.assertIn("cannot stop motors", md)
            self.assertEqual(json.loads((Path(temp) / "report.json").read_text()), report)

    def test_cli_rejects_nan_and_negative(self):
        for value in ("nan", "inf", "-1", "0"):
            with self.subTest(value=value), self.assertRaises(Exception):
                pilot.finite_positive(value)

    def test_read_failure_does_not_leak_error_details(self):
        class Client:
            def get(self, name):
                raise urllib.error.URLError("SECRET_TOKEN_OR_SERVER_TEXT")
        data, errors = pilot.read_sample(Client())
        self.assertNotIn("SECRET", json.dumps(errors))
        self.assertEqual(data, {})


@unittest.skipUnless(which("openssl"), "OpenSSL needed only for simulated HTTPS tests")
class HttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.cert = cls.root / "ca.crt"
        cls.key = cls.root / "server.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(cls.key), "-out", str(cls.cert), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
            "-addext", "basicConstraints=critical,CA:TRUE",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.calls = []
        outer = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.calls.append((self.command, self.path))
                by_path = {p: n for n, p in pilot.ENDPOINTS.items()}
                name = by_path.get(self.path)
                if name is None:
                    self.send_error(404)
                    return
                data = copy.deepcopy(payloads()[name])
                if "sequence" in data:
                    data["sequence"] = len(outer.calls)
                if name == "speaker":
                    data["state"] = "waiting_for_speech"
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cls.cert), str(cls.key))
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"https://localhost:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def test_all_requests_are_allowlisted_gets(self):
        self.calls.clear()
        client = pilot.StatusClient(self.url, self.cert, token="TEST_TOKEN")
        data, errors = pilot.read_sample(client)
        self.assertEqual(errors, {})
        self.assertEqual(set(data), set(pilot.ENDPOINTS))
        self.assertTrue(all(method == "GET" for method, path in self.calls))
        self.assertEqual({path for method, path in self.calls}, set(pilot.ENDPOINTS.values()))

    def test_hostname_mismatch_is_rejected(self):
        client = pilot.StatusClient(self.url.replace("localhost", "127.0.0.1"), self.cert)
        with self.assertRaises(urllib.error.URLError):
            client.get("safety")

    def test_full_cli_against_simulated_https(self):
        out = self.root / "reports"
        with contextlib.redirect_stdout(io.StringIO()):
            code = pilot.main(["--duration", "1.1", "--interval", "0.5", "--ca", str(self.cert),
                               "--base-url", self.url, "--output-dir", str(out)])
        self.assertEqual(code, 0)
        summary = next(out.glob("*/report.json"))
        data = json.loads(summary.read_text())
        self.assertEqual(data["result"], "NO_TELEMETRY_ALERTS")
        self.assertGreaterEqual(data["sample_count"], 2)
        self.assertTrue(all(v == "NOT_TESTED" for v in data["manual_checks"].values()))
        raw = summary.with_name("telemetry.jsonl").read_text()
        self.assertNotIn("TEST_TOKEN", raw)
        self.assertNotIn("DO_NOT_LOG", raw)

    def test_interruption_still_writes_report(self):
        out = self.root / "interrupted"
        with patch.object(pilot, "read_sample", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()):
            code = pilot.main(["--duration", "1", "--ca", str(self.cert),
                               "--base-url", self.url, "--output-dir", str(out)])
        self.assertEqual(code, 1)
        data = json.loads(next(out.glob("*/report.json")).read_text())
        self.assertEqual(data["stop_reason"], "interrupted")


if __name__ == "__main__":
    unittest.main()
