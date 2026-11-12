
const API_URL = "http://localhost:8000";

const workflowList = document.getElementById("workflowList");
const workflowDetails = document.getElementById("workflowDetails");
const connectionStatus = document.getElementById("connectionStatus");
const formMessage = document.getElementById("formMessage");
let selectedWorkflowId = null;

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || `Request failed: ${response.status}`);
    }

    return data;
}

function showStatus(status) {
    const normalizedStatus = String(status || "unknown").toLowerCase();
    return `<span class="status status-${escapeHtml(normalizedStatus)}">${escapeHtml(status || "unknown")}</span>`;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

async function checkConnection() {
    try {
        await apiRequest("/health");
        connectionStatus.textContent = "API Connected";
        connectionStatus.style.color = "#9df0bd";
    } catch {
        connectionStatus.textContent = "API Disconnected";
        connectionStatus.style.color = "#ffaaaa";
    }
}

async function loadWorkflows({ silent = false } = {}) {
    if (!silent) {
        workflowList.innerHTML = `
            <div class="emptyState">Loading workflow state...</div>
        `;
    }

    try {
        const workflows = await apiRequest("/workflows");

        document.getElementById("totalWorkflows").textContent =
            workflows.length;

        document.getElementById("activeWorkflows").textContent =
            workflows.filter(w => ["running", "queued"].includes(w.status)).length;

        document.getElementById("completedWorkflows").textContent =
            workflows.filter(w => w.status === "completed").length;

        document.getElementById("failedWorkflows").textContent =
            workflows.filter(w => w.status === "failed").length;

        if (workflows.length === 0) {
            workflowList.innerHTML = `
                <div class="emptyState">No workflows yet. Create your first deployment above.</div>
            `;
            return;
        }

        workflowList.innerHTML = workflows.map(workflow => `
            <div class="workflow">
                <div>
                    <h3>${escapeHtml(workflow.name)}</h3>
                    <p>${escapeHtml(workflow.workflow_id)}</p>
                    <p>${showStatus(workflow.status)}</p>
                </div>
                <div class="workflowActions">
                    <button class="detailsButton" type="button"
                        data-workflow-id="${escapeHtml(workflow.workflow_id)}">
                        Inspect
                    </button>
                    <button class="runButton" type="button"
                        data-run-id="${escapeHtml(workflow.workflow_id)}">
                        ${workflow.status === "pending" ? "Run Workflow" : "Run"}
                    </button>
                </div>
            </div>
        `).join("");

    } catch (error) {
        workflowList.innerHTML = `
            <div class="emptyState">Could not load workflows: ${escapeHtml(error.message)}</div>
        `;
    }
}

async function showWorkflowDetails(workflowId) {
    selectedWorkflowId = workflowId;
    workflowDetails.textContent = "Loading workflow details...";

    try {
        const encodedId = encodeURIComponent(workflowId);
        const [workflow, logs] = await Promise.all([
            apiRequest(`/workflows/${encodedId}`),
            apiRequest(`/workflows/${encodedId}/logs`)
        ]);

        const tasks = workflow.tasks || [];

        workflowDetails.innerHTML = `
            <div class="detailSummary">
                <div>
                    <h3>${escapeHtml(workflow.name)}</h3>
                    <p>Workflow ID: ${escapeHtml(workflow.workflow_id)}</p>
                </div>
                ${showStatus(workflow.status)}
            </div>
            <h3 class="subheading">Tasks <span>${tasks.length}</span></h3>
            ${tasks.length ? tasks.map(task => `
                <div class="task">
                    <div class="taskTop">
                        <h3>${escapeHtml(task.name)}</h3>
                        ${showStatus(task.status)}
                    </div>
                    <p>${escapeHtml(task.id)}</p>
                    <div class="taskMeta">
                        <div><span>Type</span><strong>${escapeHtml(task.task_type)}</strong></div>
                        <div><span>Attempts</span><strong>${escapeHtml(task.attempts)}</strong></div>
                        <div><span>Depends on</span><strong>${escapeHtml(
                            (task.dependencies || []).join(", ") || "None"
                        )}</strong></div>
                    </div>
                    <p><strong>Result:</strong> ${escapeHtml(
                        JSON.stringify(task.result ?? "Not available")
                    )}</p>
                    ${task.error ? `<p class="errorText"><strong>Error:</strong> ${escapeHtml(task.error)}</p>` : ""}
                </div>
            `).join("") : "<p>No tasks found.</p>"}
            <h3 class="subheading">Execution timeline <span>${logs.length} events</span></h3>
            <div class="execution-logs">
                ${logs.length ? logs.map(log => `
                    <div class="log-entry">
                        <div class="logTop">
                            <span class="status">${escapeHtml(log.event)}</span>
                            <small>${escapeHtml(
                                log.created_at
                                    ? new Date(log.created_at).toLocaleString()
                                    : ""
                            )}</small>
                        </div>
                        <p>${escapeHtml(log.message)}</p>
                    </div>
                `).join("") : "<p>No execution logs yet.</p>"}
            </div>
        `;
    } catch (error) {
        workflowDetails.innerHTML = `
            <div class="emptyState">Could not load workflow: ${escapeHtml(error.message)}</div>
        `;
    }
}

document.getElementById("workflowForm").addEventListener("submit", async event => {
    event.preventDefault();
    formMessage.textContent = "";

    try {
        const name = document.getElementById("workflowName").value.trim();
        const taskData = JSON.parse(
            document.getElementById("tasksJson").value
        );

        if (!Array.isArray(taskData.tasks) || taskData.tasks.length === 0) {
            throw new Error("Provide at least one task in the JSON.");
        }

        const result = await apiRequest("/workflows", {
            method: "POST",
            body: JSON.stringify({
                name,
                tasks: taskData.tasks
            })
        });

        formMessage.textContent =
            `Success! Workflow created: ${result.workflow_id}`;

        selectedWorkflowId = result.workflow_id;
        await loadWorkflows();
        await showWorkflowDetails(result.workflow_id);

    } catch (error) {
        formMessage.textContent =
            `Error: ${error instanceof SyntaxError
                ? "Invalid JSON. Check the task format."
                : error.message}`;
    }
});

workflowList.addEventListener("click", async event => {
    const detailsButton = event.target.closest("button[data-workflow-id]");
    const runButton = event.target.closest("button[data-run-id]");

    if (detailsButton) {
        await showWorkflowDetails(detailsButton.dataset.workflowId);
    }

    if (runButton) {
        const workflowId = runButton.dataset.runId;

        try {
            if (runButton.textContent.trim() !== "Run Workflow") {
                return;
            }
            runButton.disabled = true;
            runButton.textContent = "Starting...";

            const result = await apiRequest(
                `/workflows/${encodeURIComponent(workflowId)}/run`,
                { method: "POST" }
            );

            formMessage.textContent = result.message;
            await loadWorkflows();
            await showWorkflowDetails(workflowId);
        } catch (error) {
            formMessage.textContent = `Error: ${error.message}`;
        }
    }
});

document.getElementById("refreshButton").addEventListener("click", async () => {
    await checkConnection();
    await loadWorkflows();
    if (selectedWorkflowId) {
        await showWorkflowDetails(selectedWorkflowId);
    }
});

async function initializeDashboard() {
    await checkConnection();
    await loadWorkflows();
}

setInterval(async () => {
    await checkConnection();
    await loadWorkflows({ silent: true });

    if (selectedWorkflowId) {
        await showWorkflowDetails(selectedWorkflowId);
    }
}, 3000);

initializeDashboard();
