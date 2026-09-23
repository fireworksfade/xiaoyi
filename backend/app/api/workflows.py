from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.common import envelope
from app.api.deps import CurrentUser, Db
from app.models import OperationWorkflow, OperationWorkflowStep
from app.services.workflows import workflow_view

router = APIRouter(prefix="/operation-workflows", tags=["operation-workflows"])


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str, request: Request, db: Db, user: CurrentUser
) -> dict[str, object]:
    workflow = await db.scalar(
        select(OperationWorkflow).where(
            OperationWorkflow.id == workflow_id,
            OperationWorkflow.user_id == user.id,
        )
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WORKFLOW_NOT_FOUND")
    steps = list(
        (
            await db.scalars(
                select(OperationWorkflowStep)
                .where(OperationWorkflowStep.workflow_id == workflow.id)
                .order_by(OperationWorkflowStep.sequence)
            )
        ).all()
    )
    return envelope(request, workflow_view(workflow, steps))
