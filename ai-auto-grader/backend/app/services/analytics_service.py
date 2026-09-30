"""学情分析报表服务（F8 系列）。

在阅卷完成后，基于正式判分数据（choice_results / subjective_results / students /
template_regions）按需聚合出多维度学情报表：

- F8-01 年级整场考试总览（分数分布、及格率、优秀率、班级对比）
- F8-02 分班级学情报表
- F8-03 题目维度分析（得分率、难度、区分度、选项分布、高频错误）
- F8-04 知识点掌握情况（依据模板区域的 knowledge_tags）
- F8-05 学生个人学情报告
- F8-06 讲评素材（优秀作答 / 典型错误 / 高频错题）

报表按需计算，不写入额外表；原始作答图复用已有的题块图像接口。
"""

import math
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.choice_result import ChoiceResult
from app.models.exam import Exam
from app.models.student import ExamStudent, Student
from app.models.subjective_result import SubjectiveResult
from app.models.template import AnswerCardTemplate
from app.models.template_config import TemplateRegion
from app.services.choice_service import _question_sort_key

# 掌握等级阈值（得分率）
MASTERED = 0.85
BASIC = 0.6


# ---------------- 公共采集 ----------------

def _exam_or_404(db: Session, exam_id: UUID) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考试不存在")
    return exam


def _roster(db: Session, exam_id: UUID) -> List[Tuple[ExamStudent, Student]]:
    return (
        db.query(ExamStudent, Student)
        .join(Student, ExamStudent.student_id == Student.id)
        .filter(ExamStudent.exam_id == exam_id)
        .all()
    )


def _collect(db: Session, exam_id: UUID) -> dict:
    exam = _exam_or_404(db, exam_id)
    return {
        "exam": exam,
        "choice": db.query(ChoiceResult).filter(ChoiceResult.exam_id == exam_id).all(),
        "subjective": db.query(SubjectiveResult).filter(SubjectiveResult.exam_id == exam_id).all(),
        "roster": _roster(db, exam_id),
        "regions": (
            db.query(TemplateRegion).filter(TemplateRegion.template_id == exam.answer_card_template_id).all()
            if exam.answer_card_template_id
            else []
        ),
    }


def _effective_subjective(result: SubjectiveResult) -> Optional[float]:
    """非选择题有效得分：仲裁 > 双评均分 > 一评 > 二评 > AI 预评。"""
    if result.final_score is not None:
        return float(result.final_score)
    first = result.first_score
    second = result.second_score
    if first is not None and second is not None:
        return round((float(first) + float(second)) / 2, 2)
    if first is not None:
        return float(first)
    if second is not None:
        return float(second)
    if result.ai_score is not None:
        return float(result.ai_score)
    return None


def _is_graded(result: SubjectiveResult) -> bool:
    return result.final_score is not None or result.first_score is not None or result.second_score is not None


def _student_totals(data: dict) -> Dict[UUID, dict]:
    """按学生汇总总分与选择题 / 非选择题得分。"""
    totals: Dict[UUID, dict] = {}

    def bucket(sid: UUID) -> dict:
        return totals.setdefault(
            sid, {"choice": 0.0, "subjective": 0.0, "choice_max": 0.0, "subjective_max": 0.0, "ungraded": 0}
        )

    for r in data["choice"]:
        if not r.student_id:
            continue
        b = bucket(r.student_id)
        b["choice"] += float(r.score or 0)
        b["choice_max"] += float(r.max_score or 0)

    for r in data["subjective"]:
        if not r.student_id:
            continue
        b = bucket(r.student_id)
        b["subjective_max"] += float(r.max_score or 0)
        score = _effective_subjective(r)
        if score is None:
            b["ungraded"] += 1
        else:
            b["subjective"] += score

    for sid, b in totals.items():
        b["total"] = round(b["choice"] + b["subjective"], 2)
    return totals


# ---------------- 统计辅助 ----------------

def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return round(ordered[mid], 2)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return round(math.sqrt(var), 2)


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _distribution(values: List[float], total_score: float, bins: int = 10) -> List[dict]:
    """把总分按满分等分为 bins 段，返回每段人数直方图。"""
    total_score = total_score or 100.0
    width = total_score / bins
    result = []
    for i in range(bins):
        low = round(i * width, 2)
        high = round((i + 1) * width, 2)
        count = sum(1 for v in values if (low <= v < high) or (i == bins - 1 and v >= high))
        result.append({"label": f"{low:g}-{high:g}", "min": low, "max": high, "count": count})
    return result


def _thresholds(exam: Exam) -> Tuple[float, float, float]:
    total = float(exam.total_score or 0)
    pass_score = float(exam.pass_score) if exam.pass_score is not None else round(total * 0.6, 2)
    excellent = float(exam.excellent_score) if exam.excellent_score is not None else round(total * 0.85, 2)
    return total, pass_score, excellent


def _class_of(roster_map: Dict[UUID, Student], sid: UUID) -> str:
    student = roster_map.get(sid)
    return (student.class_name if student and student.class_name else "未分班")


# ---------------- F8-01 年级总览 ----------------

def overview(db: Session, exam_id: UUID) -> dict:
    data = _collect(db, exam_id)
    exam = data["exam"]
    total_score, pass_score, excellent = _thresholds(exam)

    roster_map = {es.student_id: st for es, st in data["roster"]}
    totals = _student_totals(data)

    appeared_ids = set(totals.keys())
    roster_ids = set(roster_map.keys())
    absent_ids = roster_ids - appeared_ids

    scores = [totals[sid]["total"] for sid in appeared_ids]
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    passed = sum(1 for v in scores if v >= pass_score)
    excellent_count = sum(1 for v in scores if v >= excellent)
    absent_flag = sum(1 for es, _ in data["roster"] if es.is_absent)

    # 班级对比
    class_rows: Dict[str, dict] = OrderedDict()
    for es, st in data["roster"]:
        cls = st.class_name or "未分班"
        class_rows.setdefault(cls, {"class_name": cls, "student_count": 0, "scores": [], "absent": 0})
        class_rows[cls]["student_count"] += 1

    for sid, b in totals.items():
        cls = _class_of(roster_map, sid)
        class_rows.setdefault(cls, {"class_name": cls, "student_count": 0, "scores": [], "absent": 0})
        class_rows[cls]["scores"].append(b["total"])

    for sid in absent_ids:
        cls = _class_of(roster_map, sid)
        if cls in class_rows:
            class_rows[cls]["absent"] += 1

    classes = []
    for cls, row in class_rows.items():
        cs = row["scores"]
        classes.append({
            "class_name": cls,
            "student_count": row["student_count"],
            "appeared": len(cs),
            "absent": row["absent"],
            "avg_score": round(sum(cs) / len(cs), 2) if cs else 0.0,
            "max_score": round(max(cs), 2) if cs else 0.0,
            "min_score": round(min(cs), 2) if cs else 0.0,
            "median_score": _median(cs),
            "pass_rate": _rate(sum(1 for v in cs if v >= pass_score), len(cs)),
            "excellent_rate": _rate(sum(1 for v in cs if v >= excellent), len(cs)),
        })
    classes.sort(key=lambda c: c["avg_score"], reverse=True)

    return {
        "exam_id": exam.id,
        "exam_name": exam.name,
        "subject": exam.subject,
        "grade": exam.grade,
        "total_score": total_score,
        "pass_score": pass_score,
        "excellent_score": excellent,
        "roster_count": len(roster_map),
        "appeared_count": len(appeared_ids),
        "absent_count": len(absent_ids),
        "absent_flag_count": absent_flag,
        "avg_score": avg,
        "max_score": round(max(scores), 2) if scores else 0.0,
        "min_score": round(min(scores), 2) if scores else 0.0,
        "median_score": _median(scores),
        "score_std": _std(scores),
        "pass_rate": _rate(passed, len(scores)),
        "excellent_rate": _rate(excellent_count, len(scores)),
        "distribution": _distribution(scores, total_score),
        "classes": classes,
    }


# ---------------- F8-02 班级学情 ----------------

def class_report(db: Session, exam_id: UUID) -> dict:
    data = _collect(db, exam_id)
    exam = data["exam"]
    total_score, pass_score, excellent = _thresholds(exam)

    # 题目维度元信息，用于计算各班分题型得分率
    qmeta = _question_meta(data)
    choice_q = [q for q, m in qmeta.items() if m["type"] == "choice"]
    subj_q = [q for q, m in qmeta.items() if m["type"] == "subjective"]

    roster_map = {es.student_id: st for es, st in data["roster"]}
    totals = _student_totals(data)

    by_class: Dict[str, dict] = OrderedDict()
    for es, st in data["roster"]:
        cls = st.class_name or "未分班"
        by_class.setdefault(cls, {
            "class_name": cls, "student_count": 0, "scores": [],
            "choice_sum": 0.0, "choice_max": 0.0, "subj_sum": 0.0, "subj_max": 0.0, "absent": 0,
        })
        by_class[cls]["student_count"] += 1

    for sid, b in totals.items():
        cls = _class_of(roster_map, sid)
        row = by_class.setdefault(cls, {
            "class_name": cls, "student_count": 0, "scores": [],
            "choice_sum": 0.0, "choice_max": 0.0, "subj_sum": 0.0, "subj_max": 0.0, "absent": 0,
        })
        row["scores"].append(b["total"])
        row["choice_sum"] += b["choice"]
        row["choice_max"] += b["choice_max"]
        row["subj_sum"] += b["subjective"]
        row["subj_max"] += b["subjective_max"]

    for es, st in data["roster"]:
        if es.student_id not in totals:
            by_class[st.class_name or "未分班"]["absent"] += 1

    classes = []
    for cls, row in by_class.items():
        cs = row["scores"]
        classes.append({
            "class_name": cls,
            "student_count": row["student_count"],
            "appeared": len(cs),
            "absent": row["absent"],
            "avg_score": round(sum(cs) / len(cs), 2) if cs else 0.0,
            "max_score": round(max(cs), 2) if cs else 0.0,
            "min_score": round(min(cs), 2) if cs else 0.0,
            "median_score": _median(cs),
            "pass_rate": _rate(sum(1 for v in cs if v >= pass_score), len(cs)),
            "excellent_rate": _rate(sum(1 for v in cs if v >= excellent), len(cs)),
            "choice_rate": _rate(0, 1) if not row["choice_max"] else round(row["choice_sum"] / row["choice_max"], 4),
            "subjective_rate": _rate(0, 1) if not row["subj_max"] else round(row["subj_sum"] / row["subj_max"], 4),
            "question_count": len(choice_q) + len(subj_q),
        })
    classes.sort(key=lambda c: c["avg_score"], reverse=True)
    return {
        "exam_id": exam.id,
        "total_score": total_score,
        "pass_score": pass_score,
        "excellent_score": excellent,
        "classes": classes,
    }


# ---------------- F8-03 题目分析 ----------------

def _question_meta(data: dict) -> "OrderedDict[str, dict]":
    """题号 -> 元信息（类型、满分、选项数、知识点、区域）。"""
    meta: "OrderedDict[str, dict]" = OrderedDict()
    for r in data["regions"]:
        if r.region_type not in ("choice", "subjective") or not r.question_number:
            continue
        existing = meta.get(r.question_number)
        entry = {
            "type": r.region_type,
            "max_score": float(r.max_score or 0),
            "options_count": int(r.options_count or 4),
            "allow_multiple": bool(r.allow_multiple),
            "knowledge_tags": list(r.knowledge_tags or []),
            "region_id": r.id,
        }
        if existing is None:
            meta[r.question_number] = entry
        elif existing["type"] == "choice":
            # 同题号出现多种类型时，保留选择题（通常不会发生）
            continue
        else:
            meta[r.question_number] = entry
    return OrderedDict((q, meta[q]) for q in sorted(meta.keys(), key=_question_sort_key))


def _discrimination(by_student_scores: Dict[UUID, float], totals: Dict[UUID, dict], max_ratio: float) -> float:
    """高分组与低分组得分率之差，作为题目区分度（-1~1）。"""
    students = [sid for sid in totals.keys() if sid in by_student_scores]
    if len(students) < 6:
        return 0.0
    students.sort(key=lambda sid: totals[sid]["total"], reverse=True)
    k = max(1, int(round(len(students) * 0.27)))
    top, bottom = students[:k], students[-k:]

    def rate(group: List[UUID]) -> float:
        if not group or max_ratio <= 0:
            return 0.0
        return sum(by_student_scores[sid] for sid in group) / len(group) / max_ratio

    return round(max(-1.0, min(1.0, rate(top) - rate(bottom))), 3)


def question_report(db: Session, exam_id: UUID) -> dict:
    data = _collect(db, exam_id)
    exam = data["exam"]
    qmeta = _question_meta(data)
    totals = _student_totals(data)

    # 按题号汇聚结果
    choice_by_q: Dict[str, List[ChoiceResult]] = defaultdict(list)
    for r in data["choice"]:
        choice_by_q[r.question_number or "-"].append(r)
    subj_by_q: Dict[str, List[SubjectiveResult]] = defaultdict(list)
    for r in data["subjective"]:
        subj_by_q[r.question_number or "-"].append(r)

    questions = []
    for q, meta in qmeta.items():
        if meta["type"] == "choice":
            rows = choice_by_q.get(q, [])
            answered = [r for r in rows if r.status != "exception"]
            correct = sum(1 for r in answered if r.is_correct)
            score_sum = sum(float(r.score or 0) for r in answered)
            max_score = meta["max_score"]
            per_student: Dict[UUID, float] = {}
            wrong_counter: Dict[str, int] = defaultdict(int)
            for r in answered:
                if r.student_id:
                    per_student[r.student_id] = float(r.score or 0)
                opts = (r.recognized_options or "").upper()
                if not r.is_correct and opts:
                    wrong_counter[opts] += 1
            common_wrong = [
                {"options": opts, "count": cnt}
                for opts, cnt in sorted(wrong_counter.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
            letters = [chr(ord("A") + i) for i in range(meta["options_count"])]
            distribution = {ch: 0 for ch in letters}
            for r in rows:
                for ch in (r.recognized_options or "").upper():
                    if ch in distribution:
                        distribution[ch] += 1
            questions.append({
                "question_number": q,
                "question_type": "choice",
                "max_score": max_score,
                "total": len(rows),
                "graded": len(answered),
                "exception": len(rows) - len(answered),
                "correct": correct,
                "correct_rate": _rate(correct, len(answered)),
                "avg_score": round(score_sum / len(answered), 2) if answered else 0.0,
                "score_rate": round(score_sum / len(answered) / max_score, 4) if answered and max_score else 0.0,
                "difficulty": round(score_sum / len(answered) / max_score, 4) if answered and max_score else 0.0,
                "discrimination": _discrimination(per_student, totals, max_score),
                "option_distribution": distribution,
                "common_wrong": common_wrong,
                "knowledge_tags": meta["knowledge_tags"],
            })
        else:
            rows = subj_by_q.get(q, [])
            scored = [(r, _effective_subjective(r)) for r in rows]
            scored = [(r, s) for r, s in scored if s is not None]
            score_sum = sum(s for _, s in scored)
            max_score = meta["max_score"]
            per_student = {r.student_id: s for r, s in scored if r.student_id}
            questions.append({
                "question_number": q,
                "question_type": "subjective",
                "max_score": max_score,
                "total": len(rows),
                "graded": len(scored),
                "exception": 0,
                "correct": None,
                "correct_rate": None,
                "avg_score": round(score_sum / len(scored), 2) if scored else 0.0,
                "score_rate": round(score_sum / len(scored) / max_score, 4) if scored and max_score else 0.0,
                "difficulty": round(score_sum / len(scored) / max_score, 4) if scored and max_score else 0.0,
                "discrimination": _discrimination(per_student, totals, max_score),
                "option_distribution": None,
                "common_wrong": None,
                "knowledge_tags": meta["knowledge_tags"],
            })

    # 未在模板中登记但有结果的题号
    for q in sorted(set(choice_by_q) | set(subj_by_q), key=_question_sort_key):
        if q in qmeta:
            continue
        if choice_by_q.get(q):
            rows = choice_by_q[q]
            max_score = float(rows[0].max_score or 0)
            answered = [r for r in rows if r.status != "exception"]
            correct = sum(1 for r in answered if r.is_correct)
            score_sum = sum(float(r.score or 0) for r in answered)
            questions.append({
                "question_number": q, "question_type": "choice", "max_score": max_score,
                "total": len(rows), "graded": len(answered), "exception": len(rows) - len(answered),
                "correct": correct, "correct_rate": _rate(correct, len(answered)),
                "avg_score": round(score_sum / len(answered), 2) if answered else 0.0,
                "score_rate": round(score_sum / len(answered) / max_score, 4) if answered and max_score else 0.0,
                "difficulty": round(score_sum / len(answered) / max_score, 4) if answered and max_score else 0.0,
                "discrimination": 0.0, "option_distribution": None, "common_wrong": None,
                "knowledge_tags": [],
            })
        else:
            rows = subj_by_q[q]
            scored = [(r, _effective_subjective(r)) for r in rows]
            scored = [(r, s) for r, s in scored if s is not None]
            max_score = float(rows[0].max_score or 0)
            score_sum = sum(s for _, s in scored)
            questions.append({
                "question_number": q, "question_type": "subjective", "max_score": max_score,
                "total": len(rows), "graded": len(scored), "exception": 0,
                "correct": None, "correct_rate": None,
                "avg_score": round(score_sum / len(scored), 2) if scored else 0.0,
                "score_rate": round(score_sum / len(scored) / max_score, 4) if scored and max_score else 0.0,
                "difficulty": round(score_sum / len(scored) / max_score, 4) if scored and max_score else 0.0,
                "discrimination": 0.0, "option_distribution": None, "common_wrong": None,
                "knowledge_tags": [],
            })

    high_error = sorted(
        [q for q in questions if q["graded"] > 0],
        key=lambda x: x["score_rate"],
    )[:8]

    return {
        "exam_id": exam.id,
        "total_questions": len(questions),
        "questions": questions,
        "high_error_questions": high_error,
    }


# ---------------- F8-04 知识点掌握 ----------------

def _mastery_level(rate: float) -> str:
    if rate >= MASTERED:
        return "mastered"
    if rate >= BASIC:
        return "basic"
    return "weak"


def knowledge_report(db: Session, exam_id: UUID) -> dict:
    data = _collect(db, exam_id)

    # 知识点 -> 关联题号与满分
    tag_questions: Dict[str, List[str]] = defaultdict(list)
    qmeta = _question_meta(data)
    for q, meta in qmeta.items():
        for tag in meta["knowledge_tags"]:
            if tag and q not in tag_questions[tag]:
                tag_questions[tag].append(q)

    # 题号 -> 每生得分 / 满分
    q_score: Dict[str, Dict[UUID, float]] = defaultdict(dict)
    q_max: Dict[str, float] = {}
    for r in data["choice"]:
        if r.status == "exception" or not r.student_id:
            continue
        q_score[r.question_number or "-"][r.student_id] = float(r.score or 0)
        q_max[r.question_number or "-"] = float(r.max_score or 0)
    for r in data["subjective"]:
        score = _effective_subjective(r)
        if score is None or not r.student_id:
            continue
        q_score[r.question_number or "-"][r.student_id] = score
        q_max[r.question_number or "-"] = float(r.max_score or 0)

    tags = []
    for tag, questions in tag_questions.items():
        total_earned = 0.0
        total_possible = 0.0
        for q in questions:
            max_s = q_max.get(q, 0.0) or 0.0
            for _sid, score in q_score.get(q, {}).items():
                total_earned += score
                total_possible += max_s
        rate = round(total_earned / total_possible, 4) if total_possible else 0.0
        tags.append({
            "knowledge_tag": tag,
            "question_numbers": questions,
            "question_count": len(questions),
            "avg_score_rate": rate,
            "mastery_level": _mastery_level(rate),
        })
    tags.sort(key=lambda t: t["avg_score_rate"])

    return {
        "exam_id": exam_id,
        "tag_count": len(tags),
        "tags": tags,
    }


# ---------------- F8-05 学生个人报告 ----------------

def student_report(db: Session, exam_id: UUID, student_id: UUID) -> dict:
    data = _collect(db, exam_id)
    exam = data["exam"]
    total_score, pass_score, excellent = _thresholds(exam)

    roster_map = {es.student_id: st for es, st in data["roster"]}
    student = roster_map.get(student_id)
    if not student:
        student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学生不存在")

    totals = _student_totals(data)
    my = totals.get(student_id, {"choice": 0.0, "subjective": 0.0, "total": 0.0, "ungraded": 0})

    # 排名
    ranked = sorted(totals.items(), key=lambda kv: kv[1]["total"], reverse=True)
    rank_grade = next((i + 1 for i, (sid, _) in enumerate(ranked) if sid == student_id), None)
    my_class = student.class_name or "未分班"
    class_ranked = [
        (sid, b) for sid, b in ranked
        if (roster_map.get(sid).class_name if roster_map.get(sid) else None) == my_class
    ]
    rank_class = next((i + 1 for i, (sid, _) in enumerate(class_ranked) if sid == student_id), None)

    # 逐题明细
    qmeta = _question_meta(data)
    choice_by_q: Dict[str, ChoiceResult] = {}
    for r in data["choice"]:
        if r.student_id == student_id:
            choice_by_q[r.question_number or "-"] = r
    subj_by_q: Dict[str, SubjectiveResult] = {}
    for r in data["subjective"]:
        if r.student_id == student_id:
            subj_by_q[r.question_number or "-"] = r

    questions = []
    for q, meta in qmeta.items():
        if meta["type"] == "choice":
            r = choice_by_q.get(q)
            questions.append({
                "question_number": q,
                "question_type": "choice",
                "max_score": meta["max_score"],
                "score": float(r.score or 0) if r else None,
                "is_correct": bool(r.is_correct) if r else None,
                "recognized_options": r.recognized_options if r else None,
                "correct_options": r.correct_options if r else None,
                "mark": None,
                "knowledge_tags": meta["knowledge_tags"],
            })
        else:
            r = subj_by_q.get(q)
            questions.append({
                "question_number": q,
                "question_type": "subjective",
                "max_score": meta["max_score"],
                "score": _effective_subjective(r) if r else None,
                "is_correct": None,
                "recognized_options": None,
                "correct_options": None,
                "mark": (r.mark if r else None),
                "knowledge_tags": meta["knowledge_tags"],
            })

    # 个人知识点掌握
    tag_earned: Dict[str, float] = defaultdict(float)
    tag_possible: Dict[str, float] = defaultdict(float)
    for item in questions:
        if item["score"] is None:
            continue
        for tag in item["knowledge_tags"]:
            tag_earned[tag] += item["score"]
            tag_possible[tag] += item["max_score"]
    knowledge = [
        {
            "knowledge_tag": tag,
            "avg_score_rate": round(tag_earned[tag] / tag_possible[tag], 4) if tag_possible[tag] else 0.0,
            "mastery_level": _mastery_level(tag_earned[tag] / tag_possible[tag] if tag_possible[tag] else 0.0),
        }
        for tag in tag_possible
    ]
    knowledge.sort(key=lambda k: k["avg_score_rate"])

    marks = [
        {
            "question_number": r.question_number,
            "mark": r.mark,
            "score": _effective_subjective(r),
            "max_score": float(r.max_score or 0),
            "block_id": r.block_id,
            "comment": r.first_comment or r.ai_comment,
        }
        for r in data["subjective"]
        if r.student_id == student_id and r.mark in ("excellent", "typical_error", "blank")
    ]

    absent = next((es.is_absent for es, _ in data["roster"] if es.student_id == student_id), False)

    return {
        "exam_id": exam.id,
        "exam_name": exam.name,
        "student_id": student.id,
        "student_name": student.name,
        "exam_number": student.exam_number,
        "class_name": my_class,
        "is_absent": absent,
        "total_score": total_score,
        "pass_score": pass_score,
        "excellent_score": excellent,
        "score": my["total"],
        "choice_score": round(my["choice"], 2),
        "subjective_score": round(my["subjective"], 2),
        "rank_in_grade": rank_grade,
        "rank_in_class": rank_class,
        "grade_student_count": len(ranked),
        "class_student_count": len(class_ranked),
        "passed": my["total"] >= pass_score,
        "excellent": my["total"] >= excellent,
        "questions": questions,
        "knowledge": knowledge,
        "marks": marks,
    }


# ---------------- F8-06 讲评素材 ----------------

def review_materials(db: Session, exam_id: UUID, limit: int = 30) -> dict:
    data = _collect(db, exam_id)
    exam = data["exam"]
    roster_map = {es.student_id: st for es, st in data["roster"]}

    def material(r: SubjectiveResult) -> dict:
        student = roster_map.get(r.student_id)
        return {
            "result_id": r.id,
            "block_id": r.block_id,
            "question_number": r.question_number,
            "student_id": r.student_id,
            "student_name": student.name if student else None,
            "class_name": student.class_name if student else None,
            "exam_number": student.exam_number if student else None,
            "score": _effective_subjective(r),
            "max_score": float(r.max_score or 0),
            "mark": r.mark,
            "comment": r.first_comment or r.second_comment or r.ai_comment,
            "arbitration_note": r.arbitration_note,
        }

    excellent = [material(r) for r in data["subjective"] if r.mark == "excellent"]
    typical_error = [material(r) for r in data["subjective"] if r.mark == "typical_error"]
    blank = [material(r) for r in data["subjective"] if r.mark == "blank"]

    question_data = question_report(db, exam_id)
    high_error = question_data["high_error_questions"]

    return {
        "exam_id": exam.id,
        "excellent": excellent[:limit],
        "typical_error": typical_error[:limit],
        "blank": blank[:limit],
        "high_error_questions": high_error,
        "question_count": question_data["total_questions"],
    }


# ---------------- 学生列表（个人报告下拉用） ----------------

def list_students(db: Session, exam_id: UUID) -> List[dict]:
    data = _collect(db, exam_id)
    totals = _student_totals(data)
    return [
        {
            "student_id": st.id,
            "name": st.name,
            "exam_number": st.exam_number,
            "class_name": st.class_name,
            "is_absent": es.is_absent,
            "total_score": totals.get(st.id, {}).get("total", 0.0),
        }
        for es, st in data["roster"]
    ]


def scoreboard(db: Session, exam_id: UUID) -> Dict[UUID, dict]:
    """按学生实时汇总总分与年级/班级排名，供成绩单、导出等场景复用。"""
    data = _collect(db, exam_id)
    totals = _student_totals(data)
    roster_map = {es.student_id: st for es, st in data["roster"]}
    ranked = sorted(totals.items(), key=lambda kv: kv[1]["total"], reverse=True)

    board: Dict[UUID, dict] = {}
    class_members: Dict[str, List[UUID]] = defaultdict(list)
    for idx, (sid, bucket) in enumerate(ranked):
        student = roster_map.get(sid)
        class_name = (student.class_name if student else None) or "未分班"
        board[sid] = {
            "total": bucket["total"],
            "rank_in_grade": idx + 1,
            "grade_student_count": len(ranked),
            "class_name": class_name,
        }
        class_members[class_name].append(sid)

    for members in class_members.values():
        for idx, sid in enumerate(members):
            board[sid]["rank_in_class"] = idx + 1
            board[sid]["class_student_count"] = len(members)
    return board