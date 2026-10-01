from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.core.permissions import require_permission, has_permission
from app.models.user import User
from app.models.exam import Exam
from app.models.template import AnswerCardTemplate
from app.models.template_page import TemplatePage
from app.models.template_config import TemplateRegion, ChoiceAnswer, AIScoringConfig
from app.schemas.template import (
    TemplateCreate,
    TemplateUpdate,
    TemplateOut,
    TemplateDetailOut,
    TemplateCopyRequest,
    TemplateRegionCreate,
    TemplateRegionOut,
    ChoiceAnswerBatch,
    ChoiceAnswerOut,
    AIScoringConfigBatch,
    AIScoringConfigOut,
    TemplateImportRequest,
    PrecheckIssue,
    PrecheckResult,
    TemplatePageOut,
    TemplatePageUpdate,
    TemplatePageUploadResult,
    ChoiceGridRequest,
    ChoiceGridOut,
    DigitGridRequest,
    DigitGridOut,
)
from app.services.template_service import render_answer_card_pdf
from app.services import choice_grid_service, template_page_service

router = APIRouter(prefix="/templates", tags=["Templates"])


def _get_template_or_404(db: Session, template_id: UUID) -> AnswerCardTemplate:
    tpl = db.query(AnswerCardTemplate).filter(AnswerCardTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return tpl


def _require_template_edit(current_user: User) -> None:
    if not (has_permission(current_user.role, "template:update") or has_permission(current_user.role, "template:create")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


@router.get("", response_model=List[TemplateOut])
def list_templates(
    keyword: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    query = db.query(AnswerCardTemplate)
    if keyword:
        query = query.filter(AnswerCardTemplate.name.ilike(f"%{keyword}%"))
    return query.order_by(AnswerCardTemplate.updated_at.desc()).all()


@router.post("", response_model=TemplateDetailOut)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:create")),
):
    data = payload.model_dump(exclude={"regions"})
    tpl = AnswerCardTemplate(**data, created_by=current_user.id)
    db.add(tpl)
    db.flush()

    regions = payload.regions or []
    for r in regions:
        db.add(TemplateRegion(**r.model_dump(), template_id=tpl.id))

    db.commit()
    db.refresh(tpl)
    return _to_detail(db, tpl)


@router.get("/{template_id}", response_model=TemplateDetailOut)
def get_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    tpl = _get_template_or_404(db, template_id)
    return _to_detail(db, tpl)


@router.put("/{template_id}", response_model=TemplateDetailOut)
def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    tpl = _get_template_or_404(db, template_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tpl, key, value)
    db.commit()
    db.refresh(tpl)
    return _to_detail(db, tpl)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:delete")),
):
    tpl = _get_template_or_404(db, template_id)
    used = db.query(Exam).filter(Exam.answer_card_template_id == template_id).first()
    if used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="模板已被考试引用，无法删除",
        )
    db.query(TemplateRegion).filter(TemplateRegion.template_id == template_id).delete()
    db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template_id).delete()
    db.query(AIScoringConfig).filter(AIScoringConfig.template_id == template_id).delete()
    db.delete(tpl)
    db.commit()
    return None


@router.post("/{template_id}/copy", response_model=TemplateDetailOut)
def copy_template(
    template_id: UUID,
    payload: TemplateCopyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:create")),
):
    src = _get_template_or_404(db, template_id)
    new_tpl = AnswerCardTemplate(
        name=payload.name or f"{src.name} 副本",
        subject=src.subject,
        source_type=src.source_type,
        orientation=src.orientation,
        page_sizes=src.page_sizes,
        paper_size=src.paper_size,
        duplex=src.duplex,
        page_count=src.page_count,
        margin_top=src.margin_top,
        margin_bottom=src.margin_bottom,
        margin_left=src.margin_left,
        margin_right=src.margin_right,
        title=src.title,
        exam_number_digits=src.exam_number_digits,
        exam_number_mode=src.exam_number_mode,
        class_prefix_enabled=src.class_prefix_enabled,
        name_ocr_enabled=src.name_ocr_enabled,
        tilt_threshold=src.tilt_threshold,
        perspective_enabled=src.perspective_enabled,
        deskew_enabled=src.deskew_enabled,
        is_blank=src.is_blank,
        description=src.description,
        created_by=current_user.id,
    )
    db.add(new_tpl)
    db.flush()

    for r in db.query(TemplateRegion).filter(TemplateRegion.template_id == template_id).all():
        db.add(TemplateRegion(
            template_id=new_tpl.id,
            page_index=r.page_index,
            region_type=r.region_type,
            question_number=r.question_number,
            sub_question_number=r.sub_question_number,
            max_score=r.max_score,
            x=r.x, y=r.y, width=r.width, height=r.height,
            options_count=r.options_count,
            allow_multiple=r.allow_multiple,
            partial_score_rules=r.partial_score_rules,
            knowledge_tags=r.knowledge_tags,
            config=r.config,
            group_key=r.group_key,
            option_spec=r.option_spec,
        ))

    template_page_service.copy_pages(db, template_id, new_tpl.id)

    for a in db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template_id).all():
        db.add(ChoiceAnswer(
            template_id=new_tpl.id,
            question_number=a.question_number,
            correct_options=a.correct_options,
            score=a.score,
            partial_score_rules=a.partial_score_rules,
        ))

    for c in db.query(AIScoringConfig).filter(AIScoringConfig.template_id == template_id).all():
        db.add(AIScoringConfig(
            template_id=new_tpl.id,
            question_number=c.question_number,
            standard_answer=c.standard_answer,
            scoring_points=c.scoring_points,
            deduction_notes=c.deduction_notes,
            prompt_template=c.prompt_template,
            confidence_threshold=c.confidence_threshold,
            score_tolerance=c.score_tolerance,
            enabled=c.enabled,
        ))

    db.commit()
    db.refresh(new_tpl)
    return _to_detail(db, new_tpl)


# ---------------- 区域管理 ----------------

@router.get("/{template_id}/regions", response_model=List[TemplateRegionOut])
def list_regions(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    _get_template_or_404(db, template_id)
    return (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == template_id)
        .order_by(TemplateRegion.page_index, TemplateRegion.y, TemplateRegion.x)
        .all()
    )


@router.put("/{template_id}/regions", response_model=List[TemplateRegionOut])
def replace_regions(
    template_id: UUID,
    payload: List[TemplateRegionCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    _get_template_or_404(db, template_id)
    db.query(TemplateRegion).filter(TemplateRegion.template_id == template_id).delete()
    for r in payload:
        db.add(TemplateRegion(**r.model_dump(), template_id=template_id))
    db.commit()
    return (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == template_id)
        .order_by(TemplateRegion.page_index, TemplateRegion.y, TemplateRegion.x)
        .all()
    )


# ---------------- 选择题答案 ----------------

@router.get("/{template_id}/choice-answers", response_model=List[ChoiceAnswerOut])
def list_choice_answers(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    _get_template_or_404(db, template_id)
    return (
        db.query(ChoiceAnswer)
        .filter(ChoiceAnswer.template_id == template_id)
        .order_by(ChoiceAnswer.question_number)
        .all()
    )


@router.put("/{template_id}/choice-answers", response_model=List[ChoiceAnswerOut])
def replace_choice_answers(
    template_id: UUID,
    payload: ChoiceAnswerBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    _get_template_or_404(db, template_id)
    db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template_id).delete()
    for a in payload.answers:
        db.add(ChoiceAnswer(**a.model_dump(), template_id=template_id))
    db.commit()
    return (
        db.query(ChoiceAnswer)
        .filter(ChoiceAnswer.template_id == template_id)
        .order_by(ChoiceAnswer.question_number)
        .all()
    )


# ---------------- AI 评分配置 ----------------

@router.get("/{template_id}/ai-configs", response_model=List[AIScoringConfigOut])
def list_ai_configs(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    _get_template_or_404(db, template_id)
    return (
        db.query(AIScoringConfig)
        .filter(AIScoringConfig.template_id == template_id)
        .order_by(AIScoringConfig.question_number)
        .all()
    )


@router.put("/{template_id}/ai-configs", response_model=List[AIScoringConfigOut])
def replace_ai_configs(
    template_id: UUID,
    payload: AIScoringConfigBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    _get_template_or_404(db, template_id)
    db.query(AIScoringConfig).filter(AIScoringConfig.template_id == template_id).delete()
    for c in payload.configs:
        db.add(AIScoringConfig(**c.model_dump(), template_id=template_id))
    db.commit()
    return (
        db.query(AIScoringConfig)
        .filter(AIScoringConfig.template_id == template_id)
        .order_by(AIScoringConfig.question_number)
        .all()
    )


# ---------------- 标注式底图页（上传真实答题卡） ----------------

@router.post("/{template_id}/pages", response_model=TemplatePageUploadResult)
def upload_template_pages(
    template_id: UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    """上传真实答题卡（图片 / PDF）作为模板底图。

    PDF 自动读取页数并逐页登记；原图按上传尺寸保存，不做缩放。
    """
    tpl = _get_template_or_404(db, template_id)
    added, pages = template_page_service.upload_pages(db, tpl, files)
    return TemplatePageUploadResult(
        added=added,
        pages=[TemplatePageOut.model_validate(p) for p in pages],
    )


@router.get("/{template_id}/pages", response_model=List[TemplatePageOut])
def list_template_pages(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    _get_template_or_404(db, template_id)
    return template_page_service.list_pages(db, template_id)


@router.patch("/{template_id}/pages/{page_index}", response_model=TemplatePageOut)
def update_template_page(
    template_id: UUID,
    page_index: int,
    payload: TemplatePageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    """人工覆盖底图页的空白页标识。"""
    tpl = _get_template_or_404(db, template_id)
    return template_page_service.update_page(db, tpl, page_index, payload.is_blank)


@router.delete("/{template_id}/pages/{page_index}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_page(
    template_id: UUID,
    page_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    tpl = _get_template_or_404(db, template_id)
    template_page_service.delete_page(db, tpl, page_index)
    return None


@router.get("/{template_id}/pages/{page_index}/image")
def get_template_page_image(
    template_id: UUID,
    page_index: int,
    thumb: bool = Query(default=True, description="true 返回画布缩略图，false 返回原图"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    _get_template_or_404(db, template_id)
    data, media = template_page_service.page_image_bytes(db, template_id, page_index, thumb=thumb)
    return Response(content=data, media_type=media, headers={"Cache-Control": "no-cache"})


@router.get("/{template_id}/pages/{page_index}/crop")
def crop_template_page(
    template_id: UUID,
    page_index: int,
    x: float = Query(...),
    y: float = Query(...),
    width: float = Query(...),
    height: float = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    """裁剪预览：按相对坐标返回底图局部，用于核对框选与气泡是否对准。"""
    _get_template_or_404(db, template_id)
    data = template_page_service.crop_preview(db, template_id, page_index, x, y, width, height)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-cache"})


# ---------------- 选择题自动切格 ----------------

@router.post("/{template_id}/choice-grid", response_model=ChoiceGridOut)
def build_choice_grid(
    template_id: UUID,
    payload: ChoiceGridRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    """把框选出的选择题大区自动切成"一题一区域"，并生成气泡坐标。

    返回的区域尚未入库：前端可先渲染、微调气泡位置，确认后再保存模板。
    """
    _get_template_or_404(db, template_id)
    try:
        page = template_page_service.get_page(db, template_id, payload.page_index)
    except HTTPException:
        page = None

    regions = choice_grid_service.build_choice_grid(
        {
            "x": float(payload.x),
            "y": float(payload.y),
            "width": float(payload.width),
            "height": float(payload.height),
        },
        page_index=payload.page_index,
        start_question=payload.start_question,
        question_count=payload.question_count,
        options_count=payload.options_count,
        columns=payload.columns,
        direction=payload.direction,
        score=float(payload.score),
        page_width_px=page.width_px if page else 0,
        page_height_px=page.height_px if page else 0,
    )
    return ChoiceGridOut(regions=[TemplateRegionCreate(**r) for r in regions])


@router.post("/{template_id}/digit-grid", response_model=DigitGridOut)
def build_digit_grid(
    template_id: UUID,
    payload: DigitGridRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:update")),
):
    """为考号区生成填涂格坐标（位数 × 10 行），供真实答题卡精确采样。

    返回的 option_spec 由前端挂到考号区后随模板保存。
    """
    _get_template_or_404(db, template_id)
    spec = choice_grid_service.build_digit_grid(
        {
            "x": float(payload.x),
            "y": float(payload.y),
            "width": float(payload.width),
            "height": float(payload.height),
        },
        digits=payload.digits,
    )
    return DigitGridOut(option_spec=spec)


# ---------------- 导出与备份 ----------------

@router.get("/{template_id}/export-pdf")
def export_answer_card_pdf(
    template_id: UUID,
    watermark: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    tpl = _get_template_or_404(db, template_id)
    regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == template_id).all()
    if tpl.source_type == "annotated":
        # 标注式模板：直接以底图页合成为 PDF，保留原始版面
        pdf_bytes = template_page_service.render_annotated_pdf(db, tpl)
    else:
        pdf_bytes = render_answer_card_pdf(tpl, regions, watermark=watermark)
    filename = f"answer_card_{template_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{template_id}/backup")
def backup_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    tpl = _get_template_or_404(db, template_id)
    return _to_backup(db, tpl)


@router.post("/import-backup", response_model=TemplateDetailOut)
def import_template_backup(
    payload: TemplateImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:create")),
):
    data = payload.payload or {}
    meta = data.get("template", {})
    if not meta.get("name"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="备份文件缺少模板名称")

    allowed = {
        "name", "subject", "paper_size", "duplex", "page_count",
        "margin_top", "margin_bottom", "margin_left", "margin_right",
        "title", "exam_number_digits", "exam_number_mode",
        "class_prefix_enabled", "name_ocr_enabled", "tilt_threshold",
        "perspective_enabled", "deskew_enabled", "description",
    }
    tpl = AnswerCardTemplate(
        **{k: v for k, v in meta.items() if k in allowed},
        created_by=current_user.id,
    )
    db.add(tpl)
    db.flush()

    for r in data.get("regions", []):
        region_data = {k: v for k, v in r.items() if k in {
            "page_index", "region_type", "question_number", "sub_question_number",
            "max_score", "x", "y", "width", "height", "options_count",
            "allow_multiple", "partial_score_rules", "knowledge_tags", "config",
        }}
        db.add(TemplateRegion(**region_data, template_id=tpl.id))

    for a in data.get("choice_answers", []):
        answer_data = {k: v for k, v in a.items() if k in {
            "question_number", "correct_options", "score", "partial_score_rules",
        }}
        db.add(ChoiceAnswer(**answer_data, template_id=tpl.id))

    for c in data.get("ai_configs", []):
        config_data = {k: v for k, v in c.items() if k in {
            "question_number", "standard_answer", "scoring_points", "deduction_notes",
            "prompt_template", "confidence_threshold", "score_tolerance", "enabled",
        }}
        db.add(AIScoringConfig(**config_data, template_id=tpl.id))

    db.commit()
    db.refresh(tpl)
    return _to_detail(db, tpl)


# ---------------- 模板预校验 ----------------

@router.post("/{template_id}/precheck", response_model=PrecheckResult)
def precheck_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("template:list")),
):
    """模板单样例预校验：检查区域坐标、覆盖度与答案/AI 配置一致性。

    在正式打印答题卡或批量导入答卷前给出配置级校验结果。
    """
    tpl = _get_template_or_404(db, template_id)
    regions = (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == template_id)
        .order_by(TemplateRegion.page_index, TemplateRegion.y, TemplateRegion.x)
        .all()
    )
    answers = db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == template_id).all()
    ai_configs = db.query(AIScoringConfig).filter(AIScoringConfig.template_id == template_id).all()

    issues: List[PrecheckIssue] = []

    def add(level: str, code: str, message: str, page_index=None, region_index=None):
        issues.append(PrecheckIssue(
            level=level, code=code, message=message,
            page_index=page_index, region_index=region_index,
        ))

    if not regions:
        add("warning", "no_region", "模板尚未绘制任何识别区域")

    # 1. 逐区域坐标与必填项校验
    for idx, r in enumerate(regions):
        page = r.page_index
        if page < 0 or page >= max(1, tpl.page_count):
            add("error", "page_out_of_range", f"区域所在页码 {page + 1} 超出模板页数", page, idx)
        x, y = float(r.x), float(r.y)
        w, h = float(r.width), float(r.height)
        if w <= 0 or h <= 0:
            add("error", "invalid_size", "区域宽高必须大于 0", page, idx)
        if x < 0 or y < 0 or x + w > 1000 or y + h > 1000:
            add("error", "out_of_bounds", "区域超出页面有效范围（0~1000）", page, idx)
        if r.region_type == "choice":
            if not r.question_number:
                add("warning", "choice_no_number", "选择题区域未填写题号", page, idx)
        elif r.region_type == "subjective":
            if not r.question_number:
                add("warning", "subjective_no_number", "非选择题区域未填写题号", page, idx)
            if float(r.max_score or 0) <= 0:
                add("warning", "subjective_no_score", "非选择题区域未设置分值", page, idx)

    # 2. 同页区域重叠检测
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            a, b = regions[i], regions[j]
            if a.page_index != b.page_index:
                continue
            if _overlap_ratio(a, b) > 0.15:
                add(
                    "warning", "region_overlap",
                    f"区域「{_region_label(a)}」与「{_region_label(b)}」存在明显重叠",
                    a.page_index, i,
                )

    # 3. 选择题答案覆盖校验
    choice_numbers = {r.question_number for r in regions if r.region_type == "choice" and r.question_number}
    answer_numbers = {a.question_number for a in answers}
    for q in sorted(choice_numbers - answer_numbers):
        add("warning", "missing_answer", f"选择题 {q} 未配置标准答案")
    for q in sorted(answer_numbers - choice_numbers):
        add("warning", "orphan_answer", f"标准答案 {q} 找不到对应的选择题区域")

    # 4. AI 评分规则覆盖校验
    subjective_numbers = {r.question_number for r in regions if r.region_type == "subjective" and r.question_number}
    for c in ai_configs:
        if subjective_numbers and c.question_number not in subjective_numbers:
            add("warning", "orphan_ai_config", f"AI 评分规则 {c.question_number} 找不到对应的非选择题区域")

    # 5. 考号区校验
    if not any(r.region_type == "exam_number" for r in regions):
        add("warning", "no_exam_number", "未绘制考号区，系统将无法自动识别考号")

    error_count = sum(1 for i in issues if i.level == "error")
    warning_count = sum(1 for i in issues if i.level == "warning")
    return PrecheckResult(
        passed=error_count == 0,
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )


# ---------------- helpers ----------------

def _region_label(r) -> str:
    labels = {"exam_number": "考号区", "name": "姓名区", "choice": "选择题", "subjective": "非选择题"}
    base = labels.get(r.region_type, r.region_type)
    return f"{base} {r.question_number}" if r.question_number else base


def _overlap_ratio(a, b) -> float:
    ax1, ay1 = float(a.x), float(a.y)
    ax2, ay2 = ax1 + float(a.width), ay1 + float(a.height)
    bx1, by1 = float(b.x), float(b.y)
    bx2, by2 = bx1 + float(b.width), by1 + float(b.height)
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    smaller = min(float(a.width) * float(a.height), float(b.width) * float(b.height))
    return inter / smaller if smaller > 0 else 0.0


def _to_detail(db: Session, tpl: AnswerCardTemplate) -> TemplateDetailOut:
    regions = (
        db.query(TemplateRegion)
        .filter(TemplateRegion.template_id == tpl.id)
        .order_by(TemplateRegion.page_index, TemplateRegion.y, TemplateRegion.x)
        .all()
    )
    detail = TemplateDetailOut.model_validate(tpl)
    detail.regions = [TemplateRegionOut.model_validate(r) for r in regions]
    return detail


def _to_backup(db: Session, tpl: AnswerCardTemplate) -> dict:
    regions = db.query(TemplateRegion).filter(TemplateRegion.template_id == tpl.id).all()
    answers = db.query(ChoiceAnswer).filter(ChoiceAnswer.template_id == tpl.id).all()
    ai_configs = db.query(AIScoringConfig).filter(AIScoringConfig.template_id == tpl.id).all()

    def _region(r):
        return {
            "page_index": r.page_index,
            "region_type": r.region_type,
            "question_number": r.question_number,
            "sub_question_number": r.sub_question_number,
            "max_score": float(r.max_score) if r.max_score is not None else 0,
            "x": float(r.x), "y": float(r.y),
            "width": float(r.width), "height": float(r.height),
            "options_count": r.options_count,
            "allow_multiple": r.allow_multiple,
            "partial_score_rules": r.partial_score_rules,
            "knowledge_tags": r.knowledge_tags,
            "config": r.config,
        }

    return {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "template": {
            "name": tpl.name,
            "subject": tpl.subject,
            "paper_size": tpl.paper_size,
            "duplex": tpl.duplex,
            "page_count": tpl.page_count,
            "margin_top": float(tpl.margin_top),
            "margin_bottom": float(tpl.margin_bottom),
            "margin_left": float(tpl.margin_left),
            "margin_right": float(tpl.margin_right),
            "title": tpl.title,
            "exam_number_digits": tpl.exam_number_digits,
            "exam_number_mode": tpl.exam_number_mode,
            "class_prefix_enabled": tpl.class_prefix_enabled,
            "name_ocr_enabled": tpl.name_ocr_enabled,
            "tilt_threshold": float(tpl.tilt_threshold),
            "perspective_enabled": tpl.perspective_enabled,
            "deskew_enabled": tpl.deskew_enabled,
            "description": tpl.description,
        },
        "regions": [_region(r) for r in regions],
        "choice_answers": [
            {
                "question_number": a.question_number,
                "correct_options": a.correct_options,
                "score": float(a.score) if a.score is not None else 0,
                "partial_score_rules": a.partial_score_rules,
            }
            for a in answers
        ],
        "ai_configs": [
            {
                "question_number": c.question_number,
                "standard_answer": c.standard_answer,
                "scoring_points": c.scoring_points,
                "deduction_notes": c.deduction_notes,
                "prompt_template": c.prompt_template,
                "confidence_threshold": float(c.confidence_threshold),
                "score_tolerance": float(c.score_tolerance),
                "enabled": c.enabled,
            }
            for c in ai_configs
        ],
    }