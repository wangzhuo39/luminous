from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from luminous.runtime.config import PROJECT_ROOT, load_backend_config


def create_backup(data_dir: Path, backup_root: Path, *, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_root.chmod(0o700)
    name = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_root / name
    if destination.exists():
        name = f"{name}-{uuid.uuid4().hex[:8]}"
        destination = backup_root / name
    partial = backup_root / f".{name}.partial-{uuid.uuid4().hex[:8]}"
    partial.mkdir(mode=0o700)
    databases = sorted(data_dir.glob("*.sqlite3"))
    if not databases:
        shutil.rmtree(partial)
        raise FileNotFoundError(f"no SQLite databases found in {data_dir}")
    files: list[dict[str, object]] = []
    try:
        for source_path in databases:
            target_path = partial / source_path.name
            with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
                source.backup(target)
            _assert_integrity(target_path)
            files.append({
                "name": target_path.name,
                "size": target_path.stat().st_size,
                "sha256": _sha256(target_path),
            })
        (partial / "manifest.json").write_text(
            json.dumps({"created_at": now.isoformat(), "files": files}, indent=2) + "\n",
            encoding="utf-8",
        )
        partial.rename(destination)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    prune_backups(backup_root)
    return destination


def restore_backup(backup_dir: Path, data_dir: Path, *, require_empty: bool = True) -> list[Path]:
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    if not isinstance(files, list) or not files:
        raise ValueError("backup manifest contains no databases")
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = list(data_dir.iterdir())
    if require_empty and existing:
        raise ValueError("restore target must be empty")
    restored: list[Path] = []
    for record in files:
        name = Path(str(record["name"])).name
        source_path = backup_dir / name
        if _sha256(source_path) != record.get("sha256"):
            raise ValueError(f"backup checksum mismatch: {name}")
        _assert_integrity(source_path)
        target_path = data_dir / name
        with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
            source.backup(target)
        _assert_integrity(target_path)
        restored.append(target_path)
    return restored


def prune_backups(backup_root: Path) -> None:
    backups: list[tuple[Path, datetime]] = []
    for path in backup_root.iterdir():
        if not path.is_dir() or path.name.startswith(".") or not (path / "manifest.json").exists():
            continue
        try:
            created = datetime.fromisoformat(json.loads((path / "manifest.json").read_text())["created_at"])
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        backups.append((path, created))
    backups.sort(key=lambda item: item[1], reverse=True)
    keep: set[Path] = set()
    daily: set[str] = set()
    weekly: set[tuple[int, int]] = set()
    for path, created in backups:
        day = created.date().isoformat()
        week = (created.isocalendar().year, created.isocalendar().week)
        if day not in daily and len(daily) < 7:
            daily.add(day)
            keep.add(path)
        elif week not in weekly and len(weekly) < 4:
            weekly.add(week)
            keep.add(path)
    for path, _ in backups:
        if path not in keep:
            shutil.rmtree(path)


def _assert_integrity(path: Path) -> None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    if result != "ok":
        raise ValueError(f"SQLite integrity check failed for {path.name}: {result}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or restore verified Luminous SQLite backups.")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--env", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--backup-root", type=Path, default=Path("/var/lib/luminous/backups"))
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--target", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_backend_config(env_path=args.env)
    if args.action == "backup":
        print(create_backup(config.runtime_data_dir, args.backup_root))
        return 0
    if args.backup is None:
        raise SystemExit("--backup is required for restore")
    target = args.target or config.runtime_data_dir
    for path in restore_backup(args.backup, target):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
