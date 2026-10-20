from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor

import httpx

from .config import HealthCheck, Service


def probe(service: Service) -> dict:
    if not service.port or not service.health:
        return {"status": "not_configured"}
    return probe_url(f"http://127.0.0.1:{service.port}{service.health.path}", service.health)


def probe_url(url: str, check: HealthCheck) -> dict:
    started = time.monotonic()
    try:
        with httpx.Client(
            trust_env=False,
            timeout=check.timeout,
            follow_redirects=False,
            headers={"Accept-Encoding": "identity"},
        ) as client:
            with client.stream("GET", url) as response:
                status_ok = (
                    response.status_code == check.expected_status
                    if check.expected_status is not None
                    else 200 <= response.status_code < 500
                )
                body = bytearray()
                if check.expected_body is not None:
                    for block in response.iter_raw():
                        body.extend(block[: 65536 - len(body)])
                        if len(body) >= 65536 or time.monotonic() - started >= check.timeout:
                            break
                body_ok = check.expected_body is None or check.expected_body in body.decode(
                    "utf-8", errors="replace"
                )
                return {
                    "status": "healthy" if status_ok and body_ok else "unhealthy",
                    "http_status": response.status_code,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                }
    except httpx.HTTPError:
        return {"status": "unhealthy", "reason": "HTTP health check could not connect"}


class HealthMonitor:
    """Bounded background probes never block the supervisor's reconciliation loop."""

    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="speii-health")
        self.pending: dict[str, tuple[int, Future]] = {}
        self.states: dict[str, dict] = {}
        self.next_at: dict[str, float] = {}

    def poll(self, services: dict[str, Service], workers: dict) -> dict[str, dict]:
        now = time.monotonic()
        for name, (generation, future) in list(self.pending.items()):
            if not future.done():
                continue
            self.pending.pop(name)
            service = services.get(name)
            if not service or service.generation != generation:
                continue
            result = future.result()
            previous = self.states.get(name, {})
            failures = previous.get("failures", 0) + 1 if result["status"] == "unhealthy" else 0
            self.states[name] = {**result, "failures": failures, "generation": generation}
            worker = workers.get(name)
            if (
                worker
                and service.health
                and failures >= service.health.failures
                and now - worker.started_at > service.health.startup_timeout
            ):
                if worker.process and worker.process.poll() is None:
                    worker.request_restart("Health check failure limit reached; restarting")
                    self.states[name]["failures"] = 0
        for name, service in services.items():
            if service.status != "running" or not service.health or not service.port:
                self.states.pop(name, None)
                continue
            if name not in self.pending and now >= self.next_at.get(name, 0):
                if len(self.pending) < 16:
                    self.pending[name] = (
                        service.generation,
                        self.pool.submit(probe, service.model_copy(deep=True)),
                    )
                    self.next_at[name] = now + service.health.interval
        return {
            name: value
            for name, value in self.states.items()
            if name in services and value["generation"] == services[name].generation
        }

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
