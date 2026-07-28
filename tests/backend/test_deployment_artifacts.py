import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentArtifactsTest(unittest.TestCase):
    def test_shell_scripts_parse_and_are_executable(self):
        scripts = sorted((ROOT / "scripts/deploy").glob("*.sh"))
        self.assertEqual({path.name for path in scripts}, {
            "install-local-test.sh", "rollback.sh", "smoke-test.sh",
        })
        for path in scripts:
            self.assertTrue(path.stat().st_mode & 0o111, path)
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_systemd_units_keep_the_api_private_and_data_writable(self):
        api = (ROOT / "deploy/systemd/luminous-api.service").read_text()
        worker = (ROOT / "deploy/systemd/luminous-worker.service").read_text()
        backup = (ROOT / "deploy/systemd/luminous-backup.service").read_text()
        timer = (ROOT / "deploy/systemd/luminous-backup.timer").read_text()
        self.assertIn("--host 127.0.0.1 --port 8000", api)
        for unit in (api, worker, backup):
            self.assertIn("User=luminous", unit)
            self.assertIn("EnvironmentFile=/etc/luminous/luminous.env", unit)
            self.assertIn("NoNewPrivileges=true", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ReadWritePaths=/var/lib/luminous", unit)
        self.assertIn("OnUnitActiveSec=6h", timer)

    def test_tunnel_only_forwards_to_the_loopback_api(self):
        tunnel = (ROOT / "deploy/cloudflared/config.yml").read_text()
        self.assertIn("service: http://127.0.0.1:8000", tunnel)
        self.assertIn("service: http_status:404", tunnel)
        self.assertNotIn("0.0.0.0", tunnel)


if __name__ == "__main__":
    unittest.main()
