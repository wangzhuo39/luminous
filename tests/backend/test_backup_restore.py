import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from luminous.runtime.infrastructure.backup import create_backup, restore_backup
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "runtime"
        self.backup_root = self.root / "backups"
        self.data_dir.mkdir()
        store = CompanionRuntimeStore(self.data_dir)
        store.upsert_notification_device(token="sensitive-device-token", installation_id="phone-1")
        store.enqueue_job("outbox_delivery", {"scheduled": True}, idempotency_key="backup-job")
        store.append_outbox({
            "message_id": "backup-outbox", "draft_text": "backup message",
            "status": "queued", "idempotency_key": "backup-outbox",
        })
        with closing(sqlite3.connect(self.data_dir / "runtime.sqlite3")) as connection:
            connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
            connection.execute("INSERT INTO evidence VALUES (?)", ("conversation-before",))
            connection.commit()
        with closing(sqlite3.connect(self.data_dir / "life_flow.sqlite3")) as connection:
            connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
            connection.execute("INSERT INTO evidence VALUES (?)", ("task-before",))
            connection.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_online_backup_restores_both_databases_into_an_empty_directory(self):
        backup = create_backup(
            self.data_dir,
            self.backup_root,
            now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )
        manifest = json.loads((backup / "manifest.json").read_text())
        self.assertEqual({item["name"] for item in manifest["files"]}, {"runtime.sqlite3", "life_flow.sqlite3"})
        self.assertEqual(self.backup_root.stat().st_mode & 0o777, 0o700)
        for item in manifest["files"]:
            self.assertEqual((backup / item["name"]).stat().st_mode & 0o777, 0o600)

        restore_dir = self.root / "restored"
        restored = restore_backup(backup, restore_dir)
        self.assertEqual(len(restored), 2)
        with closing(sqlite3.connect(restore_dir / "runtime.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT value FROM evidence").fetchone()[0], "conversation-before")
            self.assertEqual(
                connection.execute("SELECT token FROM notification_devices").fetchone()[0],
                "sensitive-device-token",
            )
            self.assertEqual(connection.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)
            outbox_columns = {row[1] for row in connection.execute("PRAGMA table_info(outbox)")}
            self.assertIn("delivery_lock_token", outbox_columns)
        with closing(sqlite3.connect(restore_dir / "life_flow.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT value FROM evidence").fetchone()[0], "task-before")
        for path in restored:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_restore_rejects_a_nonempty_target(self):
        backup = create_backup(self.data_dir, self.backup_root)
        target = self.root / "nonempty"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            restore_backup(backup, target)

    def test_checksum_failure_leaves_empty_target_untouched(self):
        backup = create_backup(self.data_dir, self.backup_root)
        manifest = json.loads((backup / "manifest.json").read_text())
        second = backup / manifest["files"][-1]["name"]
        second.write_bytes(second.read_bytes() + b"tampered")
        target = self.root / "empty-target"
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            restore_backup(backup, target)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(list(self.root.glob(".empty-target.restore-*")), [])


if __name__ == "__main__":
    unittest.main()
