
from sqlalchemy import select

from database import SessionLocal
from logging_utils import log_event
from models import Task

MAX_TASK_ATTEMPTS = 3


def execute_task(workflow_id, task_id):
    with SessionLocal() as db:
        task = db.scalars(
            select(Task).where(
                Task.workflow_id == workflow_id,
                Task.id == task_id,
            )
        ).first()

        if task is None or task.status != "queued":
            return

        task.status = "running"
        task.attempts += 1
        db.commit()

        task_type = task.task_type
        payload = task.payload or {}

        log_event(
            workflow_id,
            "TASK_STARTED",
            f"Task '{task.name}' started execution.",
            task_id=task_id,
        )

    try:
        if task_type == "echo":
            result = {
                "message": payload.get("message", "Task completed"),
                "worker": "RQ worker",
                "status": "success",
            }
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

        with SessionLocal() as db:
            task = db.scalars(
                select(Task).where(
                    Task.workflow_id == workflow_id,
                    Task.id == task_id,
                )
            ).first()

            if task:
                task.result = result
                task.error = None
                task.status = "completed"
                db.commit()

        log_event(
            workflow_id,
            "TASK_COMPLETED",
            f"Task '{task_id}' completed successfully.",
            task_id=task_id,
        )

    except Exception as exc:
        should_retry = False
        next_attempt = None
        with SessionLocal() as db:
            task = db.scalars(
                select(Task).where(
                    Task.workflow_id == workflow_id,
                    Task.id == task_id,
                )
            ).first()

            if task:
                should_retry = task.attempts < MAX_TASK_ATTEMPTS
                next_attempt = task.attempts + 1
                task.status = "pending" if should_retry else "failed"
                task.error = str(exc)
                db.commit()

        log_event(
            workflow_id,
            "TASK_FAILED",
            f"Task '{task_id}' failed: {exc}",
            task_id=task_id,
        )

        if should_retry:
            log_event(
                workflow_id,
                "TASK_RETRYING",
                (
                    f"Task '{task_id}' will be retried "
                    f"(attempt {next_attempt} of {MAX_TASK_ATTEMPTS})."
                ),
                task_id=task_id,
            )

    from scheduler import dispatch_ready_tasks

    dispatch_ready_tasks(workflow_id)
