from fastapi import APIRouter

from app.api.attachments import router as attachments_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.diagnosis import router as diagnosis_router
from app.api.fault_cases import router as fault_cases_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.messages import router as messages_router
from app.api.model_config import router as model_config_router
from app.api.remediation import router as remediation_router
from app.api.runs import router as runs_router
from app.api.workflows import router as workflows_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(conversations_router)
router.include_router(messages_router)
router.include_router(runs_router)
router.include_router(mcp_router)
router.include_router(diagnosis_router)
router.include_router(model_config_router)
router.include_router(attachments_router)
router.include_router(knowledge_router)
router.include_router(fault_cases_router)
router.include_router(remediation_router)
router.include_router(workflows_router)
