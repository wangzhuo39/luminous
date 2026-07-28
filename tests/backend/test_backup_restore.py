import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from luminous.runtime.infrastructure.backup import create_backup, restore_backup


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "runtime"
        self.backup_root = self.root / "backups"
        self.data_dir.mkdir()
        for name, value in (("runtime.sqlite3", "conversation-before"), ("life_flow.sqlite3", "task-before")):
            with sqlite3.connect(self.data_dir / name) as connection:
                connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
                connection.execute("INSERT INTO evidence VALUES (?)", (value,))

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

        restore_dir = self.root / "restored"
        restored = restore_backup(backup, restore_dir)
        self.assertEqual(len(restored), 2)
        with sqlite3.connect(restore_dir / "runtime.sqlite3") as connection:
            self.assertEqual(connection.execute("SELECT value FROM evidence").fetchone()[0], "conversation-before")
        with sqlite3.connect(restore_dir / "life_flow.sqlite3") as connection:
            self.assertEqual(connection.execute("SELECT value FROM evidence").fetchone()[0], "task-before")

    def test_restore_rejects_a_nonempty_target(self):
        backup = create_backup(self.data_dir, self.backup_root)
        target = self.root / "nonempty"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            restore_backup(backup, target)


if __name__ == "__main__":
    unittest.main()
