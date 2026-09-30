"""考试归档服务（F10-04）。

归档 = 打包「原试卷 + 成绩明细 Excel + 学情报告 HTML」到考试归档目录，
并把考试状态置为 archived；支持列表查看、下载归档包、恢复与删除。
"""

import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.answer_block import AnswerBlock
from app.models.choice_result import ChoiceResult
from app.models.exam import Exam
from app.models.exam_archive import ExamArchive
from app.models.exception import ExamException
from app.models.student import ExamStudent
from app.models.subjective_result import SubjectiveResult
from app.services import analytics_service, export_service
from app.utils.file_storage import absolute_path, get_exam_storage_dir, relative_to_root

logger = logging.getLogger(__name__)


def _exam_or_404(db: Session, exam_id: UUID) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def _snapshot(db: Session, exam: Exam) -> dict:
    overview = analytics_service.overview(db, exam.id)
    return {
        "roster_count": overview["roster_count"],
        "appeared_count": overview["appeared_count"],
        "avg_score": overview["avg_score"],
        "pass_rate": overview["pass_rate"],
        "excellent_rate": overview["excellent_rate"],
        "student_count": db.query(ExamStudent).filter(ExamStudent.exam_id == exam.id).count(),
        "choice_result_count": db.query(ChoiceResult).filter(ChoiceResult.exam_id == exam.id).count(),
        "subjective_result_count": db.query(SubjectiveResult).filter(SubjectiveResult.exam_id == exam.id).count(),
        "block_count": db.query(AnswerBlock).filter(AnswerBlock.exam_id == exam.id).count(),
        "exception_count": db.query(ExamException).filter(ExamException.exam_id == exam.id).count(),
        "original_paper_included": bool(exam.original_paper_path),
    }


def create_archive(db: Session, exam_id: UUID, user) -> ExamArchive:
    exam = _exam_or_404(db, exam_id)
    if exam.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="考试已归档")

    snapshot = _snapshot(db, exam)

    # 打包：原试卷 + 成绩明细 + 学情报告
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as zf:
        if exam.original_paper_path:
            paper = absolute_path(exam.original_paper_path)
            if paper.exists():
                zf.writestr("原试卷.pdf", paper.read_bytes())
        try:
            detail, detail_name = export_service.build_grade_detail(db, exam_id)
            zf.writestr(f"成绩明细/{detail_name}", detail)
        except Exception as exc:  # noqa: BLE001
            logger.warning("归档时生成成绩明细失败: %s", exc)
        try:
            html, html_name = export_service.build_report_html(db, exam_id)
            zf.writestr(f"学情报告/{html_name}", html)
        except Exception as exc:  # noqa: BLE001
            logger.warning("归档时生成学情报告失败: %s", exc)
        manifest = (
            f"考试：{exam.name}\n科目：{exam.subject}\n年级：{exam.grade}\n"
            f"归档时间：{datetime.now(timezone.utc).isoformat()}\n"
            f"应考：{snapshot['roster_count']}  实考：{snapshot['appeared_count']}  "
            f"平均分：{snapshot['avg_score']}\n"
        )
        zf.writestr("归档说明.txt", manifest)

    bundle_dir = get_exam_storage_dir(exam.id) / "archives"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_file = bundle_dir / f"archive_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    bundle_file.write_bytes(stream.getvalue())

    archive = ExamArchive(
        exam_id=exam.id,
        exam_name=exam.name,
        previous_status=exam.status,
        status="archived",
        bundle_path=relative_to_root(bundle_file),
        file_size=bundle_file.stat().st_size,
        original_paper_included=bool(exam.original_paper_path),
        snapshot=snapshot,
        created_by=user.id if user else None,
    )
    db.add(archive)
    exam.status = "archived"
    db.commit()
    db.refresh(archive)
    return archive


def list_archives(db: Session, include_restored: bool = True) -> List[ExamArchive]:
    query = db.query(ExamArchive)
    if not include_restored:
        query = query.filter(ExamArchive.status == "archived")
    return query.order_by(ExamArchive.created_at.desc()).all()


def get_archive_or_404(db: Session, archive_id: UUID) -> ExamArchive:
    archive = db.query(ExamArchive).filter(ExamArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="归档记录不存在")
    return archive


def get_bundle(archive: ExamArchive) -> tuple[bytes, str]:
    if not archive.bundle_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="归档包不存在")
    path = absolute_path(archive.bundle_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="归档包文件已丢失")
    return path.read_bytes(), f"{archive.exam_name}_归档_{archive.id}.zip"


def restore_archive(db: Session, archive_id: UUID, user) -> ExamArchive:
    archive = get_archive_or_404(db, archive_id)
    if archive.status != "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该归档已恢复")
    exam = db.query(Exam).filter(Exam.id == archive.exam_id).first()
    if exam:
        exam.status = archive.previous_status or "draft"
    archive.status = "restored"
    archive.restored_by = user.id if user else None
    archive.restored_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(archive)
    return archive


def delete_archive(db: Session, archive_id: UUID) -> None:
    archive = get_archive_or_404(db, archive_id)
    if archive.bundle_path:
        path = absolute_path(archive.bundle_path)
        if path.exists():
            path.unlink()
    db.delete(archive)
    db.commit()