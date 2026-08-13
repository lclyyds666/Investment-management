from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import WorkflowAction, WorkflowAssigneeMode, WorkflowTaskStatus


class WorkflowCandidate(BaseModel):
    user_id: int
    full_name: str
    assignment_id: int
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str
    valid_from: date
    valid_until: date | None


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


class WorkflowTimelineUser(BaseModel):
    id: int
    full_name: str


class WorkflowTimelineTask(BaseModel):
    id: int
    sequence: int
    node_code: str
    node_name: str
    mode: WorkflowAssigneeMode
    required_position_code: str
    required_position_name: str
    designated_user: WorkflowTimelineUser | None
    status: WorkflowTaskStatus
    activated_at: datetime | None
    completed_at: datetime | None
    actions: list[WorkflowTimelineAction]
