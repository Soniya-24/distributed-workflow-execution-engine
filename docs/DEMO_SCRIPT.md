# Demonstration Script

## Before the demonstration

From the project root:

```bat
docker compose up -d --build
```

Start the static frontend in a separate terminal:

```bat
cd C:\Users\jeswa\distributed-workflow-engine\Frontend
python -m http.server 5500
```

Open:

- http://127.0.0.1:5500
- http://127.0.0.1:8000/docs

Confirm the API reports `API Connected` and verify the services with:

```bat
docker compose ps
```

## Demonstration sequence

### 1. Explain the architecture

Point out that the browser calls FastAPI, FastAPI persists state in
PostgreSQL, ready tasks go to Redis, and the RQ worker executes them.

### 2. Create a workflow

In the dashboard, use:

- Name: `Document Processing Demo`
- Task 1: `collect`, no dependencies
- Task 2: `process`, dependency on `collect`

Click **Submit Workflow** and select the created workflow.

### 3. Run and observe

Click **Run Workflow**. Explain the visible transitions:

```text
pending → queued → running → completed
```

The selected workflow updates automatically every three seconds. Show each
task’s result and attempt count.

### 4. Show execution logs

Expand the **Execution Logs** section and identify:

```text
WORKFLOW_CREATED
WORKFLOW_STARTED
TASK_QUEUED
TASK_STARTED
TASK_COMPLETED
WORKFLOW_COMPLETED
```

Explain that the logs are persisted in PostgreSQL and retrieved through:

```text
GET /workflows/{workflow_id}/logs
```

### 5. Demonstrate parallel execution

Create two independent tasks and a third task depending on both. Explain that
the first two tasks are ready together, while the third waits until both
dependencies are complete.

### 6. Demonstrate failure and retries

Create a task with `task_type` set to `unsupported`. Run the workflow and show:

```text
TASK_FAILED
TASK_RETRYING
TASK_FAILED
TASK_RETRYING
TASK_FAILED
WORKFLOW_FAILED
```

Point out that the task’s attempt count reaches three and the final error is
stored with the task.

## Suggested viva questions

### Why is a DAG validation step necessary?

It prevents impossible execution plans. Duplicate IDs make task references
ambiguous, unknown dependencies cannot be scheduled, and cycles have no valid
starting point.

### Where does the asynchronous behavior happen?

The API enqueues work in Redis and returns without executing the task. The RQ
worker consumes the queue and performs the task separately.

### How is parallelism achieved?

The scheduler marks every pending task whose dependencies are complete as
`queued` in one pass. Independent tasks therefore enter the queue together.

### How are retries bounded?

The worker increments the persisted attempt counter before execution and allows
three total attempts. This prevents an endlessly failing task from retrying
forever.

### How is the system observable?

Workflow and task state are persisted in PostgreSQL, and state transitions are
recorded as execution log events. The dashboard displays both.

### What does Docker Compose provide?

It starts PostgreSQL, Redis, the FastAPI API, and the RQ worker with health
checks and service-to-service networking.

## Closing statement

This project demonstrates a complete workflow execution path from API
submission, through dependency-aware queueing and worker execution, to durable
results, retries, failure propagation, and browser-visible execution history.


cd /mnt/c/Users/jeswa/distributed-workflow-engine
ls
Step 2: Start the project
Run:
docker compose up -d --build


Wait for the build and containers to finish starting.
Step 3: Check the containers
docker compose ps


If any container is not running, inspect the logs:
docker compose logs --tail=100


Step 4: Start the frontend dashboard
If your Compose configuration does not already start the frontend, open a second Ubuntu terminal and run:
cd /mnt/c/Users/jeswa/distributed-workflow-engine/Frontend
python3 -m http.server 5500


Keep that terminal open.
Step 5: Open your project
Frontend Dashboard

http://127.0.0.1:5500

Open

FastAPI Swagger

http://127.0.0.1:8000/docs
