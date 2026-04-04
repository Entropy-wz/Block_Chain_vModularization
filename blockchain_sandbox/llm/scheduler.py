import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .agent import AgentObservation, MinerAgent

logger = logging.getLogger(__name__)


class TaskPriority:
    HIGH = 0
    MEDIUM = 5
    LOW = 10


@dataclass(order=True)
class LLMTask:
    priority: int
    created_at: float
    sequence: int
    miner_id: str = field(compare=False)
    obs: AgentObservation = field(compare=False)
    agent: MinerAgent = field(compare=False)
    future: asyncio.Future = field(compare=False)
    timeout: float = field(default=30.0, compare=False)
    max_attempts: int = field(default=3, compare=False)
    attempts: int = field(default=0, compare=False)


class LLMScheduler:
    """Independent async scheduler for LLM requests with concurrency control and backpressure."""

    def __init__(
        self,
        max_concurrent: int = 5,
        max_queue_size: int = 256,
        default_timeout: float = 30.0,
        max_attempts: int = 3,
    ) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.max_queue_size = max(1, int(max_queue_size))
        self.default_timeout = max(0.1, float(default_timeout))
        self.max_attempts = max(1, int(max_attempts))

        self.task_queue: asyncio.PriorityQueue[LLMTask] = asyncio.PriorityQueue(maxsize=self.max_queue_size)

        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.timeout_requests = 0
        self.rejected_requests = 0
        self.retried_requests = 0
        self.total_wait_time = 0.0
        self.total_processing_time = 0.0
        self.max_observed_queue_size = 0

        self._workers: List[asyncio.Task] = []
        self._is_running = False
        self._sequence = 0

    async def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        for _ in range(self.max_concurrent):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        self._is_running = False
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def submit(
        self,
        agent: MinerAgent,
        obs: AgentObservation,
        priority: int = TaskPriority.MEDIUM,
        timeout: float | None = None,
    ) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        if self.task_queue.full():
            self.total_requests += 1
            self.failed_requests += 1
            self.rejected_requests += 1
            future.set_exception(RuntimeError("LLM scheduler queue is full; request rejected by backpressure"))
            return future

        self._sequence += 1
        task = LLMTask(
            priority=int(priority),
            created_at=time.perf_counter(),
            sequence=self._sequence,
            miner_id=agent.miner_id,
            obs=obs,
            agent=agent,
            future=future,
            timeout=self.default_timeout if timeout is None else max(0.1, float(timeout)),
            max_attempts=self.max_attempts,
        )
        self.task_queue.put_nowait(task)
        self.total_requests += 1
        self.max_observed_queue_size = max(self.max_observed_queue_size, self.task_queue.qsize())
        return future

    async def _worker_loop(self) -> None:
        while self._is_running:
            try:
                task = await self.task_queue.get()
                self.total_wait_time += max(0.0, time.perf_counter() - task.created_at)
                try:
                    await self._process_task(task)
                finally:
                    self.task_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover
                logger.exception("LLM scheduler worker loop error: %s", exc)

    async def _process_task(self, task: LLMTask) -> None:
        task.attempts += 1
        started_at = time.perf_counter()
        try:
            decision = await asyncio.wait_for(task.agent.decide_async(task.obs), timeout=task.timeout)
            self.total_processing_time += max(0.0, time.perf_counter() - started_at)
            self.successful_requests += 1
            if not task.future.done():
                task.future.set_result(decision)
        except asyncio.TimeoutError as exc:
            if task.attempts < task.max_attempts:
                self.retried_requests += 1
                self.task_queue.put_nowait(task)
                self.max_observed_queue_size = max(self.max_observed_queue_size, self.task_queue.qsize())
                return
            self.timeout_requests += 1
            self.failed_requests += 1
            if not task.future.done():
                task.future.set_exception(exc)
        except Exception as exc:
            if task.attempts < task.max_attempts:
                self.retried_requests += 1
                await asyncio.sleep(0.25 * task.attempts)
                self.task_queue.put_nowait(task)
                self.max_observed_queue_size = max(self.max_observed_queue_size, self.task_queue.qsize())
                return
            self.failed_requests += 1
            if not task.future.done():
                task.future.set_exception(exc)

    def get_metrics(self) -> Dict[str, Any]:
        avg_wait = self.total_wait_time / self.total_requests if self.total_requests else 0.0
        avg_processing = self.total_processing_time / self.successful_requests if self.successful_requests else 0.0
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "timeout_requests": self.timeout_requests,
            "rejected_requests": self.rejected_requests,
            "retried_requests": self.retried_requests,
            "queue_size": self.task_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "max_observed_queue_size": self.max_observed_queue_size,
            "avg_wait_time_sec": avg_wait,
            "avg_processing_time_sec": avg_processing,
        }
