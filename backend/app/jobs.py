# -*- coding: utf-8 -*-
"""Реестр фоновых задач: генерация и декодирование без блокировки UI (ТЗ §28).

Файлы-результаты хранятся во временном хранилище со случайными именами и
удаляются после истечения срока (ТЗ §32).
"""
import os
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

JOB_TTL_SEC = 3600  # результаты хранятся не дольше часа


class Job:
    def __init__(self, kind: str):
        self.id: str = uuid.uuid4().hex
        self.kind: str = kind          # "generate" | "decode"
        self.status: str = "queued"   # queued | running | done | error
        self.phase: str = ""          # текущая фаза
        self.done: int = 0
        self.total: int = 0
        self.message: str = ""
        self.results: List[Dict[str, Any]] = []
        self.extra: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.file_path: Optional[str] = None
        self.file_name: Optional[str] = None
        self.mime: Optional[str] = None
        self.created: float = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "results": self.results,
            "extra": self.extra,
            "error": self.error,
            "fileReady": bool(self.file_path and os.path.exists(self.file_path)),
            "fileName": self.file_name,
        }


_JOBS: Dict[str, Job] = {}
_LOCK = threading.Lock()


def create_job(kind: str) -> Job:
    job = Job(kind)
    with _LOCK:
        _cleanup_old_unlocked()
        _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def set_progress(job: Job, done: int, total: int, phase: str = "",
                 message: str = "") -> None:
    job.done = done
    job.total = total
    if phase:
        job.phase = phase
    if message:
        job.message = message


def store_result_file(job: Job, data: bytes, file_name: str, mime: str) -> None:
    """Сохраняет результат во временное хранилище со случайным именем (§32)."""
    fd, path = tempfile.mkstemp(prefix="dmjob_", suffix=os.path.splitext(file_name)[1])
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    job.file_path = path
    job.file_name = file_name
    job.mime = mime


def finish_error(job: Job, message: str) -> None:
    job.status = "error"
    job.error = message
    _remove_file(job)


def finish_ok(job: Job) -> None:
    job.status = "done"


def _remove_file(job: Job) -> None:
    if job.file_path and os.path.exists(job.file_path):
        try:
            os.remove(job.file_path)
        except OSError:
            pass
        job.file_path = None


def _cleanup_old_unlocked() -> None:
    """Удаляет завершённые задачи старше JOB_TTL_SEC вместе с файлами."""
    now = time.time()
    stale = [jid for jid, j in _JOBS.items() if now - j.created > JOB_TTL_SEC]
    for jid in stale:
        job = _JOBS.pop(jid)
        _remove_file(job)