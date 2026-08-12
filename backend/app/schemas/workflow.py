from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import WorkflowAction


class WorkflowCandidate(BaseModel):
    user_id: int
    full_name: str
    assignment_id: int
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


class WorkflowStartRequest(BaseModel):
    designated_users: dict[str, int] = Field(default_factory=dict)


class WorkflowTimelineAction(BaseModel):
    id: int
    task_id: int
    node_code: str
    node_name: str
    action: WorkflowAction
    actor_id: int
    actor_name: str
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str
    comment: str
    previous_assignee_id: int | None
    previous_assignee_name: str | None
    new_assignee_id: int | None
    new_assignee_name: str | None
    reason: str
    returned_to_sequence: int | None
    created_at: datetime
