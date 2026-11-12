
import os

from redis import Redis
from rq import Queue
from sqlalchemy import select

from database import SessionLocal
from logging_utils import log_event
from models import Task, Workflow

redis_connection = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=False,
)
task_queue = Queue("workflow_tasks", connection=redis_connection)


def dispatch_ready_tasks(workflow_id):
    with SessionLocal() as db:
        workflow = db.get(Workflow, workflow_id)

        if workflow is None or workflow.status in ("completed", "failed"):
            return

        tasks = db.scalars(
            select(Task).where(Task.workflow_id == workflow_id)
        ).all()

        tasks_by_id = {task.id: task for task in tasks}

        # Stop the workflow if a task has failed.
        if any(task.status == "failed" for task in tasks):
            workflow.status = "failed"
            db.commit()
            log_event(
                workflow_id,
                "WORKFLOW_FAILED",
                "Workflow stopped because a task failed.",
            )
            return

        # Complete the workflow when every task is complete.
        if all(task.status == "completed" for task in tasks):
            workflow.status = "completed"
            db.commit()
            log_event(
                workflow_id,
                "WORKFLOW_COMPLETED",
                "All workflow tasks completed successfully.",
            )
            return

        workflow.status = "running"
        ready_task_ids = []

        for task in tasks:
            if task.status != "pending":
                continue

            dependencies = task.dependencies or []

            if all(
                tasks_by_id[dependency].status == "completed"
                for dependency in dependencies
            ):
                task.status = "queued"
                ready_task_ids.append(task.id)

        # Save queued status before sending tasks to Redis.
        db.commit()

    # Enqueue outside the database session.
    from worker import execute_task

    for task_id in ready_task_ids:
        try:
            task_queue.enqueue(
                execute_task,
                workflow_id,
                task_id,
                job_timeout=120,
            )
            log_event(
                workflow_id,
                "TASK_QUEUED",
                f"Task '{task_id}' added to the Redis queue.",
                task_id=task_id,
            )
        except Exception:
            with SessionLocal() as db:
                task = db.get(Task, task_id)
                if task and task.workflow_id == workflow_id:
                    task.status = "failed"
                    task.error = "Could not enqueue task in Redis."
                    workflow = db.get(Workflow, workflow_id)
                    if workflow:
                        workflow.status = "failed"
                    db.commit()
            raise
