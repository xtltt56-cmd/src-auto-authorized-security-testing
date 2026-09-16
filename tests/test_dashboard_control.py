import threading
import unittest
from concurrent.futures import Future
from dataclasses import dataclass

from src_auto.dashboard_control import DashboardControlService


@dataclass(frozen=True)
class FakeSpec:
    lab_id: str
    host_port: int
    health_url: str


class FakeManager:
    def __init__(self):
        self.specs = {
            "juice-shop": FakeSpec("juice-shop", 3000, "http://127.0.0.1:3000/"),
            "dvwa": FakeSpec("dvwa", 8081, "http://127.0.0.1:8081/login.php"),
        }
        self.states = {lab_id: "NOT_FOUND" for lab_id in self.specs}
        self.calls = []
        self.release = threading.Event()

    def spec(self, lab_id):
        if lab_id not in self.specs:
            raise ValueError("unknown_lab_id")
        return self.specs[lab_id]

    def status(self, lab_id):
        spec = self.spec(lab_id)
        return {
            "lab_id": lab_id,
            "status": self.states[lab_id],
            "host_port": spec.host_port,
            "health_url": spec.health_url,
            "network_contact": False,
        }

    def operate(self, action, lab_id, wait=True, cancel_event=None):
        self.calls.append((action, lab_id, wait))
        self.release.wait(2)
        self.states[lab_id] = "READY" if action in ("start", "reset") else "STOPPED"
        return {"status": self.states[lab_id], "lab_id": lab_id, "network_contact": action in ("start", "reset")}


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - asserted through service state
            future.set_exception(exc)
        return future


class DashboardControlServiceTests(unittest.TestCase):
    def test_detection_updates_real_task_counters_and_report_link(self):
        manager = FakeManager()
        manager.states["juice-shop"] = "READY"

        def detection(lab_id, cancel_event, progress):
            progress("表面发现", 45, {"endpoints": 7, "api": 2, "candidates": 0, "blocked": 0, "errors": 0}, "已完成回环表面发现")
            return {
                "status": "completed", "runId": "run-123", "reportId": "reports/run-123.md",
                "candidateCount": 2, "endpointCount": 7, "apiCount": 2, "blockedCount": 0,
                "networkContact": "loopback",
            }

        service = DashboardControlService(
            manager, executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"),
            detection_runner=detection,
        )

        accepted = service.submit_detection("juice-shop")
        snapshot = service.snapshot()
        task = next(item for item in snapshot["tasks"] if item["id"] == "run-lab-juice-shop")
        lab = next(item for item in snapshot["labs"] if item["id"] == "juice-shop")

        self.assertTrue(accepted["accepted"])
        self.assertEqual(task["state"], "completed")
        self.assertEqual(task["stage"], "检测完成")
        self.assertEqual(task["counters"]["candidates"], 2)
        self.assertEqual(lab["candidates"], 2)
        self.assertEqual(lab["reportId"], "reports/run-123.md")
        self.assertEqual(lab["lastRunId"], "run-123")
        self.assertEqual(lab["detectionOperation"], "completed")
        self.assertTrue(any(event["stage"] == "表面发现" for event in snapshot["events"]))

    def test_detection_refuses_a_stopped_lab_before_network_contact(self):
        called = []
        service = DashboardControlService(
            FakeManager(), executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"),
            detection_runner=lambda *args: called.append(args),
        )

        with self.assertRaisesRegex(RuntimeError, "lab_not_ready"):
            service.submit_detection("juice-shop")
        self.assertEqual(called, [])

    def test_detection_can_be_cancelled_at_a_safe_checkpoint(self):
        manager = FakeManager()
        manager.states["juice-shop"] = "READY"
        started = threading.Event()

        def detection(_lab_id, cancel_event, progress):
            progress("候选检测", 60, {"endpoints": 1, "api": 0, "candidates": 0, "blocked": 0, "errors": 0}, "等待停止检查点")
            started.set()
            cancel_event.wait(2)
            return {"status": "cancelled", "networkContact": "loopback"}

        service = DashboardControlService(manager, dependency_check=lambda: (True, "Docker 可用"), detection_runner=detection)
        try:
            service.submit_detection("juice-shop")
            self.assertTrue(started.wait(1))
            service.cancel_detection("juice-shop")
            for _ in range(20):
                task = next(item for item in service.snapshot()["tasks"] if item["id"] == "run-lab-juice-shop")
                if task["state"] == "cancelled":
                    break
                threading.Event().wait(0.05)
            self.assertEqual(task["state"], "cancelled")
        finally:
            service.close()

    def test_missing_docker_is_reported_as_unavailable_not_failed_lab(self):
        service = DashboardControlService(
            FakeManager(),
            executor=ImmediateExecutor(),
            dependency_check=lambda: (False, "Docker Desktop 尚未就绪，请先启动 Docker Desktop"),
        )

        snapshot = service.snapshot()

        self.assertFalse(snapshot['dependency']['dockerReady'])
        self.assertTrue(all(lab['health'] == 'unavailable' for lab in snapshot['labs']))
        self.assertTrue(all(lab['stage'] == 'Docker 未就绪' for lab in snapshot['labs']))
        self.assertTrue(all('Docker Desktop' in lab['message'] for lab in snapshot['labs']))
        self.assertTrue(all(task['state'] == 'blocked' for task in snapshot['tasks']))

    def test_stop_replaces_queued_start_without_starting_container(self):
        class Queue:
            def __init__(self): self.jobs = []
            def submit(self, fn, *args): self.jobs.append((fn, args))
        manager = FakeManager()
        manager.release.set()
        queue = Queue()
        service = DashboardControlService(manager, executor=queue)
        service.submit('dvwa', 'start')
        result = service.submit_all('stop')
        self.assertEqual(len(result['operations']), 2)
        for fn, args in queue.jobs: fn(*args)
        self.assertNotIn(('start', 'dvwa', True), manager.calls)
        self.assertIn(('stop', 'dvwa', False), manager.calls)

    def test_stop_cancels_a_running_start_before_reporting_stopped(self):
        class CancellableManager(FakeManager):
            def __init__(self):
                super().__init__(); self.started = threading.Event(); self.stopped = threading.Event()
            def operate(self, action, lab_id, wait=True, cancel_event=None):
                self.calls.append((action, lab_id, wait))
                if action == 'start':
                    self.started.set()
                    self.assert_cancelled = cancel_event.wait(2)
                    return {'status': 'CANCELLED', 'lab_id': lab_id, 'network_contact': False}
                self.states[lab_id] = 'STOPPED'; self.stopped.set()
                return {'status': 'STOPPED', 'lab_id': lab_id, 'network_contact': False}
        manager = CancellableManager()
        service = DashboardControlService(manager, dependency_check=lambda: (True, 'Docker 可用'))
        try:
            service.submit('juice-shop', 'start')
            self.assertTrue(manager.started.wait(1))
            service.submit('juice-shop', 'stop')
            self.assertTrue(manager.stopped.wait(2))
            self.assertTrue(manager.assert_cancelled)
            self.assertEqual(manager.calls, [('start', 'juice-shop', True), ('stop', 'juice-shop', False)])
            task = next(item for item in service.snapshot()['tasks'] if item['id'] == 'run-lab-juice-shop')
            self.assertEqual(task['state'], 'idle')
        finally:
            service.close()

    def test_empty_snapshot_is_idle_with_zero_elapsed_time(self):
        manager = FakeManager()
        service = DashboardControlService(manager, executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"))
        snapshot = service.snapshot()
        self.assertEqual(snapshot["source"], "loopback")
        self.assertTrue(snapshot["dependency"]["dockerReady"])
        self.assertTrue(all(task["state"] == "idle" for task in snapshot["tasks"]))
        self.assertTrue(all(task["elapsedSeconds"] == 0 for task in snapshot["tasks"]))
        self.assertEqual([lab["id"] for lab in snapshot["labs"]], ["juice-shop", "dvwa"])
        self.assertTrue(all(lab["health"] == "stopped" for lab in snapshot["labs"]))

    def test_ready_status_maps_to_completed_and_loopback(self):
        manager = FakeManager()
        manager.states["juice-shop"] = "READY"
        service = DashboardControlService(manager, executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"))
        snapshot = service.snapshot()
        task = next(item for item in snapshot["tasks"] if item["id"] == "run-lab-juice-shop")
        lab = next(item for item in snapshot["labs"] if item["id"] == "juice-shop")
        self.assertEqual(task["state"], "completed")
        self.assertEqual(task["networkContact"], "loopback")
        self.assertEqual(lab["health"], "healthy")
        self.assertEqual(lab["openUrl"], "http://127.0.0.1:3000/")

    def test_rejects_unknown_actions_and_labs(self):
        service = DashboardControlService(FakeManager(), executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"))
        with self.assertRaisesRegex(ValueError, "unsupported_dashboard_action"):
            service.submit("juice-shop", "shell")
        with self.assertRaisesRegex(ValueError, "unknown_lab_id"):
            service.submit("../outside", "start")

    def test_duplicate_operation_is_rejected_while_running(self):
        manager = FakeManager()
        service = DashboardControlService(manager, dependency_check=lambda: (True, "Docker 可用"))
        try:
            service.submit("juice-shop", "start")
            with self.assertRaisesRegex(RuntimeError, "lab_operation_in_progress"):
                service.submit("juice-shop", "reset")
        finally:
            manager.release.set()
            service.close()

    def test_operation_records_redacted_event_and_updates_state(self):
        manager = FakeManager()
        manager.release.set()
        service = DashboardControlService(manager, executor=ImmediateExecutor(), dependency_check=lambda: (True, "Docker 可用"))
        service.submit("dvwa", "start")
        snapshot = service.snapshot()
        self.assertEqual(manager.calls, [("start", "dvwa", True)])
        task = next(item for item in snapshot["tasks"] if item["id"] == "run-lab-dvwa")
        self.assertEqual(task["state"], "completed")
        self.assertTrue(snapshot["events"])
        self.assertTrue(all(event["redacted"] for event in snapshot["events"]))
        self.assertNotIn("command", str(snapshot["events"]))


if __name__ == "__main__":
    unittest.main()
