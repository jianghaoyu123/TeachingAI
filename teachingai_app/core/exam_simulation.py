from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .llm_api import LLMApiError, _build_profile_context, invoke_llm, parse_llm_json
from .models import (
    ExamQuestion,
    ExamReport,
    OptimizationSuggestion,
    QuestionDiagnostic,
    StudentQuestionAttempt,
)
from .profiles import get_profiles_for_subject

ProgressCallback = Callable[[str, int, int], None]


def _emit(callback: ProgressCallback | None, message: str, current: int, total: int) -> None:
    if callback is not None:
        callback(message, current, total)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _run_exam_parser_agent(
    *,
    text: str,
    subject: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> list[ExamQuestion]:
    system_prompt = (
        f"你是{subject}教师，负责从试卷文本中解析出结构化题目信息。"
        "必须只输出JSON，不要输出其他文字。"
    )
    user_prompt = f"""
请从以下试卷文本中解析出每道题目的结构化信息。

学科: {subject}
年级: {grade}

试卷文本:
{text[:12000]}

请严格输出JSON:
{{
  "questions": [
    {{
      "question_id": "q1",
      "content": "题目完整内容（含选项）",
      "question_type": "选择题|填空题|解答题|判断题|其他",
      "points": 5.0,
      "knowledge_tags": ["涉及的知识点1", "知识点2"]
    }}
  ]
}}

要求:
- question_id 使用 q1, q2, ... 格式
- 尽量保留题目完整内容（含选项、图示说明）
- points 若试卷未标明则根据题型合理估计（选择题2-4分，填空题3-5分，解答题8-15分）
- knowledge_tags 提取本题考查的1-3个核心知识点
""".strip()

    raw = invoke_llm(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=120,
    )
    parsed = parse_llm_json(raw)
    raw_questions = parsed.get("questions", [])
    if not isinstance(raw_questions, list):
        raw_questions = []

    questions: list[ExamQuestion] = []
    for idx, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            continue
        qid = str(item.get("question_id", f"q{idx}")).strip() or f"q{idx}"
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        qtype = str(item.get("question_type", "其他")).strip()
        try:
            points = float(item.get("points", 5))
        except (TypeError, ValueError):
            points = 5.0
        tags = _as_str_list(item.get("knowledge_tags"))[:3]
        questions.append(
            ExamQuestion(
                question_id=qid,
                content=content,
                question_type=qtype,
                points=points,
                knowledge_tags=tags,
            )
        )

    if not questions:
        raise LLMApiError(
            "试卷解析失败：未能从文本中提取出有效题目。"
            "请确认输入内容为试卷/试题格式，并至少包含一道完整题目。"
        )
    return questions


def _run_exam_simulation_agent(
    *,
    questions: list[ExamQuestion],
    subject: str,
    grade: str,
    exam_topic: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[list[StudentQuestionAttempt], list[QuestionDiagnostic]]:
    profiles = get_profiles_for_subject(subject, grade)
    profile_context = _build_profile_context(subject, grade)
    profile_names = [p.name for p in profiles]

    question_summary = "\n".join(
        f"[{q.question_id}] ({q.question_type}, {q.points}分) {q.content[:300]}"
        for q in questions
    )

    system_prompt = (
        f"你是{subject}教师与教研分析专家，负责模拟不同层级学生在试卷上的表现，并诊断每道题目的教学问题。"
        "必须只输出JSON，不要输出其他文字。"
    )
    user_prompt = f"""
请模拟以下学生画像对试卷各题目的作答情况，并给出每道题的诊断分析。

学科: {subject} | 年级: {grade} | 考试主题: {exam_topic}

学生画像:
{profile_context}

试卷题目（共 {len(questions)} 题）:
{question_summary}

请严格输出JSON:
{{
  "student_attempts": [
    {{
      "profile_name": "必须与以下姓名之一完全一致: {", ".join(profile_names)}",
      "question_id": "q1",
      "predicted_correct": true,
      "estimated_score": 4.0,
      "predicted_answer": "该学生可能写出的答案或解题过程（简短描述，1-2句）",
      "error_type": "无明显错误|概念错误|计算错误|审题失误|思路偏差|其他",
      "reasoning_note": "该学生解题思路的简短说明（1-2句）"
    }}
  ],
  "question_diagnostics": [
    {{
      "question_id": "q1",
      "difficulty_label": "易|中|难",
      "predicted_class_accuracy": 0.75,
      "common_error_type": "最常见错误类型",
      "teaching_note": "本题暴露的教学盲点或教学建议（1-2句）"
    }}
  ]
}}

要求:
- student_attempts 必须覆盖每位学生对每道题的作答（共 {len(profile_names)} × {len(questions)} 条）
- estimated_score 必须在 0 到该题满分之间
- predicted_class_accuracy 为预测的全班平均正确率（0-1）
- 不同层级学生的表现要有明显差异，基础薄弱型学生应在难题上失分明显
""".strip()

    raw = invoke_llm(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=180,
    )
    parsed = parse_llm_json(raw)

    attempts: list[StudentQuestionAttempt] = []
    raw_attempts = parsed.get("student_attempts", [])
    if isinstance(raw_attempts, list):
        for item in raw_attempts:
            if not isinstance(item, dict):
                continue
            name = str(item.get("profile_name", "")).strip()
            qid = str(item.get("question_id", "")).strip()
            if not name or not qid:
                continue
            try:
                est_score = float(item.get("estimated_score", 0))
            except (TypeError, ValueError):
                est_score = 0.0
            # Clamp to the question's max points
            q_match = next((q for q in questions if q.question_id == qid), None)
            max_pts = q_match.points if q_match else 10.0
            est_score = round(max(0.0, min(float(max_pts), est_score)), 1)
            attempts.append(
                StudentQuestionAttempt(
                    profile_name=name,
                    question_id=qid,
                    predicted_correct=bool(item.get("predicted_correct", False)),
                    estimated_score=est_score,
                    predicted_answer=str(item.get("predicted_answer", "")).strip(),
                    error_type=str(item.get("error_type", "其他")).strip() or "其他",
                    reasoning_note=str(item.get("reasoning_note", "")).strip(),
                )
            )

    diagnostics: list[QuestionDiagnostic] = []
    raw_diagnostics = parsed.get("question_diagnostics", [])
    if isinstance(raw_diagnostics, list):
        for item in raw_diagnostics:
            if not isinstance(item, dict):
                continue
            qid = str(item.get("question_id", "")).strip()
            if not qid:
                continue
            try:
                acc = float(item.get("predicted_class_accuracy", 0.5))
                acc = round(max(0.0, min(1.0, acc)), 2)
            except (TypeError, ValueError):
                acc = 0.5
            diagnostics.append(
                QuestionDiagnostic(
                    question_id=qid,
                    difficulty_label=str(item.get("difficulty_label", "中")).strip(),
                    predicted_class_accuracy=acc,
                    common_error_type=str(item.get("common_error_type", "")).strip(),
                    teaching_note=str(item.get("teaching_note", "")).strip(),
                )
            )

    # Fill missing diagnostics for any question not returned by LLM.
    covered_diag_ids = {d.question_id for d in diagnostics}
    for q in questions:
        if q.question_id not in covered_diag_ids:
            diagnostics.append(
                QuestionDiagnostic(
                    question_id=q.question_id,
                    difficulty_label="中",
                    predicted_class_accuracy=0.5,
                    common_error_type="未分析",
                    teaching_note="",
                )
            )

    return attempts, diagnostics


def _run_exam_suggestion_agent(
    *,
    questions: list[ExamQuestion],
    attempts: list[StudentQuestionAttempt],
    diagnostics: list[QuestionDiagnostic],
    subject: str,
    grade: str,
    exam_topic: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[list[OptimizationSuggestion], str]:
    profile_context = _build_profile_context(subject, grade)

    diag_summary = "\n".join(
        f"[{d.question_id}] 难度:{d.difficulty_label} "
        f"预测正确率:{int(d.predicted_class_accuracy * 100)}% "
        f"常见错误:{d.common_error_type} | {d.teaching_note}"
        for d in diagnostics
    )

    low_acc = [d for d in diagnostics if d.predicted_class_accuracy < 0.5]
    low_acc_desc = (
        "; ".join(f"{d.question_id}({int(d.predicted_class_accuracy * 100)}%)" for d in low_acc)
        or "无"
    )

    # Build per-student total score summary for prompt context.
    score_by_student: dict[str, float] = {}
    for a in attempts:
        score_by_student[a.profile_name] = score_by_student.get(a.profile_name, 0.0) + a.estimated_score
    total_points = sum(q.points for q in questions)
    score_summary = "; ".join(
        f"{name}: {score:.0f}/{total_points:.0f}分"
        for name, score in sorted(score_by_student.items(), key=lambda x: -x[1])
    )

    system_prompt = (
        f"你是{subject}教研组长，根据试题分析结果给出针对性教学改进建议。"
        "必须只输出JSON，不要输出其他文字。"
    )
    user_prompt = f"""
以下是一次{subject}试卷的学生作答模拟结果，请给出教学改进建议。

学科: {subject} | 年级: {grade} | 考试主题: {exam_topic}

学生画像:
{profile_context}

各学生预测总分（满分 {total_points:.0f} 分）:
{score_summary}

题目诊断摘要:
{diag_summary}

预测正确率低于50%的题目（教学薄弱点）: {low_acc_desc}

请输出JSON:
{{
  "suggestions": [
    {{
      "priority": "高|中|低",
      "issue": "从试卷分析中发现的教学问题（引用具体题号或知识点）",
      "suggestion": "可执行的教学改进建议",
      "expected_impact": "预期改进效果"
    }}
  ],
  "class_summary": "对整体班级预测表现的简短总结（3-5句），包括整体得分情况、最大失分点、各层级学生的差异表现"
}}

要求:
- suggestions 3-6条，优先针对低正确率题目和跨层级共同失分的知识点
- 建议要具体可操作，避免泛泛而谈
""".strip()

    raw = invoke_llm(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=120,
    )
    parsed = parse_llm_json(raw)

    suggestions: list[OptimizationSuggestion] = []
    raw_suggestions = parsed.get("suggestions", [])
    if isinstance(raw_suggestions, list):
        for item in raw_suggestions:
            if not isinstance(item, dict):
                continue
            suggestions.append(
                OptimizationSuggestion(
                    priority=str(item.get("priority", "中")).strip(),
                    issue=str(item.get("issue", "")).strip(),
                    suggestion=str(item.get("suggestion", "")).strip(),
                    expected_impact=str(item.get("expected_impact", "")).strip(),
                )
            )

    class_summary = str(parsed.get("class_summary", "")).strip()
    return suggestions, class_summary


def analyze_exam_with_llm(
    text: str,
    subject: str,
    exam_topic: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    progress_callback: ProgressCallback | None = None,
) -> ExamReport:
    total_steps = 3

    _emit(progress_callback, "试卷解析智能体：正在从文本中提取题目结构…", 0, total_steps)
    questions = _run_exam_parser_agent(
        text=text,
        subject=subject,
        grade=grade,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    _emit(
        progress_callback,
        f"学生模拟智能体：正在模拟 {len(questions)} 道题目的作答情况…",
        1,
        total_steps,
    )
    attempts, diagnostics = _run_exam_simulation_agent(
        questions=questions,
        subject=subject,
        grade=grade,
        exam_topic=exam_topic,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    _emit(progress_callback, "教研建议智能体：正在生成针对性教学改进建议…", 2, total_steps)
    suggestions, class_summary = _run_exam_suggestion_agent(
        questions=questions,
        attempts=attempts,
        diagnostics=diagnostics,
        subject=subject,
        grade=grade,
        exam_topic=exam_topic,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    _emit(progress_callback, "试卷分析完成", total_steps, total_steps)
    return ExamReport(
        subject=subject,
        grade=grade,
        exam_topic=exam_topic,
        original_exam_text=text,
        questions=questions,
        student_attempts=attempts,
        question_diagnostics=diagnostics,
        suggestions=suggestions,
        class_summary=class_summary,
    )
