import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src_auto.local_labs import (
    LabSpec,
    LocalLabManager,
    build_compose_command,
    load_lab_specs,
    parse_lab_status,
    safe_lab_id,
)
from src_auto.cli import build_parser


class LocalLabSpecTests(unittest.TestCase):
    def test_loads_only_pinned_loopback_labs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "labs.json"
            path.write_text(
                json.dumps(
                    {
                        "labs": [
                            {
                                "lab_id": "juice-shop",
                                "service": "juice-shop",
                                "image": "bkimminich/juice-shop",
                                "digest": "sha256:" + "a" * 64,
                                "container_port": 3000,
                                "host": "127.0.0.1",
                                "host_port": 3000,
                                "health_url": "http://127.0.0.1:3000/",
                            },
                            {
                                "lab_id": "dvwa",
                                "service": "dvwa",
                                "image": "ghcr.io/digininja/dvwa",
                                "digest": "sha256:" + "b" * 64,
                                "container_port": 80,
                                "host": "127.0.0.1",
                                "host_port": 8081,
                                "health_url": "http://127.0.0.1:8081/login.php",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            specs = load_lab_specs(path)
        self.assertEqual([item.lab_id for item in specs], ["juice-shop", "dvwa"])
        self.assertEqual(specs[0].pinned_image, "bkimminich/juice-shop@sha256:" + "a" * 64)
        self.assertTrue(all(item.is_loopback_only for item in specs))

    def test_rejects_unpinned_or_non_loopback_spec(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "labs.json"
            path.write_text(
                json.dumps(
                    {
                        "labs": [
                            {
                                "lab_id": "bad",
                                "service": "bad",
                                "image": "example/bad:latest",
                                "digest": "",
                                "container_port": 80,
                                "host": "0.0.0.0",
                                "host_port": 8080,
                                "health_url": "http://0.0.0.0:8080/",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_lab_specs(path)

    def test_compose_commands_are_fixed_to_known_service(self):
        spec = LabSpec(
            lab_id="dvwa",
            service="dvwa",
            image="ghcr.io/digininja/dvwa",
            digest="sha256:" + "b" * 64,
            container_port=80,
            host="127.0.0.1",
            host_port=8081,
            health_url="http://127.0.0.1:8081/login.php",
        )
        command = build_compose_command(Path("D:/project/docker-compose.local-labs.yml"), spec, "up")
        self.assertEqual(command[:4], ["docker", "compose", "-f", str(Path("D:/project/docker-compose.local-labs.yml").resolve())])
        self.assertEqual(command[-3:], ["up", "-d", "dvwa"])
        self.assertNotIn("--privileged", command)

    def test_status_parser_never_turns_missing_health_into_ready(self):
        spec = LabSpec(
            lab_id="juice-shop",
            service="juice-shop",
            image="bkimminich/juice-shop",
            digest="sha256:" + "a" * 64,
            container_port=3000,
            host="127.0.0.1",
            host_port=3000,
            health_url="http://127.0.0.1:3000/",
        )
        self.assertEqual(parse_lab_status(spec, {"State": "running", "Health": "starting"})["status"], "STARTING")
        self.assertEqual(parse_lab_status(spec, {"State": "running", "Health": "healthy"})["status"], "READY")
        self.assertEqual(parse_lab_status(spec, {"State": "exited", "Health": "none"})["status"], "STOPPED")

    def test_lab_ids_are_strict(self):
        self.assertEqual(safe_lab_id("dvwa"), "dvwa")
        with self.assertRaises(ValueError):
            safe_lab_id("../dvwa")

    def test_manager_rejects_unknown_service_without_running_docker(self):
        with tempfile.TemporaryDirectory() as temp:
            inventory = Path(temp) / "labs.json"
            inventory.write_text(json.dumps({"labs": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                LocalLabManager(Path(temp), inventory, Path(temp) / "compose.yml")

    def test_manager_status_uses_inspect_and_requires_healthy_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "labs.json"
            inventory.write_text(
                json.dumps(
                    {
                        "labs": [
                            {
                                "lab_id": "dvwa",
                                "service": "dvwa",
                                "image": "ghcr.io/digininja/dvwa",
                                "digest": "sha256:" + "b" * 64,
                                "container_port": 80,
                                "host": "127.0.0.1",
                                "host_port": 8081,
                                "health_url": "http://127.0.0.1:8081/login.php",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manager = LocalLabManager(root, inventory, root / "compose.yml")
            result = manager.status("dvwa", inspect_fn=lambda _: {"State": "running", "Health": "starting"})
        self.assertEqual(result["status"], "STARTING")
        self.assertFalse(result["network_contact"])

    def test_manager_start_creates_missing_container_with_compose_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "labs.json"
            inventory.write_text(
                json.dumps(
                    {
                        "labs": [
                            {
                                "lab_id": "vampi",
                                "service": "vampi",
                                "image": "erev0s/vampi",
                                "digest": "sha256:" + "c" * 64,
                                "container_port": 5000,
                                "host": "127.0.0.1",
                                "host_port": 8083,
                                "health_url": "http://127.0.0.1:8083/ui/",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manager = LocalLabManager(root, inventory, root / "compose.yml")
            with patch.object(manager, "_run", return_value={"status": "COMPLETED", "returncode": 0}) as run_mock:
                result = manager.operate("start", "vampi", wait=False)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[-3:], ["up", "-d", "vampi"])
        self.assertEqual(result["action"], "start")

    def test_cli_exposes_local_lab_lifecycle_without_external_mode(self):
        args = build_parser().parse_args(["local-labs", "status", "--lab", "dvwa", "--json"])
        self.assertEqual(args.command, "local-labs")
        self.assertEqual(args.action, "status")
        self.assertEqual(args.lab, "dvwa")
        self.assertTrue(args.json_output)

    def test_cli_exposes_local_validation_with_bounded_rounds(self):
        args = build_parser().parse_args(["local-validation", "--local-only", "--repeat-rounds", "1", "--lab", "dvwa", "--json"])
        self.assertEqual(args.command, "local-validation")
        self.assertTrue(args.local_only)
        self.assertEqual(args.repeat_rounds, 1)
        self.assertEqual(args.labs, ["dvwa"])

    def test_pinned_compose_uses_juice_shop_node_path_for_healthcheck(self):
        compose = (Path(__file__).parents[1] / "docker-compose.local-labs.yml").read_text(encoding="utf-8")
        self.assertIn("/nodejs/bin/node", compose)
        self.assertNotIn("\n        - node\n", compose)

    def test_webgoat_is_pinned_and_loopback_only(self):
        root = Path(__file__).parents[1]
        specs = {item.lab_id: item for item in load_lab_specs(root / "config" / "labs" / "local_labs.json")}
        self.assertIn("webgoat", specs)
        webgoat = specs["webgoat"]
        self.assertEqual(webgoat.host, "127.0.0.1")
        self.assertEqual(webgoat.host_port, 8082)
        self.assertEqual(webgoat.container_port, 8080)
        self.assertEqual(webgoat.digest, "sha256:3101bd9e7bcfe122d7ef91e690ef3720de36cc4e86b3d06763a1ddf2e2751a4b")
        self.assertEqual(webgoat.health_url, "http://127.0.0.1:8082/WebGoat/actuator/health")
        compose = (root / "docker-compose.local-labs.yml").read_text(encoding="utf-8")
        self.assertIn("webgoat/webgoat@sha256:3101bd9e7bcfe122d7ef91e690ef3720de36cc4e86b3d06763a1ddf2e2751a4b", compose)
        self.assertIn("127.0.0.1:8082:8080", compose)
        self.assertIn("wget -q -O - http://127.0.0.1:8080/WebGoat/actuator/health", compose)
        self.assertNotIn("curl -fsS http://127.0.0.1:8080/WebGoat/actuator/health", compose)

    def test_dvwa_compose_has_pinned_mariadb_dependency(self):
        compose = (Path(__file__).parents[1] / "docker-compose.local-labs.yml").read_text(encoding="utf-8")
        self.assertIn("image: mariadb@sha256:8020e05c4c498d06c87f0a1db010eb79bd6f8fb30e9b763d4690c34ce1e61008", compose)
        self.assertIn("DB_SERVER=db", compose)
        self.assertIn("condition: service_healthy", compose)
        self.assertIn("dvwa-db-data:/var/lib/mysql", compose)

    def test_vampi_business_api_is_pinned_loopback_and_has_guided_ui(self):
        root = Path(__file__).parents[1]
        specs = {item.lab_id: item for item in load_lab_specs(root / "config" / "labs" / "local_labs.json")}
        self.assertIn("vampi", specs)
        vampi = specs["vampi"]
        self.assertEqual(vampi.host, "127.0.0.1")
        self.assertEqual(vampi.host_port, 8083)
        self.assertEqual(vampi.container_port, 5000)
        self.assertEqual(vampi.digest, "sha256:0a5a224b6e14ae7da6a6ea265178ff71286ff903aec74adee98f660bb0e4ca12")
        self.assertEqual(vampi.health_url, "http://127.0.0.1:8083/ui/")
        compose = (root / "docker-compose.local-labs.yml").read_text(encoding="utf-8")
        self.assertIn("erev0s/vampi@sha256:0a5a224b6e14ae7da6a6ea265178ff71286ff903aec74adee98f660bb0e4ca12", compose)
        self.assertIn('127.0.0.1:8083:5000', compose)
        self.assertIn("vulnerable=1", compose)


if __name__ == "__main__":
    unittest.main()
