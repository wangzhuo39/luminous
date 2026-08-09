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
        voice_agent = (ROOT / "deploy/systemd/luminous-livekit-agent.service").read_text()
        backup = (ROOT / "deploy/systemd/luminous-backup.service").read_text()
        timer = (ROOT / "deploy/systemd/luminous-backup.timer").read_text()
        self.assertIn("--host 127.0.0.1 --port 8000", api)
        for unit in (api, worker, voice_agent, backup):
            self.assertIn("User=luminous", unit)
            self.assertIn("EnvironmentFile=/etc/luminous/luminous.env", unit)
            self.assertIn("NoNewPrivileges=true", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ReadWritePaths=/var/lib/luminous", unit)
        self.assertIn("OnUnitActiveSec=6h", timer)
        self.assertIn("luminous-livekit-agent start", voice_agent)
        self.assertIn("Requires=luminous-api.service", voice_agent)

    def test_tunnel_only_forwards_to_the_loopback_api(self):
        tunnel = (ROOT / "deploy/cloudflared/config.yml").read_text()
        self.assertIn("service: http://127.0.0.1:8000", tunnel)
        self.assertIn("service: http_status:404", tunnel)
        self.assertNotIn("0.0.0.0", tunnel)

    def test_user_services_are_restartable_without_embedding_tunnel_token(self):
        unit_dir = ROOT / "deploy/systemd/user"
        api = (unit_dir / "luminous-api.service").read_text()
        worker = (unit_dir / "luminous-worker.service").read_text()
        voice_agent = (unit_dir / "luminous-livekit-agent.service").read_text()
        livekit_server = (unit_dir / "luminous-livekit-server.service").read_text()
        tunnel = (unit_dir / "luminous-cloudflared.service").read_text()
        for unit in (api, worker, voice_agent, livekit_server, tunnel):
            self.assertIn("Restart=on-failure", unit)
            self.assertIn("WantedBy=default.target", unit)
            self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("--host 127.0.0.1 --port 8000", api)
        self.assertIn("luminous-livekit-agent start", voice_agent)
        self.assertIn("livekit-server --config", livekit_server)
        self.assertIn("--key-file /home/wz/.config/luminous/livekit.keys", livekit_server)
        self.assertIn("--protocol http2", tunnel)
        self.assertIn("--token-file /home/wz/.cloudflared/luminous.token", tunnel)
        self.assertNotIn("--token ", tunnel)

    def test_android_manifest_disables_backup_and_cleartext_with_restricted_deep_link(self):
        manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text()
        env_example = (ROOT / ".env.example").read_text()
        self.assertIn('android:allowBackup="false"', manifest)
        self.assertIn('android:fullBackupContent="false"', manifest)
        self.assertIn('android:usesCleartextTraffic="false"', manifest)
        self.assertIn('android:scheme="havilume" android:host="app"', manifest)
        self.assertNotIn('android:scheme="http"', manifest)
        self.assertIn("https://localhost", env_example)

    def test_android_build_has_explicit_upgradeable_version_inputs(self):
        gradle = (ROOT / "android/app/build.gradle").read_text()
        script = (ROOT / "scripts/build-android-debug.mjs").read_text()
        release_script = (ROOT / "scripts/build-android-release.mjs").read_text()
        self.assertIn("luminousVersionCode", gradle)
        self.assertIn("luminousVersionName", gradle)
        self.assertIn("LUMINOUS_ANDROID_VERSION_CODE", script)
        self.assertIn("LUMINOUS_ANDROID_VERSION_NAME", script)
        self.assertIn("System.getenv('LUMINOUS_ANDROID_KEYSTORE')", gradle)
        self.assertIn("storePassword luminousReleaseStorePassword", gradle)
        self.assertIn("keyPassword luminousReleaseKeyPassword", gradle)
        self.assertNotIn("storePassword '", gradle)
        self.assertNotIn("keyPassword '", gradle)
        self.assertIn("apksigner", release_script)
        self.assertIn("LUMINOUS_ANDROID_KEYSTORE", release_script)

    def test_wsl_livekit_firewall_is_port_scoped(self):
        script = (ROOT / "scripts/deploy/configure-livekit-wsl-firewall.ps1").read_text()
        self.assertIn("#Requires -RunAsAdministrator", script)
        self.assertIn("-LocalPorts 7880, 7881", script)
        self.assertIn("-LocalPorts 7882", script)
        self.assertIn("-Protocol TCP", script)
        self.assertIn("-Protocol UDP", script)
        self.assertNotIn("DefaultInboundAction Allow", script)


if __name__ == "__main__":
    unittest.main()
