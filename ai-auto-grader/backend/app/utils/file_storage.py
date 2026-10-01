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


# ---------------- 答卷导入相关 ----------------

def get_batch_dir(exam_id: UUID, batch_id: UUID, sub: str = "") -> Path:
    """批次文件目录：exams/<exam_id>/imports/<batch_id>/<sub>"""
    path = get_exam_storage_dir(exam_id) / "imports" / str(batch_id)
    if sub:
        path = path / sub
    return ensure_dir(path)


def relative_to_root(path: Path) -> str:
    return str(Path(path).resolve().relative_to(Path(settings.STORAGE_ROOT).resolve()))


def absolute_path(relative_path: str) -> Path:
    return Path(settings.STORAGE_ROOT) / relative_path


def save_upload_to(file: UploadFile, target_dir: Path, filename: str) -> str:
    """把上传文件保存到指定目录，返回相对 STORAGE_ROOT 的路径。"""
    ensure_dir(target_dir)
    target = target_dir / filename
    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return relative_to_root(target)
