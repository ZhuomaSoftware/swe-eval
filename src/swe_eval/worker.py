from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import threading
import time
import uuid

from .config import Settings
from .engine import execute_run
from .sandbox import cleanup_containers
from .schema import ACTIVE, Metrics, RunState
from .service import repository
from .storage import Conflict

logger = logging.getLogger(__name__)


def terminate_child(process):
    """Kill the child's Unix session, including in-flight Docker client processes."""
    def send(signum):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            # The spawn target may not yet have called setsid().
            if process.is_alive():
                process.terminate() if signum == signal.SIGTERM else process.kill()
    send(signal.SIGTERM)
    process.join(timeout=2)
    send(signal.SIGKILL)
    process.join(timeout=2)


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = repository(settings, worker=True)
        self.owner = uuid.uuid4().hex
        self.stop = threading.Event()

    def acquire(self):
        if not self.repo.acquire(self.owner, self.settings.lease_seconds):
            raise Conflict("another worker holds the single-worker lease")
        # Recover only after the previous lease expires. Never silently repeat a paid run.
        self.repo.event("worker_starting", "Lease acquired; recovery and cleanup in progress")
        cleanup_started = time.monotonic()
        self.repo.event("cleanup_started", "Startup orphan cleanup in progress")
        interrupted = self.repo.recover(self.owner)
        if not cleanup_containers(self.settings.docker_bin, self.repo.service_id):
            self.repo.event("cleanup_failed", "Startup orphan cleanup failed")
            self.repo.release(self.owner)
            raise RuntimeError("Docker unavailable or orphan cleanup failed; worker refuses to start")
        self.repo.event("cleanup_complete", f"Startup cleanup finished in {time.monotonic()-cleanup_started:.3f}s")
        self.repo.event("worker_ready", f"Docker cleanup complete in {time.monotonic()-cleanup_started:.3f}s; recovered {len(interrupted)} runs")
        if interrupted:
            logger.info("Recovered %d interrupted evaluations as failed", len(interrupted))

    def supervise(self, record, *, supplied_patch=None):
        run_id = record["id"]
        effective = (record.get("snapshot") or {}).get("effective_model", record["model"])
        limit = min(record["task"]["time_limit"], effective["max_evaluation_duration"])
        process = multiprocessing.get_context("spawn").Process(
            target=execute_run, args=(self.settings, run_id, supplied_patch), daemon=False)
        process.start()
        started, last_heartbeat = time.monotonic(), 0.0
        final_state, error = None, None
        lease_lost = False
        try:
            while process.is_alive():
                now = time.monotonic()
                if now - last_heartbeat >= self.settings.lease_seconds / 3:
                    if not self.repo.heartbeat(self.owner, self.settings.lease_seconds):
                        lease_lost = True
                        final_state, error = RunState.FAILED, "worker_lease_lost"
                        break
                    last_heartbeat = now
                self.repo.reconcile_batches()
                current = self.repo.get(run_id)
                if self.stop.is_set() or current["cancel_requested"]:
                    final_state, error = RunState.CANCELLED, "evaluation_cancelled"
                    break
                if now - started >= limit:
                    final_state, error = RunState.TIMEOUT, "evaluation_time_limit_exceeded"
                    break
                process.join(timeout=0.2)
        finally:
            terminate_child(process)
            # A worker crash or timeout must not leave the daemon running generated code.
            self.repo.event("cleanup_started", "Run container cleanup in progress")
            cleaned = cleanup_containers(self.settings.docker_bin, self.repo.service_id, run_id)
            current = self.repo.get(run_id)
            if current["state"] in ACTIVE and not lease_lost:
                metrics = Metrics.model_validate(current["metrics"])
                metrics.wall_seconds = round(time.monotonic() - started, 4)
                try:
                    self.repo.transition(run_id, final_state or RunState.FAILED,
                                         error or "worker_child_interrupted", metrics=metrics)
                except Conflict:
                    # Another lease owner recovered the run after our last
                    # heartbeat. Its terminal record is authoritative.
                    if self.repo.heartbeat(self.owner, self.settings.lease_seconds):
                        raise
                    lease_lost = True
            if cleaned:
                self.repo.event("cleanup_complete", "Run container cleanup finished")
            if not cleaned:
                self.repo.event("cleanup_failed", "Run container cleanup failed")
                logger.error("Container cleanup failed; stopping worker")
                self.stop.set()
                self.repo.log(run_id, "cleanup_error", "Daemon cleanup failed; operator intervention required")
        if lease_lost:
            raise Conflict("worker lease was lost; worker stopped")
        return self.repo.get(run_id)

    def run(self, *, once=False):
        self.acquire()
        try:
            while not self.stop.is_set():
                if not self.repo.heartbeat(self.owner, self.settings.lease_seconds):
                    raise Conflict("worker lease was lost")
                record = self.repo.claim(self.owner)
                if record:
                    self.supervise(record)
                elif once:
                    return
                else:
                    self.stop.wait(1)
                if once:
                    return
        finally:
            self.repo.release(self.owner)

    def install_signal_handlers(self):
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: self.stop.set())
