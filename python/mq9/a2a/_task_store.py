"""Mq9A2ATaskStore — A2A TaskStore backed by a mq9 mailbox."""

from __future__ import annotations

import logging

from a2a.server.tasks import TaskStore
from a2a.server.request_handlers import ServerCallContext
from a2a.types.a2a_pb2 import Task, ListTasksRequest, ListTasksResponse
from google.protobuf import json_format

from mq9.client import Mq9Client

_logger = logging.getLogger(__name__)

# key prefix used for dedup: only the latest state per task_id is kept
_KEY_PREFIX = "task."


class Mq9A2ATaskStore(TaskStore):
    """
    A2A TaskStore that stores task state in a dedicated mq9 mailbox.

    Each task is stored as a mq9 message with key="task.{task_id}" so that
    only the latest state is retained (key dedup).  On restart the agent
    recovers all live tasks via QUERY — no in-memory state required.

    The mailbox is created automatically on first use inside agent.run().
    """

    def __init__(self, mq9_client: Mq9Client, mailbox: str) -> None:
        self._mq9 = mq9_client
        self._mailbox = mailbox
        self._ready = False

    # Called by Mq9A2AAgent after the mailbox has been created.
    def mark_ready(self) -> None:
        self._ready = True

    # ------------------------------------------------------------------ TaskStore

    async def save(self, task: Task, context: ServerCallContext | None = None) -> None:
        if not self._ready:
            return
        payload = json_format.MessageToJson(task).encode()
        try:
            await self._mq9.send(
                self._mailbox,
                payload,
                key=f"{_KEY_PREFIX}{task.id}",
            )
        except Exception as exc:
            _logger.warning("[task_store] save failed for task_id=%s: %s", task.id, exc)

    async def get(self, task_id: str, context: ServerCallContext | None = None) -> Task | None:
        if not self._ready:
            return None
        try:
            msgs = await self._mq9.query(self._mailbox, key=f"{_KEY_PREFIX}{task_id}")
            if not msgs:
                return None
            return json_format.Parse(msgs[0].payload, Task())
        except Exception as exc:
            _logger.warning("[task_store] get failed for task_id=%s: %s", task_id, exc)
            return None

    async def delete(self, task_id: str, context: ServerCallContext | None = None) -> None:
        if not self._ready:
            return
        try:
            msgs = await self._mq9.query(self._mailbox, key=f"{_KEY_PREFIX}{task_id}")
            for msg in msgs:
                await self._mq9.delete(self._mailbox, msg.msg_id)
        except Exception as exc:
            _logger.warning("[task_store] delete failed for task_id=%s: %s", task_id, exc)

    async def list(
        self,
        params: ListTasksRequest,
        context: ServerCallContext | None = None,
    ) -> ListTasksResponse:
        if not self._ready:
            return ListTasksResponse(tasks=[])
        try:
            limit = params.page_size if params.page_size > 0 else 100
            msgs = await self._mq9.query(self._mailbox, limit=limit)
            tasks: list[Task] = []
            for msg in msgs:
                try:
                    tasks.append(json_format.Parse(msg.payload, Task()))
                except Exception:
                    pass
            return ListTasksResponse(tasks=tasks)
        except Exception as exc:
            _logger.warning("[task_store] list failed: %s", exc)
            return ListTasksResponse(tasks=[])
