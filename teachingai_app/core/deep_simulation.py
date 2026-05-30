from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .llm_api import (
    LLMApiError,
    _build_profile_context,
    build_report_from_parsed,
    generate_topic_adjustments_with_llm,
    invoke_llm,
    normalize_profile_name,
    parse_llm_json,
)
from .models import (
    LessonModule,
    ModuleDeliberationRecord,
    ModuleStudentInteraction,
    SimulationReport,
    StudentProfile,
)
from .profiles import get_profiles_for_subject
from .curriculum_standards import CurriculumStandardEvaluator

ProgressCallback = Callable[[str, int, int], None]
TeacherFeedback = dict[str, dict[str, Any]]


def _emit(callback: ProgressCallback | None, message: str, current: int, total: int) -> None:
    if callback is not None:
        callback(message, current, total)


def _fallback_module_count_for_material(text: str) -> int:
    length = len(text.strip())
    if length < 2500:
        return 3
    if length < 6000:
        return 4
    return 5


def _run_teacher_agent(
    *,
    text: str,
    subject: str,
    lesson_topic: str,
    grade: str,
    region_curriculum: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> tuple[str, list[LessonModule]]:
    profile_context = _build_profile_context(
        subject,
        grade,
        lesson_topic,
        region_curriculum,
        dynamic_topic_rules,
    )
    system_prompt = (
        f"你是经验丰富的{subject}教师智能体，擅长把教案转化为可执行的课堂讲稿。"
        "必须只输出JSON，不要输出其他文字。"
    )
    user_prompt = f"""
请将教师提供的材料整理为一份可直接用于授课的课堂讲稿（逐字稿风格），并由你自主决定划分为几个教学模块。

学科: {subject}
课题: {lesson_topic}
年级: {grade}
教材地区: {region_curriculum}

后续将安排不同层级学生智能体逐模块与教师互动，请保证每个模块有清晰的教学目标与讲解内容。

学生画像（供你把握讲解节奏与难度）:
{profile_context}

输入材料:
{text[:12000]}

请严格输出JSON:
{{
    "teacher_script": "整课逐字稿，含导入、讲解、互动提问、练习反馈、小结与作业布置，分段清晰",
  "modules": [
    {{
      "module_id": "m1",
      "title": "模块标题",
      "order": 1,
      "teacher_script": "本模块教师讲解逐字稿（300-800字）",
      "key_points": ["本模块关键知识点1", "关键知识点2"]
    }}
  ]
}}

要求:
- modules 数量由你根据教学内容灵活决定，通常建议 3-8 个
- 划分依据优先考虑：知识点边界、认知跨度、讲练评节奏、前后依赖关系
- teacher_script 必须是可直接上课的整课讲稿，不能只写课堂引入；建议总长度不少于 1200 字
- 每个模块 teacher_script 要具体，便于学生智能体据此产生真实课堂反应
- module_id 使用 m1, m2, ... 格式
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
    
    try:
        parsed = parse_llm_json(raw)
    except LLMApiError as e:
        raise LLMApiError(
            f"教师智能体返回格式错误：{e}。请尝试更换模型提供商或调整输入内容后重试。"
        ) from e
    
    if not isinstance(parsed, dict):
        raise LLMApiError("教师智能体返回内容不是有效的JSON对象。")
    
    teacher_script = str(parsed.get("teacher_script", "")).strip()

    modules: list[LessonModule] = []
    raw_modules = parsed.get("modules", [])
    if not isinstance(raw_modules, list):
        raw_modules = []

    for idx, item in enumerate(raw_modules, start=1):
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("module_id", f"m{idx}")).strip() or f"m{idx}"
        title = str(item.get("title", f"模块{idx}")).strip() or f"模块{idx}"
        order = int(item.get("order", idx))
        script = str(item.get("teacher_script", "")).strip()
        key_points = item.get("key_points", [])
        if not isinstance(key_points, list):
            key_points = []
        key_points = [str(k).strip() for k in key_points if str(k).strip()][:6]
        modules.append(
            LessonModule(
                module_id=module_id,
                title=title,
                order=order,
                teacher_script=script,
                key_points=key_points,
            )
        )

    modules.sort(key=lambda m: m.order)
    if not modules:
        raise LLMApiError("教师智能体未生成有效教学模块。")

    # Guardrail for extreme outputs.
    if len(modules) > 10:
        modules = modules[:10]

    # Some models return a very short overview paragraph for teacher_script.
    # In that case, synthesize a practical whole-class script from module scripts.
    min_script_len = max(500, len(modules) * 220)
    if len(teacher_script) < min_script_len:
        merged_parts: list[str] = []
        for module in modules:
            merged_parts.append(f"【模块{module.order}：{module.title}】\n{module.teacher_script}".strip())
        teacher_script = "\n\n".join(part for part in merged_parts if part).strip() or teacher_script

    return teacher_script, modules


def _format_student_agent_specs(profiles: list[StudentProfile]) -> str:
    lines: list[str] = []
    for p in profiles:
        lines.append(
            "\n".join(
                [
                    f"### 学生智能体: {p.name} (层级 {p.level})",
                    f"- 优势: {'; '.join(p.strengths[:4])}",
                    f"- 薄弱点: {'; '.join(p.weaknesses[:4])}",
                    f"- 典型错误倾向: {'; '.join(p.likely_errors[:4])}",
                    f"- 需要的教学支持: {'; '.join(p.support_needs[:3])}",
                    (
                        "- 量化画像: "
                        f"学习活跃度={p.activity_level}/100, "
                        f"基线正确率={p.baseline_success_rate}/100, "
                        f"专注稳定性={p.focus_stability}/100, "
                        f"知识覆盖度={p.knowledge_coverage}/100"
                    ),
                    "- 量化画像字段定义(必须严格按此含义解释): 学习活跃度=主动回应/提问/参与倾向；基线正确率=未点拨前答对概率；专注稳定性=长讲解下持续跟随能力；知识覆盖度=前置知识完整度",
                ]
            )
        )
    return "\n\n".join(lines)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _init_student_memory(profiles: list[StudentProfile]) -> dict[str, dict[str, Any]]:
    memory: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        memory[profile.name] = {
            "confusion_strength": {},
            "error_strength": {},
            "resolved_strength": {},
            "teacher_feedback_notes": [],
            "last_module": "",
        }
    return memory


def _merge_unique(items: list[str], incoming: list[str], limit: int = 8) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in items + incoming:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
        if len(merged) >= limit:
            break
    return merged


def _bucket_to_ranked_list(bucket: dict[str, float], limit: int = 8) -> list[str]:
    pairs = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)
    return [str(key).strip() for key, _ in pairs if str(key).strip()][:limit]


def _reinforce_bucket(bucket: dict[str, float], items: list[str], gain: float, limit: int = 12) -> None:
    for raw in items:
        item = str(raw).strip()
        if not item:
            continue
        bucket[item] = float(bucket.get(item, 0.0)) + gain
    if len(bucket) > limit:
        ranked = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        bucket.clear()
        bucket.update({k: v for k, v in ranked})


def _decay_memory_state(
    student_memory: dict[str, dict[str, Any]],
    *,
    decay: float = 0.86,
    forget_threshold: float = 0.35,
) -> list[str]:
    updates: list[str] = []
    for student, mem in student_memory.items():
        forgotten: list[str] = []
        for key in ("confusion_strength", "error_strength", "resolved_strength"):
            bucket = mem.get(key, {})
            if not isinstance(bucket, dict):
                continue
            for item in list(bucket.keys()):
                bucket[item] = float(bucket[item]) * decay
                if bucket[item] < forget_threshold:
                    forgotten.append(item)
                    bucket.pop(item, None)
        if forgotten:
            updates.append(f"{student} 记忆衰减后淡化: {'; '.join(forgotten[:2])}")
    return updates[:10]


def _apply_teacher_feedback(
    student_memory: dict[str, dict[str, Any]],
    teacher_feedback: TeacherFeedback,
) -> list[str]:
    updates: list[str] = []
    for student, feedback in teacher_feedback.items():
        if student not in student_memory or not isinstance(feedback, dict):
            continue
        mem = student_memory[student]
        confusion_bucket = mem.setdefault("confusion_strength", {})
        error_bucket = mem.setdefault("error_strength", {})
        resolved_bucket = mem.setdefault("resolved_strength", {})

        reinforce_confusions = _as_str_list(feedback.get("reinforce_confusions"))[:6]
        reinforce_errors = _as_str_list(feedback.get("reinforce_errors"))[:6]
        resolve_confusions = _as_str_list(feedback.get("resolve_confusions"))[:6]
        resolve_errors = _as_str_list(feedback.get("resolve_errors"))[:6]
        note = str(feedback.get("note", "")).strip()

        _reinforce_bucket(confusion_bucket, reinforce_confusions, gain=1.2)
        _reinforce_bucket(error_bucket, reinforce_errors, gain=1.2)

        for item in resolve_confusions:
            confusion_bucket.pop(item, None)
        _reinforce_bucket(resolved_bucket, resolve_confusions, gain=1.1)

        for item in resolve_errors:
            error_bucket.pop(item, None)
        _reinforce_bucket(resolved_bucket, resolve_errors, gain=1.0)

        if note:
            notes = mem.setdefault("teacher_feedback_notes", [])
            notes.append(note)
            mem["teacher_feedback_notes"] = notes[-4:]

        updates.append(f"教师纠偏已应用到 {student}")

    return updates[:12]


def _memory_context_for_prompt(
    profiles: list[StudentProfile],
    student_memory: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    for profile in profiles:
        mem = student_memory.get(profile.name, {})
        open_confusions = _bucket_to_ranked_list(mem.get("confusion_strength", {}), 4)
        recurring_errors = _bucket_to_ranked_list(mem.get("error_strength", {}), 4)
        resolved_points = _bucket_to_ranked_list(mem.get("resolved_strength", {}), 4)
        feedback_notes = mem.get("teacher_feedback_notes", [])
        last_module = str(mem.get("last_module", "")).strip() or "无"
        lines.append(
            "\n".join(
                [
                    f"### {profile.name} 的跨模块记忆",
                    f"- 上一模块: {last_module}",
                    f"- 未解决困惑: {'; '.join(open_confusions[:4]) if open_confusions else '暂无'}",
                    f"- 反复错误: {'; '.join(recurring_errors[:4]) if recurring_errors else '暂无'}",
                    f"- 已解决点: {'; '.join(resolved_points[:4]) if resolved_points else '暂无'}",
                    f"- 教师纠偏提示: {'; '.join(feedback_notes[-2:]) if feedback_notes else '暂无'}",
                ]
            )
        )
    return "\n\n".join(lines)


def _run_module_student_agents(
    *,
    module: LessonModule,
    profiles: list[StudentProfile],
    subject: str,
    lesson_topic: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    student_memory: dict[str, dict[str, Any]],
) -> list[ModuleStudentInteraction]:
    student_specs = _format_student_agent_specs(profiles)
    memory_context = _memory_context_for_prompt(profiles, student_memory)
    profile_names = [p.name for p in profiles]

    system_prompt = (
        f"你是{subject}课堂中的学生群体模拟系统。"
        "每位学生是独立智能体，听完本模块讲解后先给出第一轮原始课堂反应。必须只输出JSON。"
    )
    user_prompt = f"""
本模块教师讲解内容:
【{module.title}】
{module.teacher_script[:4000]}

学科: {subject} | 课题: {lesson_topic} | 年级: {grade}
模块知识点: {", ".join(module.key_points) if module.key_points else "见讲解内容"}

参与互动的学生智能体（必须为以下每一位分别生成反应）:
{student_specs}

跨模块记忆（必须用于保持人物一致性）:
{memory_context}

请严格输出JSON:
{{
  "student_reactions": [
    {{
      "profile_name": "必须与下列姓名之一完全一致: {", ".join(profile_names)}",
      "engagement": "低|中低|中|中高|高",
            "listening_state": "专注跟随|基本跟随|间歇走神|明显走神|关键段未听到",
            "distraction_reason": "若走神请说明原因，如兴趣不足/前置缺口/课堂疲劳；若无可空字符串",
            "missed_key_points": ["因走神或注意力断裂而漏听的关键点"],
      "verbal_response": "学生在课堂上可能说的话或简短反馈（1-3句）",
      "confusion_points": ["困惑点"],
      "likely_questions": ["可能向老师提出的问题"],
      "error_predictions": ["可能犯的理解或计算错误"]
    }}
  ]
}}

要求:
- student_reactions 必须覆盖全部 {len(profile_names)} 位学生
- 不同层级学生的困惑点、错误、提问要有明显差异
- 反应要紧扣本模块讲解内容，不要泛泛而谈
- 这是第一轮观点，不需要达成共识
- 本轮内容必须与该学生的历史记忆保持一致，若出现变化要在后续轮次解释
- 重要提示：聚焦于本课程相关的典型错误和问题，忽略与本课无关的学科特定内容
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
    interactions: list[ModuleStudentInteraction] = []
    items = parsed.get("student_reactions", [])
    if not isinstance(items, list):
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = normalize_profile_name(item.get("profile_name", ""), {p.name for p in profiles})
        if not name:
            continue
        interactions.append(
            ModuleStudentInteraction(
                module_id=module.module_id,
                module_title=module.title,
                profile_name=name,
                engagement=str(item.get("engagement", "中")),
                verbal_response=str(item.get("verbal_response", "")).strip(),
                confusion_points=_as_str_list(item.get("confusion_points"))[:5],
                likely_questions=_as_str_list(item.get("likely_questions"))[:5],
                error_predictions=_as_str_list(item.get("error_predictions"))[:5],
                listening_state=str(item.get("listening_state", "基本跟随")).strip() or "基本跟随",
                distraction_reason=str(item.get("distraction_reason", "")).strip(),
                missed_key_points=_as_str_list(item.get("missed_key_points"))[:4],
                confidence_score=max(0, min(100, _safe_int(item.get("confidence_score", 58), 58))),
                consistency_note=str(item.get("consistency_note", "")).strip(),
            )
        )

    covered = {i.profile_name for i in interactions}
    for profile in profiles:
        if profile.name in covered:
            continue
        interactions.append(
            ModuleStudentInteraction(
                module_id=module.module_id,
                module_title=module.title,
                profile_name=profile.name,
                engagement="中",
                verbal_response="（本模块未返回该学生的详细发言）",
                confusion_points=profile.weaknesses[:3],
                likely_questions=[],
                error_predictions=profile.likely_errors[:3],
                listening_state="基本跟随",
                confidence_score=55,
                consistency_note="使用画像默认项补全。",
            )
        )

    return interactions


def _format_round_interactions(interactions: list[ModuleStudentInteraction]) -> str:
    lines: list[str] = []
    for inter in interactions:
        lines.append(
            "\n".join(
                [
                    f"- 学生: {inter.profile_name} | 参与度: {inter.engagement}",
                    f"  听课状态: {inter.listening_state}",
                    f"  分心原因: {inter.distraction_reason or '无'}",
                    f"  漏听要点: {'; '.join(inter.missed_key_points[:3]) if inter.missed_key_points else '无'}",
                    f"  首轮发言: {inter.verbal_response}",
                    f"  困惑: {'; '.join(inter.confusion_points[:4])}",
                    f"  提问: {'; '.join(inter.likely_questions[:4])}",
                    f"  错误: {'; '.join(inter.error_predictions[:4])}",
                ]
            )
        )
    return "\n".join(lines)


def _run_module_deliberation_agent(
    *,
    module: LessonModule,
    round1_interactions: list[ModuleStudentInteraction],
    profiles: list[StudentProfile],
    subject: str,
    lesson_topic: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    student_memory: dict[str, dict[str, Any]],
) -> tuple[list[ModuleStudentInteraction], ModuleDeliberationRecord]:
    profile_names = [p.name for p in profiles]
    round1_summary = _format_round_interactions(round1_interactions)
    memory_context = _memory_context_for_prompt(profiles, student_memory)

    system_prompt = (
        f"你是{subject}课堂中的多智能体讨论裁决系统。"
        "你要组织学生复议、反方挑战、教学观察员裁决，然后输出第二轮修正版学生反应。"
        "必须只输出JSON。"
    )
    user_prompt = f"""
本模块教师讲解内容:
【{module.title}】
{module.teacher_script[:4000]}

学科: {subject} | 课题: {lesson_topic} | 年级: {grade}
模块知识点: {", ".join(module.key_points) if module.key_points else "见讲解内容"}

第一轮学生原始反应（供讨论）:
{round1_summary}

跨模块记忆（讨论与裁决时必须遵循）:
{memory_context}

请执行以下流程并输出第二轮结论:
1) 学生互相质疑与补充（指出误解、遗漏、过度自信）
2) 反方挑战者专门找出当前讲解最可能导致误解的点
3) 教学观察员裁决，给出可执行修正意见

请严格输出JSON:
{{
  "student_reactions": [
    {{
      "profile_name": "必须与下列姓名之一完全一致: {", ".join(profile_names)}",
      "engagement": "低|中低|中|中高|高",
            "listening_state": "专注跟随|基本跟随|间歇走神|明显走神|关键段未听到",
            "distraction_reason": "若走神请说明原因；若无可空字符串",
            "missed_key_points": ["复议后确认仍漏听的关键点"],
      "verbal_response": "第二轮复议后学生在课堂上可能说的话（1-3句）",
      "confusion_points": ["复议后仍存在的困惑点"],
      "likely_questions": ["复议后最关键问题"],
            "error_predictions": ["复议后最可能错误"],
            "confidence_score": 0,
            "consistency_note": "与跨模块记忆的一致性说明"
    }}
  ],
  "consensus": ["本模块讨论达成的共识"],
  "disagreements": ["尚未达成一致的分歧"],
    "teaching_adjustments": ["建议教师立刻调整的讲法或练习"],
    "memory_updates": ["本模块后应写入记忆的关键变化"]
}}

要求:
- student_reactions 必须覆盖全部 {len(profile_names)} 位学生
- 第二轮结果要比第一轮更具体，且体现讨论后的修正
- 若第一轮有明显错误预测，应在第二轮显式保留或纠偏
- confidence_score 取 0-100，表示该学生反应在本模块下的可靠度
- consistency_note 必须明确说明和历史记忆的一致或冲突原因
- 重要提示：聚焦于本课程相关的典型错误和问题，忽略与本课无关的学科特定内容
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
    items = parsed.get("student_reactions", [])
    if not isinstance(items, list):
        items = []

    interactions: list[ModuleStudentInteraction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = normalize_profile_name(item.get("profile_name", ""), {p.name for p in profiles})
        if not name:
            continue
        interactions.append(
            ModuleStudentInteraction(
                module_id=module.module_id,
                module_title=module.title,
                profile_name=name,
                engagement=str(item.get("engagement", "中")),
                verbal_response=str(item.get("verbal_response", "")).strip(),
                confusion_points=_as_str_list(item.get("confusion_points"))[:5],
                likely_questions=_as_str_list(item.get("likely_questions"))[:5],
                error_predictions=_as_str_list(item.get("error_predictions"))[:5],
                listening_state=str(item.get("listening_state", "基本跟随")).strip() or "基本跟随",
                distraction_reason=str(item.get("distraction_reason", "")).strip(),
                missed_key_points=_as_str_list(item.get("missed_key_points"))[:4],
                confidence_score=max(0, min(100, _safe_int(item.get("confidence_score", 68), 68))),
                consistency_note=str(item.get("consistency_note", "")).strip(),
            )
        )

    consensus = _as_str_list(parsed.get("consensus"))[:6]
    disagreements = _as_str_list(parsed.get("disagreements"))[:6]
    teaching_adjustments = _as_str_list(parsed.get("teaching_adjustments"))[:8]
    memory_updates = _as_str_list(parsed.get("memory_updates"))[:8]

    if not interactions:
        fallback_record = ModuleDeliberationRecord(
            module_id=module.module_id,
            module_title=module.title,
            consensus=consensus,
            disagreements=disagreements,
            teaching_adjustments=teaching_adjustments,
            memory_updates=memory_updates,
        )
        return round1_interactions, fallback_record

    round1_map = {i.profile_name: i for i in round1_interactions}
    covered = {i.profile_name for i in interactions}
    for profile in profiles:
        if profile.name in covered:
            continue
        fallback = round1_map.get(profile.name)
        if fallback is not None:
            interactions.append(fallback)
            continue
        interactions.append(
            ModuleStudentInteraction(
                module_id=module.module_id,
                module_title=module.title,
                profile_name=profile.name,
                engagement="中",
                verbal_response="（讨论轮未返回该学生的详细发言）",
                confusion_points=profile.weaknesses[:3],
                likely_questions=[],
                error_predictions=profile.likely_errors[:3],
                    listening_state="基本跟随",
                    confidence_score=60,
                    consistency_note="讨论轮缺失，已回退第一轮/画像。",
            )
        )

    deliberation_record = ModuleDeliberationRecord(
        module_id=module.module_id,
        module_title=module.title,
        consensus=consensus,
        disagreements=disagreements,
        teaching_adjustments=teaching_adjustments,
        memory_updates=memory_updates,
    )
    return interactions, deliberation_record


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _summarize_interactions_for_aggregator(
    modules: list[LessonModule],
    interactions: list[ModuleStudentInteraction],
    module_deliberations: list[ModuleDeliberationRecord],
) -> str:
    by_module: dict[str, list[ModuleStudentInteraction]] = {}
    for item in interactions:
        by_module.setdefault(item.module_id, []).append(item)

    deliberation_by_module = {d.module_id: d for d in module_deliberations}

    chunks: list[str] = []
    for module in modules:
        chunks.append(f"## 模块: {module.title} ({module.module_id})")
        chunks.append(f"讲解摘要: {module.teacher_script[:500]}...")
        module_items = by_module.get(module.module_id, [])
        deliberation = deliberation_by_module.get(module.module_id)
        if deliberation is not None:
            if deliberation.consensus:
                chunks.append(f"模块共识: {'; '.join(deliberation.consensus[:4])}")
            if deliberation.disagreements:
                chunks.append(f"模块分歧: {'; '.join(deliberation.disagreements[:4])}")
            if deliberation.teaching_adjustments:
                chunks.append(f"即时教学调整: {'; '.join(deliberation.teaching_adjustments[:4])}")
        for inter in module_items:
            chunks.append(
                f"- {inter.profile_name} | 参与度 {inter.engagement}\n"
                f"  听课状态: {inter.listening_state}\n"
                f"  分心原因: {inter.distraction_reason or '无'}\n"
                f"  漏听要点: {'; '.join(inter.missed_key_points[:3]) if inter.missed_key_points else '无'}\n"
                f"  课堂发言: {inter.verbal_response}\n"
                f"  困惑: {'; '.join(inter.confusion_points[:3])}\n"
                f"  提问: {'; '.join(inter.likely_questions[:3])}\n"
                f"  错误: {'; '.join(inter.error_predictions[:3])}\n"
                f"  置信度: {inter.confidence_score}\n"
                f"  一致性说明: {inter.consistency_note or '（未提供）'}"
            )
        chunks.append("")
    return "\n".join(chunks)[:14000]


def _update_student_memory_with_module(
    *,
    module_title: str,
    interactions: list[ModuleStudentInteraction],
    student_memory: dict[str, dict[str, Any]],
) -> list[str]:
    updates: list[str] = []
    for inter in interactions:
        mem = student_memory.setdefault(
            inter.profile_name,
            {
                "confusion_strength": {},
                "error_strength": {},
                "resolved_strength": {},
                "teacher_feedback_notes": [],
                "last_module": "",
            },
        )
        confusion_bucket = mem.setdefault("confusion_strength", {})
        error_bucket = mem.setdefault("error_strength", {})
        resolved_bucket = mem.setdefault("resolved_strength", {})

        previous_open = set(_bucket_to_ranked_list(confusion_bucket, 12))
        current_open = _merge_unique([], inter.confusion_points, limit=12)
        resolved = [item for item in previous_open if item and item not in set(current_open)][:8]

        _reinforce_bucket(confusion_bucket, current_open, gain=1.0)
        _reinforce_bucket(error_bucket, inter.error_predictions, gain=1.0)
        _reinforce_bucket(resolved_bucket, resolved, gain=0.8)

        for item in resolved:
            if item in confusion_bucket:
                confusion_bucket[item] = max(0.0, float(confusion_bucket[item]) - 0.9)
                if confusion_bucket[item] < 0.35:
                    confusion_bucket.pop(item, None)

        mem["last_module"] = module_title

        if resolved:
            updates.append(f"{inter.profile_name} 在本模块解决了: {'; '.join(resolved[:2])}")
        if inter.confusion_points:
            updates.append(f"{inter.profile_name} 新增待解决困惑: {'; '.join(inter.confusion_points[:2])}")
        if inter.error_predictions:
            updates.append(f"{inter.profile_name} 错误模式被强化: {'; '.join(inter.error_predictions[:2])}")
    return updates[:12]


def _run_aggregator_agent(
    *,
    text: str,
    subject: str,
    lesson_topic: str,
    grade: str,
    region_curriculum: str,
    teacher_script: str,
    modules: list[LessonModule],
    interactions: list[ModuleStudentInteraction],
    module_deliberations: list[ModuleDeliberationRecord],
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    improvement_focus: str = "all",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> dict[str, Any]:
    profile_context = _build_profile_context(
        subject,
        grade,
        lesson_topic,
        region_curriculum,
        dynamic_topic_rules,
    )
    interaction_log = _summarize_interactions_for_aggregator(modules, interactions, module_deliberations)

    standards_evaluator = CurriculumStandardEvaluator(subject, grade, region_curriculum)
    # 设置LLM配置，用于智能模块选择
    standards_evaluator.set_llm_config(provider, api_key, base_url, model)
    standards_compliance = None
    standards_summary = ""
    has_curriculum_standards = standards_evaluator.has_standards()

    if has_curriculum_standards:
        standards_compliance = standards_evaluator.evaluate_compliance(text, teacher_script, lesson_topic)
        standards_summary = standards_evaluator.get_standards_summary()

    focus_desc = {
        "all": "兼顾全体学生，保持教学内容的均衡性",
        "low": "重点面向基础薄弱型学生，降低难度，增加更多基础讲解和练习",
        "mid-low": "重点面向中等偏下型学生，提供更多引导和支架",
        "mid": "重点面向中等稳定型学生，保持适中难度",
        "mid-high": "重点面向中等偏上型学生，适当增加挑战性内容",
        "high": "重点面向拔高拓展型学生，增加拓展内容和高阶思维训练",
    }

    curriculum_standards_instruction = ""
    if has_curriculum_standards:
        curriculum_standards_instruction = (
            "你应结合课程标准要求进行评估，确保教案符合课程标准规定的内容和难度要求。"
        )
    else:
        curriculum_standards_instruction = (
            "请基于教学经验和学生反馈进行综合评估。"
        )

    system_prompt = (
        f"你是{subject}教研组长智能体，负责汇总多轮课堂预演结果并输出最终分析报告。"
        + curriculum_standards_instruction
        + "必须只输出JSON。"
    )

    standards_info = ""
    standards_requirement = ""
    if has_curriculum_standards:
        standards_info = f"""
课程标准信息:
{standards_summary}

请在评估教案时，特别关注以下方面:
1. 知识点覆盖是否完整
2. 难度是否符合年级要求
3. 教学目标是否达成
"""
        standards_requirement = f"""
- standards_compliance: 课程标准合规性评估结果（当有课程标准数据时必填），包含:
  {{
    "topic_coverage_score": 知识点覆盖得分(0-100),
    "missing_topics": ["缺失的知识点列表"],
    "difficulty_match": "难度匹配度(匹配/偏高/偏低)",
    "overall_compliance_score": 综合合规得分(0-100),
    "recommendations": ["改进建议列表"]
  }}
"""

    user_prompt = f"""
以下是一次「深度思考模式」多智能体课堂预演的完整记录:
- 教师智能体已生成讲稿并分 {len(modules)} 个模块授课
- 各层级学生智能体在每个模块中与教师互动并产生反应

学科: {subject} | 课题: {lesson_topic} | 年级: {grade} | 教材版本: {region_curriculum}
教案改进方向: {focus_desc.get(improvement_focus, "兼顾全体学生")}
{standards_info}
学生画像模板:
{profile_context}

原始教案材料:
{text[:6000]}

教师完整讲稿（节选）:
{teacher_script[:4000]}

分模块学生互动记录:
{interaction_log}

请综合以上信息，输出与快速模式相同结构的最终报告JSON:
{{
  "key_points": ["全课关键知识点"],
  "reactions": [
    {{
      "profile_name": "学生姓名（与画像一致）",
      "engagement": "低|中低|中|中高|高",
            "listening_state": "专注跟随|基本跟随|间歇走神|明显走神|关键段未听到",
            "distraction_reason": "若存在走神请说明主要原因；若无可空",
            "missed_key_points": ["整课中因注意力问题漏听的关键点"],
      "confusion_points": ["整课汇总的困惑点，去重后3-6条"],
      "likely_questions": ["整课可能提问"],
      "error_predictions": ["整课典型错误预测"]
    }}
  ],
  "difficulty": {{
    "overall_level": "低|中|高",
    "cognitive_load_score": 1,
    "step_complexity_score": 1,
    "concept_span_score": 1,
    "rationale": ["依据分模块互动给出的难度理由"]
  }},
    "confidence": {{
        "overall_level": "低|中|高",
        "overall_score": 0,
        "rationale": ["置信度判断依据"],
        "profile_confidence": ["学生A: 72（依据...）", "学生B: 64（依据...）"]
    }},
  "suggestions": [
    {{
      "priority": "高|中|低",
      "issue": "从分模块互动中发现的教学问题",
      "suggestion": "可执行优化建议",
      "expected_impact": "预期效果"
    }}
  ],
  "lesson_plan_change_summary": ["对原教案的关键修改说明"],
  "revised_lesson_plan": "结合各模块学生反应修订后的完整教案，要求：1) 保持与原教案相同的结构和详细程度；2) 保留教学过程中的具体教学步骤、提问、例题和互动设计；3) 根据各模块学生反应和优化建议对原教案进行针对性修改；4) 分点清晰，层次分明，可直接给老师参考使用。需特别注意教案改进方向的要求。"
}}
{standards_requirement}

要求:
- reactions 须覆盖所有参与预演的学生画像
- suggestions 应引用分模块互动中的具体发现，避免空泛
- confidence 必须反映模块内讨论是否收敛、证据是否充分
- revised_lesson_plan 必须严格遵循教案改进方向的要求进行优化
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
    if has_curriculum_standards and standards_compliance is not None:
        parsed["standards_compliance"] = standards_compliance
    return parsed


def analyze_deep_with_llm(
    text: str,
    subject: str,
    lesson_topic: str,
    grade: str,
    region_curriculum: str = "人教版",
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    progress_callback: ProgressCallback | None = None,
    improvement_focus: str = "all",
    teacher_feedback: TeacherFeedback | None = None,
) -> SimulationReport:
    dynamic_topic_rules = generate_topic_adjustments_with_llm(
        text=text,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        region_curriculum=region_curriculum,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    profiles = get_profiles_for_subject(subject, grade, lesson_topic, dynamic_topic_rules)
    student_memory = _init_student_memory(profiles)
    teacher_feedback = teacher_feedback or {}

    if teacher_feedback:
        feedback_updates = _apply_teacher_feedback(student_memory, teacher_feedback)
        if feedback_updates:
            _emit(progress_callback, "已加载教师纠偏反馈，正在更新记忆先验…", 0, 4)

    _emit(progress_callback, "教师智能体：正在根据知识点自动划分教学模块…", 0, 4)
    teacher_script, modules = _run_teacher_agent(
        text=text,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        region_curriculum=region_curriculum,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        dynamic_topic_rules=dynamic_topic_rules,
    )

    if not modules:
        raise LLMApiError("未生成有效模块。")

    # If model returns too few modules unexpectedly, fallback to heuristic target reminder via truncation guard.
    min_expected = 2
    if len(modules) < min_expected:
        fallback_count = _fallback_module_count_for_material(text)
        raise LLMApiError(
            f"模型返回模块数过少（{len(modules)}）。建议重试；当前内容通常应划分为约 {fallback_count} 个模块。"
        )

    total_steps = 2 + len(modules) * 2  # teacher + per-module round1+round2 + aggregator

    all_interactions: list[ModuleStudentInteraction] = []
    module_deliberations: list[ModuleDeliberationRecord] = []
    for step_idx, module in enumerate(modules, start=1):
        forgetting_updates = _decay_memory_state(student_memory)
        round1_step = 1 + (step_idx - 1) * 2
        round2_step = round1_step + 1
        _emit(
            progress_callback,
            f"第一轮学生反应：模块 {step_idx}/{len(modules)}「{module.title}」",
            round1_step,
            total_steps,
        )
        round1_interactions = _run_module_student_agents(
            module=module,
            profiles=profiles,
            subject=subject,
            lesson_topic=lesson_topic,
            grade=grade,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            student_memory=student_memory,
        )
        _emit(
            progress_callback,
            f"第二轮讨论裁决：模块 {step_idx}/{len(modules)}「{module.title}」",
            round2_step,
            total_steps,
        )
        module_interactions, deliberation_record = _run_module_deliberation_agent(
            module=module,
            round1_interactions=round1_interactions,
            profiles=profiles,
            subject=subject,
            lesson_topic=lesson_topic,
            grade=grade,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            student_memory=student_memory,
        )
        memory_updates = _update_student_memory_with_module(
            module_title=module.title,
            interactions=module_interactions,
            student_memory=student_memory,
        )
        deliberation_record.memory_updates = _merge_unique(
            deliberation_record.memory_updates,
            memory_updates,
            8,
        )
        deliberation_record.memory_updates = _merge_unique(
            deliberation_record.memory_updates,
            forgetting_updates,
            8,
        )
        module_deliberations.append(deliberation_record)
        all_interactions.extend(module_interactions)

    _emit(progress_callback, "教研汇总智能体：正在生成最终报告…", total_steps - 1, total_steps)
    parsed = _run_aggregator_agent(
        text=text,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        region_curriculum=region_curriculum,
        teacher_script=teacher_script,
        modules=modules,
        interactions=all_interactions,
        module_deliberations=module_deliberations,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        improvement_focus=improvement_focus,
        dynamic_topic_rules=dynamic_topic_rules,
    )

    report = build_report_from_parsed(
        parsed,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        original_lesson_material=text,
        analysis_mode="deep",
        teacher_script=teacher_script,
        lesson_modules=modules,
        module_interactions=all_interactions,
        module_deliberations=module_deliberations,
        dynamic_topic_rules=dynamic_topic_rules,
    )
    _emit(progress_callback, "深度预演完成", total_steps, total_steps)
    return report
