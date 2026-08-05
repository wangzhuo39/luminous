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
from luminous.runtime.domain.events import ProactiveSignal, make_event, new_event_id
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
        self.store = store or CompanionRuntimeStore(config.runtime_data_dir)
        self.runtime = runtime or CompanionRuntime(config, store=self.store, clock=clock)
        self.clock = clock or self.runtime.clock

    def tick(self, *, now: datetime | None = None, enqueue_periodic: bool = True, limit: int = 10) -> dict[str, Any]:
        now = now or self.clock()
        try:
            if enqueue_periodic:
                self._enqueue_periodic_jobs(now)
            claimed = self.store.claim_due_jobs(now=now, limit=limit)
            results: list[dict[str, Any]] = []
            for job in claimed:
                results.append(self._run_job(job, now=now).to_dict())
            result = {
                "now": utc_now_iso(now),
                "claimed": [job["job_id"] for job in claimed],
                "results": results,
                "pending_jobs": [job["job_id"] for job in self.store.read_jobs(status="queued", limit=20)],
            }
            self.store.record_runtime_health("worker", success=True, now=now)
            return result
        except Exception as exc:
            try:
                self.store.record_runtime_health(
                    "worker",
                    success=False,
                    error_code=type(exc).__name__,
                    now=now,
                )
            except Exception:
                pass
            raise

    def run_once(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        now = now or self.clock()
        job_id = self.store.enqueue_job(
            job_type,
            payload or {},
            run_after=now,
            idempotency_key=idempotency_key or f"manual:{job_type}:{utc_now_iso(now)}",
        )
        claimed = self.store.claim_job(job_id, now=now)
        if claimed is not None:
            return self._run_job(claimed, now=now).to_dict()
        return {"job_id": job_id, "job_type": job_type, "status": "queued", "result": {}}

    def _enqueue_periodic_jobs(self, now: datetime) -> None:
        schedule = [
            ("state_decay_tick", 60),
            ("proactive_tick", 30),
            ("reminder_due_tick", 1),
            ("routine_due_tick", 15),
            ("activity_expiry_tick", 15),
            ("life_flow_effect_delivery", 1),
            ("life_flow_audit_delivery", 1),
            ("outbox_delivery", 1),
            ("runtime_maintenance", 24 * 60),
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
        lease_token = str(job.get("_job_lock_token", ""))
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
            elif job_type == "life_flow_effect_delivery":
                result = self.runtime.life_flow.flush_effect_outbox()
            elif job_type == "life_flow_audit_delivery":
                result = self.runtime.life_flow.flush_audit_outbox()
            elif job_type == "memory_consolidation":
                result = self.store.consolidate_memories()
            elif job_type == "memory_reindex":
                result = self.store.reindex_memories()
            elif job_type == "outbox_delivery":
                result = self._deliver_outbox(now=now)
            elif job_type == "runtime_maintenance":
                result = {
                    "runtime": self.store.prune_runtime_records(now=now),
                    "life_flow": self.runtime.life_flow.store.prune_delivered_outboxes(
                        before=now - timedelta(days=7),
                    ),
                }
            elif job_type == "post_chat_memory_extract":
                result = {"skipped": True, "reason": "handled_inline"}
            else:
                result = {"skipped": True, "reason": f"unknown_job_type:{job_type}"}
            with self.store.atomic():
                completed = self.store.complete_job(job_id, result, lease_token=lease_token)
                if not completed:
                    return WorkerRunResult(
                        job_id=job_id, job_type=job_type, status="lease_lost",
                        result={"error": "job_lease_lost"},
                    )
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
            retrying = self.store.fail_job(
                job_id, type(exc).__name__ + ": " + str(exc), lease_token=lease_token,
            )
            if retrying is None:
                return WorkerRunResult(
                    job_id=job_id, job_type=job_type, status="lease_lost",
                    result={"error": "job_lease_lost", "detail": str(exc)},
                )
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
                status="retrying" if retrying else "failed",
                result={"error": type(exc).__name__, "detail": str(exc)},
            )

    def _run_state_decay(self, *, now: datetime) -> dict[str, Any]:
        state = self.store.load_state()
        transition = self.runtime.state_engine.apply_time_decay(state, now=now)
        with self.store.atomic():
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
        pending = self.store.claim_deliverable_outbox(now=now)
        delivered: list[str] = []
        retrying: list[str] = []
        queued: list[str] = []
        failed: list[str] = []
        receipts: list[dict[str, Any]] = []
        title = self.store.load_state().persona_name or "叶筝"
        for item in pending:
            message_id = str(item["message_id"])
            stored_payload = dict(item.get("payload", {}) or {})
            domain_payload = dict(stored_payload.get("payload", {}) or {})
            signal_payload = dict(domain_payload.get("signal", {}) or {})
            signal = ProactiveSignal(
                due=True,
                score=float(signal_payload.get("score", item.get("score", 0.0))),
                reason=str(signal_payload.get("reason", item.get("reason", "outbox_delivery"))),
                next_check_minutes=int(signal_payload.get("next_check_minutes", 15)),
                draft_message=str(item.get("draft_text", "")),
                trace_id=str(item.get("trace_id", "")),
                created_at=str(item.get("created_at", "")),
                signal_type=str(signal_payload.get("signal_type", item.get("signal_type", "notification"))),
                anchor_memory_ids=tuple(signal_payload.get("anchor_memory_ids", item.get("anchor_memory_ids", [])) or []),
                hold_reasons=tuple(signal_payload.get("hold_reasons", []) or []),
            )
            delivery = self.runtime.notification_bridge.deliver(
                message=str(item.get("draft_text", "")), signal=signal,
                trace_id=str(item.get("trace_id", "")), now=now, title=title,
                delivery_context=dict(stored_payload.get("delivery_progress", {}) or {}),
            )
            with self.store.atomic():
                updated = self.store.update_outbox_delivery(
                    message_id,
                    delivery.to_dict(),
                    now=now,
                    lease_token=str(item.get("_delivery_lock_token", "")),
                )
                status = str(updated.get("status", "failed")) if updated else "failed"
                if updated is not None:
                    self.store.record_outbox_receipt(
                        message_id, delivery.receipt_type, channel=delivery.channel,
                        payload=delivery.to_dict(), occurred_at=delivery.occurred_at,
                    )
                if updated is not None and status == "delivered" and str(item.get("reason", "")) == "scheduled_reminder":
                    reminder_payload = dict(domain_payload.get("reminder", {}) or {})
                    reminder_id = str(reminder_payload.get("reminder_id") or item.get("signal_id", ""))
                    if reminder_id:
                        self.store.mark_reminder_delivered(reminder_id, now=now)
            target = {
                "delivered": delivered,
                "retrying": retrying,
                "queued": queued,
                "failed": failed,
            }.get(status, failed)
            target.append(message_id)
            receipts.append({"message_id": message_id, "status": status, "delivery": delivery.to_dict()})
        if receipts:
            self.store.append_event(
                make_event(
                    "outbox_delivery",
                    f"delivered={len(delivered)} retrying={len(retrying)} queued={len(queued)} failed={len(failed)}",
                    {"receipts": receipts, "processed_at": utc_now_iso(now)},
                    trace_id=new_event_id("trace"),
                    now=now,
                )
            )
        return {"delivered": delivered, "retrying": retrying, "queued": queued, "failed": failed}


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
