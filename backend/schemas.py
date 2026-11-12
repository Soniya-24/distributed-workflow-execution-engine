
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    task_type: str = "echo"
    payload: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate dependencies are not allowed")
        return value


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tasks: list[TaskCreate] = Field(min_length=1)


class TaskResponse(BaseModel):
    id: str
    name: str
    task_type: str
    payload: dict[str, Any]
    dependencies: list[str]
    status: str
    result: dict[str, Any] | None
    error: str | None
    attempts: int


class WorkflowResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: Any
    tasks: list[TaskResponse]
