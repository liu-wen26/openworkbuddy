import os
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_exam_storage_dir(exam_id: UUID) -> Path:
    path = Path(settings.STORAGE_ROOT) / "exams" / str(exam_id)
    return ensure_dir(path)


def get_original_paper_path(exam_id: UUID) -> Path:
    return get_exam_storage_dir(exam_id) / "original_paper.pdf"


def save_original_paper(exam_id: UUID, file: UploadFile) -> str:
    target = get_original_paper_path(exam_id)
    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return str(target.relative_to(Path(settings.STORAGE_ROOT)))


def delete_original_paper(exam_id: UUID) -> None:
    target = get_original_paper_path(exam_id)
    if target.exists():
        target.unlink()
