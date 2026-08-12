from pydantic import BaseModel


class WorkflowCandidate(BaseModel):
    user_id: int
    full_name: str
    assignment_id: int
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


class WorkflowStartRequest(BaseModel):
    designated_users: dict[str, int]
