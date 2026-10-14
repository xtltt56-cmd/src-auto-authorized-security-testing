import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_health(port, process):
    url = "http://127.0.0.1:{}/health".format(port)
    for _ in range(80):
        if process.poll() is not None:
            raise AssertionError("dashboard API exited before becoming healthy")
        try:
            with urlopen(url, timeout=0.5) as response:
                if json.loads(response.read().decode("utf-8")).get("status") == "ok":
                    return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("dashboard API did not become healthy")


class DashboardProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows listener parser')
    def test_listener_parser_requires_exact_loopback_state_port_and_owner(self):
        helper = str(ROOT / 'tools/dashboard_process.ps1').replace("'", "''")
        script = ". '{}'\n".format(helper) + """
$rows = @('TCP 127.0.0.1:4174 0.0.0.0:0 LISTENING 1234',
          'TCP 0.0.0.0:4174 0.0.0.0:0 LISTENING 999',
          'TCP 127.0.0.1:41740 0.0.0.0:0 LISTENING 999',
          'TCP 127.0.0.1:4174 127.0.0.1:9999 ESTABLISHED 999')
$item = Convert-DashboardTcpListeners -Rows $rows -Port 4174
if($item.OwningProcess -ne 1234) { throw 'Wrong listener selected' }
if(Convert-DashboardTcpListeners -Rows $rows -Port 1111) { throw 'Foreign port selected' }
try {
    Convert-DashboardTcpListeners -Rows @('TCP 127.0.0.1:4174 0.0.0.0:0 LISTENING 1', 'TCP 127.0.0.1:4174 0.0.0.0:0 LISTENING 2') -Port 4174
    exit 9
} catch { exit 0 }
"""
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], cwd=str(ROOT),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode('utf-8', errors='replace'))

    def start_api(self, port, origin):
        environment = os.environ.copy()
        environment["SRC_AUTO_REMOTE_AI_CONSENT"] = "disabled"
        environment["PYTHONIOENCODING"] = "cp1252"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src_auto.dashboard_server",
                "--port",
                str(port),
                "--allowed-origin",
                origin,
            ],
            cwd=str(ROOT),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_health(port, process)
        return process

    def test_custom_origin_is_enforced_by_a_real_api_process(self):
        port = free_port()
        origin = "http://127.0.0.1:{}".format(free_port())
        process = self.start_api(port, origin)
        try:
            request = Request(
                "http://127.0.0.1:{}/api/session".format(port),
                headers={"Origin": origin},
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["token"])

            denied = Request(
                "http://127.0.0.1:{}/api/session".format(port),
                headers={"Origin": "http://127.0.0.1:4173"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(denied, timeout=3)
            self.assertEqual(raised.exception.code, 403)
        finally:
            process.terminate()
            process.wait(timeout=5)

    @unittest.skipUnless(os.name == "nt", "secure Dashboard stop helper is Windows-only")
    def test_stop_helper_terminates_only_the_verified_dashboard_api(self):
        port = free_port()
        origin = "http://127.0.0.1:{}".format(free_port())
        process = self.start_api(port, origin)
        try:
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "tools" / "stop_dashboard.ps1"),
                    "-ApiPort",
                    str(port),
                    "-WebPort",
                    origin.rsplit(":", 1)[1],
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
