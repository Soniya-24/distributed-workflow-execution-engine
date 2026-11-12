
from contextlib import asynccontextmanager
from collections import deque

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from logging_utils import log_event
from models import ExecutionLog, Task, Workflow
from schemas import WorkflowCreate
from scheduler import dispatch_ready_tasks


def validate_dag(tasks):
    task_ids = [task.id for task in tasks]

    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Task IDs must be unique within a workflow")

    known_ids = set(task_ids)
    indegree = {task.id: 0 for task in tasks}
    children = {task.id: [] for task in tasks}

    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in known_ids:
                raise ValueError(
                    f"Task '{task.id}' depends on unknown task '{dependency}'"
                )

            if dependency == task.id:
                raise ValueError(
                    f"Task '{task.id}' cannot depend on itself"
                )

            indegree[task.id] += 1
            children[dependency].append(task.id)

    queue = deque(
        task_id
        for task_id, degree in indegree.items()
        if degree == 0
    )

    visited = 0

    while queue:
        current = queue.popleft()
        visited += 1

        for child in children[current]:
            indegree[child] -= 1

            if indegree[child] == 0:
                queue.append(child)

    if visited != len(tasks):
        raise ValueError(
            "Circular dependency detected; workflow must be a DAG"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Distributed Workflow Execution Engine",
    description="API for workflow submission and task monitoring",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Distributed Workflow Execution Engine API",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "workflow-api",
    }


@app.post("/workflows", status_code=201)
def create_workflow(
    request: WorkflowCreate,
    db: Session = Depends(get_db),
):
    try:
        validate_dag(request.tasks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    workflow = Workflow(
        name=request.name,
        status="pending",
    )

    db.add(workflow)
    db.flush()

    try:
        for item in request.tasks:
            db.add(
                Task(
                    id=item.id,
                    workflow_id=workflow.id,
                    name=item.name,
                    task_type=item.task_type,
                    payload=item.payload,
                    dependencies=item.dependencies,
                    status="pending",
                )
            )

        db.commit()
        db.refresh(workflow)
        log_event(
            workflow.id,
            "WORKFLOW_CREATED",
            f"Workflow '{workflow.name}' created successfully.",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not save workflow. Check task IDs "
                "and database logs."
            ),
        )

    return {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "status": workflow.status,
        "task_count": len(request.tasks),
        "message": "Workflow created successfully",
    }


@app.get("/workflows")
def list_workflows(db: Session = Depends(get_db)):
    workflows = db.scalars(
        select(Workflow).order_by(Workflow.created_at.desc())
    ).all()

    return [
        {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "status": workflow.status,
            "created_at": workflow.created_at,
        }
        for workflow in workflows
    ]


@app.get("/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    tasks = db.scalars(
        select(Task)
        .where(Task.workflow_id == workflow_id)
        .order_by(Task.id)
    ).all()

    return {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "status": workflow.status,
        "created_at": workflow.created_at,
        "tasks": [
            {
                "id": task.id,
                "name": task.name,
                "task_type": task.task_type,
                "payload": task.payload,
                "dependencies": task.dependencies,
                "status": task.status,
                "result": task.result,
                "error": task.error,
                "attempts": task.attempts,
            }
            for task in tasks
        ],
    }


@app.post("/workflows/{workflow_id}/run")
def run_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    tasks = db.scalars(
        select(Task).where(Task.workflow_id == workflow_id)
    ).all()

    if not tasks:
        raise HTTPException(
            status_code=400,
            detail="Workflow has no tasks",
        )

    if workflow.status in ("running", "completed", "failed"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Workflow cannot run from status "
                f"'{workflow.status}'"
            ),
        )

    workflow.status = "running"
    db.commit()
    log_event(
        workflow_id,
        "WORKFLOW_STARTED",
        "Workflow execution requested.",
    )

    try:
        dispatch_ready_tasks(workflow_id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=f"Could not schedule workflow: {exc}",
        )

    return {
        "workflow_id": workflow_id,
        "status": "running",
        "message": "Workflow execution started",
    }


@app.get("/workflows/{workflow_id}/logs")
def get_workflow_logs(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    logs = db.scalars(
        select(ExecutionLog)
        .where(ExecutionLog.workflow_id == workflow_id)
        .order_by(ExecutionLog.created_at.desc(), ExecutionLog.id.desc())
    ).all()

    return [
        {
            "id": log.id,
            "workflow_id": log.workflow_id,
            "task_id": log.task_id,
            "event": log.event,
            "message": log.message,
            "created_at": log.created_at,
        }
        for log in logs
    ]
