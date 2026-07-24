from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.config import PROJECT_ROOT, BackendConfig, load_backend_config
from luminous.runtime.domain.events import make_event, new_event_id
from luminous.runtime.domain.state import CompanionState
from luminous.runtime.domain.time import utc_now_iso
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


@dataclass
class WorkerRunResult:
    job_id: str
    job_type: str
    status: str
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "result": self.result,
        }


class CompanionWorker:
    def __init__(
        self,
        config: BackendConfig,
        runtime: CompanionRuntime | None = None,
        store: CompanionRuntimeStore | None = None,
        clock: callable | None = None,
    ) -> None:
        self.config = config
        self.store = store or CompanionRuntimeStore.for_project(config.project_root)
        self.runtime = runtime or CompanionRuntime(config, store=self.store, clock=clock)
        self.clock = clock or self.runtime.clock

    def tick(self, *, now: datetime | None = None, enqueue_periodic: bool = True, limit: int = 10) -> dict[str, Any]:
        now = now or self.clock()
        if enqueue_periodic:
            self._enqueue_periodic_jobs(now)
        claimed = self.store.claim_due_jobs(now=now, limit=limit)
        results: list[dict[str, Any]] = []
        for job in claimed:
            results.append(self._run_job(job, now=now).to_dict())
        return {
            "now": utc_now_iso(now),
            "claimed": [job["job_id"] for job in claimed],
            "results": results,
            "pending_jobs": [job["job_id"] for job in self.store.read_jobs(status="queued", limit=20)],
        }

    def run_once(self, job_type: str, payload: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or self.clock()
        job_id = self.store.enqueue_job(
            job_type,
            payload or {},
            run_after=now,
            idempotency_key=f"manual:{job_type}:{utc_now_iso(now)}",
        )
        claimed = self.store.claim_due_jobs(now=now, limit=1)
        for job in claimed:
            if job["job_id"] == job_id:
                return self._run_job(job, now=now).to_dict()
        if claimed:
            return self._run_job(claimed[0], now=now).to_dict()
        return {"job_id": job_id, "job_type": job_type, "status": "queued", "result": {}}

    def _enqueue_periodic_jobs(self, now: datetime) -> None:
        schedule = [
            ("state_decay_tick", 60),
            ("proactive_tick", 30),
            ("reminder_due_tick", 1),
            ("routine_due_tick", 15),
            ("activity_expiry_tick", 15),
            ("outbox_delivery", 15),
            ("memory_consolidation", 24 * 60),
            ("memory_reindex", 24 * 60),
        ]
        for job_type, minutes in schedule:
            bucket = int(now.timestamp() // (minutes * 60))
            self.store.enqueue_job(
                job_type,
                {"scheduled": True, "cadence_minutes": minutes},
                run_after=now,
                idempotency_key=f"{job_type}:{bucket}",
            )

    def _run_job(self, job: dict[str, Any], *, now: datetime | None = None) -> WorkerRunResult:
        now = now or self.clock()
        job_id = str(job["job_id"])
        job_type = str(job["job_type"])
        payload = dict(job.get("payload", {}) or {})
        try:
            if job_type == "state_decay_tick":
                result = self._run_state_decay(now=now)
            elif job_type == "proactive_tick":
                result = self.runtime.proactive_tick(send=True, now=now)
            elif job_type == "reminder_due_tick":
                result = self.runtime.process_due_reminders(now=now)
            elif job_type == "routine_due_tick":
                result = self.runtime.process_due_routines(now=now)
            elif job_type == "activity_expiry_tick":
                result = self.runtime.expire_activities(now=now)
            elif job_type == "memory_consolidation":
                result = self.store.consolidate_memories()
            elif job_type == "memory_reindex":
                result = self.store.reindex_memories()
            elif job_type == "outbox_delivery":
                result = self._deliver_outbox(now=now)
            elif job_type == "post_chat_memory_extract":
                result = {"skipped": True, "reason": "handled_inline"}
            else:
                result = {"skipped": True, "reason": f"unknown_job_type:{job_type}"}
            self.store.complete_job(job_id, result)
            self.store.append_event(
                make_event(
                    "worker_job_completed",
                    job_type,
                    {"job": job, "result": result, "payload": payload},
                    trace_id=f"job_{job_id}",
                    now=now,
                )
            )
            return WorkerRunResult(job_id=job_id, job_type=job_type, status="succeeded", result=result)
        except Exception as exc:  # noqa: BLE001 - worker should isolate failures per job.
            self.store.fail_job(job_id, type(exc).__name__ + ": " + str(exc))
            self.store.append_event(
                make_event(
                    "worker_job_failed",
                    job_type,
                    {"job": job, "error": type(exc).__name__, "detail": str(exc)[:400]},
                    trace_id=f"job_{job_id}",
                    now=now,
                )
            )
            return WorkerRunResult(
                job_id=job_id,
                job_type=job_type,
                status="failed",
                result={"error": type(exc).__name__, "detail": str(exc)},
            )

    def _run_state_decay(self, *, now: datetime) -> dict[str, Any]:
        state = self.store.load_state()
        transition = self.runtime.state_engine.apply_time_decay(state, now=now)
        self.store.save_state(state)
        self.store.append_event(
            make_event(
                "state_decay_tick",
                "state_decay",
                {"transition": transition.to_event_payload(), "state": state.to_dict()},
                trace_id=new_event_id("trace"),
                now=now,
            )
        )
        return transition.to_event_payload()

    def _deliver_outbox(self, *, now: datetime) -> dict[str, Any]:
        pending = self.store.read_outbox(status="drafted")
        delivered: list[str] = []
        for item in pending:
            message_id = str(item["message_id"])
            self.store._execute(
                """
                UPDATE outbox
                SET status = 'sent', sent_at = COALESCE(sent_at, ?)
                WHERE message_id = ?
                """,
                (utc_now_iso(now), message_id),
            )
            delivered.append(message_id)
        if delivered:
            self.store.append_event(
                make_event(
                    "outbox_delivery",
                    f"delivered={len(delivered)}",
                    {"message_ids": delivered, "delivered_at": utc_now_iso(now)},
                    trace_id=new_event_id("trace"),
                    now=now,
                )
            )
        return {"delivered": delivered}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the role-play companion background worker.")
    parser.add_argument("--env", type=str, default=str(PROJECT_ROOT / ".env"))
    parser.add_argument("--interval", type=int, default=60, help="seconds between scheduler ticks")
    parser.add_argument("--once", action="store_true", help="Run one scheduler tick and exit")
    parser.add_argument("--job", default="", help="Run a specific job once")
    parser.add_argument("--mock", action="store_true", help="Use deterministic local replies instead of calling an LLM.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_backend_config(env_path=Path(args.env))
    if args.mock:
        config.mock = True
    worker = CompanionWorker(config)
    if args.job:
        result = worker.run_once(args.job)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.once:
        result = worker.tick()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    interval = max(5, min(60, int(args.interval)))
    while True:
        result = worker.tick()
        print(json.dumps(result, ensure_ascii=False))
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
