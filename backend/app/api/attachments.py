import io
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pypdf import PdfReader

from app.api.deps import CsrfProtected, CurrentUser, Db
from app.models import Attachment

router = APIRouter(prefix="/attachments", tags=["Attachments"])
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("ATTACHMENT_ENCODING_INVALID") from exc
    elif suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("ATTACHMENT_PDF_INVALID") from exc
    else:
        raise ValueError("ATTACHMENT_TYPE_NOT_ALLOWED")
    text = text.strip()
    if not text:
        raise ValueError("ATTACHMENT_HAS_NO_TEXT")
    return text[:100_000]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
    file: UploadFile = File(),
) -> dict[str, object]:
    safe_name = Path(file.filename or "").name
    if not safe_name or Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="ATTACHMENT_TYPE_NOT_ALLOWED")
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="ATTACHMENT_TOO_LARGE")
    try:
        text = extract_text(safe_name, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = Attachment(
        user_id=user.id,
        filename=safe_name,
        media_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        extracted_text=text,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return envelope(
        request,
        {
            "id": item.id,
            "filename": item.filename,
            "media_type": item.media_type,
            "size_bytes": item.size_bytes,
        },
    )
