import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable, List
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


class StreamBroadcaster:
    """
    Thread-safe broadcaster for real-time streaming tasks.
    Allows multiple subscribers (e.g. initial request and reconnected requests after F5)
    to receive tokens while the generator runs to completion independently in the background.
    """

    def __init__(self, key: str):
        self.key = key
        self.listeners: List[asyncio.Queue] = []
        self.history: List[Dict[str, Any]] = []
        self.is_done = False
        self.final_result: Optional[Any] = None
        self.error: Optional[Exception] = None
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        async with self._lock:
            # Replay all historical events already emitted
            for evt in self.history:
                await q.put(evt)
            if not self.is_done:
                self.listeners.append(q)
            else:
                if self.error:
                    await q.put({"type": "error", "error": str(self.error)})
                elif self.final_result:
                    await q.put({"type": "ready", "step": self.final_result})
                await q.put(None)  # Sentinel to terminate listener
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            if q in self.listeners:
                self.listeners.remove(q)

    async def emit(self, event: Dict[str, Any]) -> None:
        async with self._lock:
            self.history.append(event)
            dead_queues = []
            for q in self.listeners:
                try:
                    q.put_nowait(event)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in self.listeners:
                    self.listeners.remove(dq)

    async def finish(self, final_result: Any = None) -> None:
        async with self._lock:
            self.is_done = True
            self.final_result = final_result
            for q in self.listeners:
                try:
                    if final_result:
                        q.put_nowait({"type": "ready", "step": final_result})
                    q.put_nowait(None)
                except Exception:
                    pass
            self.listeners.clear()

    async def fail(self, err: Exception) -> None:
        async with self._lock:
            self.is_done = True
            self.error = err
            for q in self.listeners:
                try:
                    q.put_nowait({"type": "error", "error": str(err)})
                    q.put_nowait(None)
                except Exception:
                    pass
            self.listeners.clear()


class DetachedTaskManager:
    """
    Manages long-running background tasks (course generation, lesson synthesis, audio prefetch)
    so they run independently with their own database sessions and NEVER get cancelled
    when a user reloads the browser, navigates away, or closes the tab.
    """

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._broadcasters: Dict[str, StreamBroadcaster] = {}
        self._lock = asyncio.Lock()

    def is_task_running(self, task_key: str) -> bool:
        t = self._tasks.get(task_key)
        return t is not None and not t.done()

    def get_broadcaster(self, task_key: str) -> Optional[StreamBroadcaster]:
        return self._broadcasters.get(task_key)

    async def run_detached(
        self,
        task_key: str,
        coro_fn: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> asyncio.Task:
        """
        Launches a detached task with its own independent AsyncSession.
        If a task with the same key is already running, returns the existing task.
        """
        async with self._lock:
            existing = self._tasks.get(task_key)
            if existing and not existing.done():
                logger.info(f"Task '{task_key}' is already running in background; returning existing task.")
                return existing

            broadcaster = StreamBroadcaster(task_key)
            self._broadcasters[task_key] = broadcaster

            async def _worker():
                start_t = time.time()
                try:
                    async with async_session_maker() as session:
                        res = await coro_fn(session, broadcaster, *args, **kwargs)
                        await broadcaster.finish(res)
                        return res
                except asyncio.CancelledError:
                    logger.warning(f"Detached task '{task_key}' was cancelled externally.")
                    await broadcaster.fail(RuntimeError("Task cancelled"))
                    raise
                except Exception as e:
                    logger.error(f"Error in detached task '{task_key}': {e}", exc_info=True)
                    await broadcaster.fail(e)
                    raise
                finally:
                    duration = time.time() - start_t
                    logger.info(f"Detached task '{task_key}' completed in {duration:.2f}s")
                    # Keep broadcaster in cache briefly so recent reloads can retrieve the result
                    asyncio.create_task(self._delayed_cleanup(task_key, delay=120.0))

            task = asyncio.create_task(_worker())
            self._tasks[task_key] = task
            return task

    async def _delayed_cleanup(self, task_key: str, delay: float = 120.0) -> None:
        await asyncio.sleep(delay)
        async with self._lock:
            self._tasks.pop(task_key, None)
            self._broadcasters.pop(task_key, None)


task_manager = DetachedTaskManager()
