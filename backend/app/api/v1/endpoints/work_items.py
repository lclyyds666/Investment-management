from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Response
from app.schemas.work_item import WorkItemOut
from app.services.work_items import build_work_items

router = APIRouter()


@router.get('', response_model=Response[list[WorkItemOut]])
def list_work_items(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return Response.ok(build_work_items(db, current_user))
