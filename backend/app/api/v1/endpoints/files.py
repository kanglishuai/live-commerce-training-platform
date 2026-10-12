"""文件上传：统一入口，受控访问（静态目录由 main.py 挂载）。

白名单扩展名 + 大小上限；文件名重命名为 UUID，避免路径穿越与重名覆盖。
生产环境应替换为对象存储（题目第 5.5 节预留了该扩展点）。
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile

from app.core import errors
from app.core.config import get_settings
from app.core.deps import CurrentUser

router = APIRouter(tags=["文件"])

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".docx", ".pptx", ".mp3", ".wav", ".webm", ".mp4"}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("/files", summary="上传文件（图片/文档/音频）")
async def upload_file(user: CurrentUser, file: UploadFile) -> dict:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise errors.validation_error(
            f"不支持的文件类型 {suffix}", {"allowed": sorted(ALLOWED_EXT)}
        )
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise errors.validation_error(
            f"文件超过大小上限 {MAX_SIZE_BYTES // 1024 // 1024}MB", {"size": len(content)}
        )
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{suffix}"
    (upload_dir / name).write_bytes(content)
    return {
        "file_id": name,
        "url": f"/static/{name}",
        "size": len(content),
        "uploaded_by": user.id,
    }
