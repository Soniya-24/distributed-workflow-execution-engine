from database import SessionLocal
from models import ExecutionLog


def log_event(workflow_id, event, message, task_id=None):
    with SessionLocal() as db:
        log = ExecutionLog(
            workflow_id=workflow_id,
            task_id=task_id,
            event=event,
            message=message,
        )
        db.add(log)
        db.commit()
