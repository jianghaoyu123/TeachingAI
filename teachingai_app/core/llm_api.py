from __future__ import annotations

import json
import random
import re
from typing import Any

import requests

from .models import (
    ConfidenceAssessment,
    DifficultyAssessment,
    OptimizationSuggestion,
    SimulationReport,
    StudentReaction,
)
from .profiles import get_grade_band_label, get_profiles_for_subject


class LLMApiError(Exception):
    pass


class LLMRateLimitError(LLMApiError):
    """Rate limit or concurrent request limit exceeded."""
    pass


def get_glm_api_key_from_env() -> str | None:
    import os
    return os.environ.get("LLM_GLM_KEY") or None


PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-latest",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-32k",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M2.7",
    },
}


def parse_llm_json(text: str) -> dict[str, Any]:
    return _extract_json_block(text)


def _extract_json_block(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    
    if not text:
        raise LLMApiError("模型返回内容为空。")
    
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError as e:
            pass
    
    obj = re.search(r"(\{.*\})", text, flags=re.S)
    if obj:
        try:
            return json.loads(obj.group(1))
        except json.JSONDecodeError as e:
            pass
    
    raise LLMApiError(f"模型返回中未找到合法JSON。原始返回内容片段: {text[:200]}...")


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _validate_api_key_for_http_header(api_key: str) -> str:
    cleaned = str(api_key or "").strip()
    if not cleaned:
        raise LLMApiError("API Key 为空，请先在设置窗口填写并保存。")
    if "\n" in cleaned or "\r" in cleaned:
        raise LLMApiError("API Key 包含换行符，请重新复制纯文本密钥后重试。")
    try:
        cleaned.encode("ascii")
    except UnicodeEncodeError as exc:
        raise LLMApiError(
            "API Key 包含非英文字符（如中文/全角符号），无法作为请求头发送。"
            "请检查是否误复制了提示文字或空格。"
        ) from exc
    return cleaned


def _build_http_error_message(status_code: int, body_text: str) -> str:
    lowered = body_text.lower()
    compact = body_text[:300]

    rate_limit_markers = [
        "rate limit",
        "rate_limit",
        "too many requests",
        "requests per",
        "concurrent",
        "qpm",
        "rpm",
        "tpm",
        "限流",
        "请求过于频繁",
        "并发",
        "ratequota",
    ]
    quota_markers = [
        "insufficient",
        "insufficient_balance",
        "insufficient quota",
        "insufficient_quota",
        "quota exceeded",
        "billing",
        "credit",
        "余额",
        "额度",
        "欠费",
        "配额",
    ]

    has_rate_limit = any(marker in lowered for marker in rate_limit_markers)
    has_quota_exhausted = any(marker in lowered for marker in quota_markers)

    if status_code == 429 and has_rate_limit:
        return (
            "RATE_LIMIT_ERROR:免费模型当前请求过于频繁（并发数或QPM达到上限），"
            "建议稍后再试，或切换到自定义API Key模式获得更稳定的体验。"
            f"（HTTP {status_code}，响应片段: {compact}）"
        )

    if status_code in {402, 429} or has_quota_exhausted:
        return (
            "模型调用失败：当前 API 账户可能余额不足或额度已用完，请充值/提升配额后重试，"
            "或切换到自定义API Key模式。"
            f"（HTTP {status_code}，响应片段: {compact}）"
        )

    auth_markers = ["invalid api key", "unauthorized", "authentication", "api key", "鉴权", "密钥"]
    if status_code in {401, 403} or any(marker in lowered for marker in auth_markers):
        return (
            "模型调用失败：API Key 无效、过期或无权限，请检查密钥与模型权限设置。"
            f"（HTTP {status_code}，响应片段: {compact}）"
        )

    return f"模型接口返回错误 {status_code}: {compact}"


def _build_profile_context(subject: str, grade: str) -> str:
    profiles = get_profiles_for_subject(subject, grade)
    band_label = get_grade_band_label(grade)
    chunks: list[str] = [f"学段参考: {band_label}（当前年级: {grade}）"]
    for p in profiles:
        chunks.append(
            "\n".join(
                [
                    f"- 画像: {p.name} ({p.level})",
                    f"  优势: {'; '.join(p.strengths)}",
                    f"  薄弱点: {'; '.join(p.weaknesses)}",
                    f"  典型错误: {'; '.join(p.likely_errors)}",
                    f"  支持需求: {'; '.join(p.support_needs)}",
                ]
            )
        )
    return "\n".join(chunks)


def _build_prompt(text: str, subject: str, lesson_topic: str, grade: str, improvement_focus: str = "all") -> str:
    profile_context = _build_profile_context(subject, grade)
    
    focus_desc = {
        "all": "兼顾全体学生，保持教学内容的均衡性",
        "low": "重点面向基础薄弱型学生，降低难度，增加更多基础讲解和练习",
        "mid-low": "重点面向中等偏下型学生，提供更多引导和支架",
        "mid": "重点面向中等稳定型学生，保持适中难度",
        "mid-high": "重点面向中等偏上型学生，适当增加挑战性内容",
        "high": "重点面向拔高拓展型学生，增加拓展内容和高阶思维训练",
    }
    
    return f"""
你是{subject}学科教研助手，请基于教师输入材料进行“虚拟学生群体教学预演”。

学科: {subject}
课题: {lesson_topic}
年级: {grade}
学生画像模板(优先遵循):
{profile_context}

教案改进方向: {focus_desc.get(improvement_focus, "兼顾全体学生")}

输入材料:
{text[:14000]}

请严格输出JSON，不要输出任何额外说明，格式如下：
{{
  "key_points": ["..."] ,
  "reactions": [
    {{
    "profile_name": "必须与上面学生画像模板中的某个名称完全一致",
      "engagement": "低|中低|中|中高|高",
            "listening_state": "专注跟随|基本跟随|间歇走神|明显走神|关键段未听到",
            "distraction_reason": "若有走神或未听到，写明原因；若无可写空字符串",
            "missed_key_points": ["因走神或兴趣不足而漏听/未建立的关键点"],
      "confusion_points": ["..."],
      "likely_questions": ["..."],
      "error_predictions": ["..."]
    }}
  ],
  "difficulty": {{
    "overall_level": "低|中|高",
    "cognitive_load_score": 1,
    "step_complexity_score": 1,
    "concept_span_score": 1,
    "rationale": ["..."]
  }},
  "suggestions": [
    {{
      "priority": "高|中|低",
      "issue": "...",
      "suggestion": "...",
      "expected_impact": "..."
    }}
    ],
    "lesson_plan_change_summary": [
        "概括说明 AI 对原教案做了哪些关键修改，每条一句话"
    ],
    "revised_lesson_plan": "基于上述建议修改后的完整新教案，要求：1) 保持与原教案相同的结构和详细程度；2) 保留教学过程中的具体教学步骤、提问、例题和互动设计；3) 根据优化建议对原教案进行针对性修改；4) 分点清晰，层次分明，可直接给老师参考使用。请特别注意教案改进方向的要求。"
}}
""".strip()


def invoke_llm(
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: int = 90,
    json_mode: bool = True,
) -> str:
    api_key = _validate_api_key_for_http_header(api_key)

    if provider == "claude":
        return _post_anthropic_message(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_sec=timeout_sec,
        )
    return _post_chat_completion(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=timeout_sec,
        json_mode=json_mode,
    )


def _post_chat_completion(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: int = 90,
    json_mode: bool = True,
) -> str:
    url = f"{_normalize_base_url(base_url)}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    except UnicodeEncodeError as exc:
        raise LLMApiError(
            "请求头编码失败：API Key 可能包含中文或特殊字符，请在 API 设置中重新粘贴密钥。"
        ) from exc
    except requests.RequestException as exc:
        raise LLMApiError(f"调用模型接口失败: {exc}") from exc

    if resp.status_code >= 400:
        error_msg = _build_http_error_message(resp.status_code, resp.text)
        if error_msg.startswith("RATE_LIMIT_ERROR:"):
            raise LLMRateLimitError(error_msg[len("RATE_LIMIT_ERROR:") :])
        raise LLMApiError(error_msg)

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMApiError("模型返回结构异常，未找到choices.message.content。") from exc


def _post_anthropic_message(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: int = 90,
) -> str:
    url = f"{_normalize_base_url(base_url)}/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "system": system_prompt,
        "temperature": 0.3,
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    except UnicodeEncodeError as exc:
        raise LLMApiError(
            "请求头编码失败：API Key 可能包含中文或特殊字符，请在 API 设置中重新粘贴密钥。"
        ) from exc
    except requests.RequestException as exc:
        raise LLMApiError(f"调用模型接口失败: {exc}") from exc

    if resp.status_code >= 400:
        raise LLMApiError(_build_http_error_message(resp.status_code, resp.text))

    data = resp.json()
    try:
        content = data["content"]
        text_blocks = [block.get("text", "") for block in content if isinstance(block, dict)]
        merged = "\n".join(block.strip() for block in text_blocks if block.strip())
        if not merged:
            raise KeyError("empty_content")
        return merged
    except (KeyError, TypeError) as exc:
        raise LLMApiError("Claude 返回结构异常，未找到 content.text。") from exc


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _fit_list_to_target(base_items: list[str], fallback_items: list[str], target_count: int, filler_prefix: str) -> list[str]:
    target_count = max(0, min(6, target_count))
    merged = _dedupe_keep_order(base_items)

    if len(merged) < target_count:
        for item in _dedupe_keep_order(fallback_items):
            if len(merged) >= target_count:
                break
            if item not in merged:
                merged.append(item)

    while len(merged) < target_count:
        merged.append(f"{filler_prefix}{len(merged) + 1}")

    return merged[:target_count]


def _sample_target_count(level: str, kind: str) -> int:
    # Lower-level students get more confusion/errors; higher-level students get fewer.
    count_ranges = {
        "low": {"confusion": (4, 6), "error": (4, 6)},
        "mid-low": {"confusion": (3, 5), "error": (3, 5)},
        "mid": {"confusion": (2, 4), "error": (2, 4)},
        "mid-high": {"confusion": (1, 3), "error": (1, 2)},
        "high": {"confusion": (0, 2), "error": (0, 1)},
    }
    low, high = count_ranges.get(level, count_ranges["mid"])[kind]
    return random.randint(low, high)


def _normalize_engagement_by_level(level: str, current_engagement: str) -> str:
    candidates = {
        "low": ["低", "中低", "中低"],
        "mid-low": ["中低", "中", "中低"],
        "mid": ["中", "中", "中高"],
        "mid-high": ["中", "中高", "中高", "高"],
        "high": ["中高", "高", "高"],
    }
    if current_engagement in {"低", "中低", "中", "中高", "高"}:
        base = current_engagement
    else:
        base = "中"

    pool = candidates.get(level, candidates["mid"])
    # Keep some stability while introducing slight randomness.
    return base if random.random() < 0.45 else random.choice(pool)


def _normalize_listening_state_by_level(level: str, current_state: str) -> str:
    valid = {"专注跟随", "基本跟随", "间歇走神", "明显走神", "关键段未听到"}
    base = current_state if current_state in valid else "基本跟随"
    candidates = {
        "low": ["间歇走神", "明显走神", "关键段未听到", "基本跟随"],
        "mid-low": ["间歇走神", "基本跟随", "明显走神"],
        "mid": ["基本跟随", "间歇走神", "专注跟随"],
        "mid-high": ["基本跟随", "专注跟随", "间歇走神"],
        "high": ["专注跟随", "基本跟随"],
    }
    pool = candidates.get(level, candidates["mid"])
    return base if random.random() < 0.5 else random.choice(pool)


def _default_distraction_reason(state: str, level: str) -> str:
    if state in {"专注跟随", "基本跟随"}:
        return ""
    fallback = {
        "low": "对该知识点兴趣低，且前置基础不足导致放弃跟随",
        "mid-low": "概念抽象度偏高，注意力出现断续",
        "mid": "在步骤较长处出现短时分心",
        "mid-high": "在重复性讲解环节短暂走神",
        "high": "在已掌握内容段落注意力下降",
    }
    return fallback.get(level, "注意力受到课堂外因素影响")


def _apply_level_variability(
    reactions: list[StudentReaction], subject: str, grade: str = "七年级"
) -> list[StudentReaction]:
    if not reactions:
        return reactions

    profiles = get_profiles_for_subject(subject, grade)
    profile_by_name = {p.name: p for p in profiles}

    adjusted: list[StudentReaction] = []
    for idx, reaction in enumerate(reactions):
        profile = profile_by_name.get(reaction.profile_name)
        if profile is None and idx < len(profiles):
            # Fallback by position when model profile_name is not exactly aligned with template name.
            profile = profiles[idx]

        level = profile.level if profile is not None else "mid"
        confusion_target = _sample_target_count(level, "confusion")
        error_target = _sample_target_count(level, "error")

        fallback_confusions = profile.weaknesses if profile is not None else []
        fallback_errors = profile.likely_errors if profile is not None else []
        listening_state = _normalize_listening_state_by_level(level, reaction.listening_state)

        adjusted.append(
            StudentReaction(
                profile_name=reaction.profile_name,
                engagement=_normalize_engagement_by_level(level, reaction.engagement),
                confusion_points=_fit_list_to_target(
                    reaction.confusion_points,
                    fallback_confusions,
                    confusion_target,
                    "该层学生在本节内容上可能仍有未澄清点",
                ),
                likely_questions=_dedupe_keep_order(reaction.likely_questions)[:6],
                error_predictions=_fit_list_to_target(
                    reaction.error_predictions,
                    fallback_errors,
                    error_target,
                    "该层学生可能出现类似步骤性错误",
                ),
                listening_state=listening_state,
                distraction_reason=(
                    reaction.distraction_reason.strip()
                    if reaction.distraction_reason.strip()
                    else _default_distraction_reason(listening_state, level)
                ),
                missed_key_points=_dedupe_keep_order(reaction.missed_key_points)[:4],
            )
        )

    return adjusted


def build_report_from_parsed(
    parsed: dict[str, Any],
    *,
    subject: str,
    lesson_topic: str,
    grade: str,
    original_lesson_material: str,
    analysis_mode: str = "quick",
    teacher_script: str = "",
    lesson_modules: list | None = None,
    module_interactions: list | None = None,
    module_deliberations: list | None = None,
) -> SimulationReport:
    key_points = _as_list(parsed.get("key_points"))[:12]

    reactions: list[StudentReaction] = []
    for item in parsed.get("reactions", []):
        if not isinstance(item, dict):
            continue
        reactions.append(
            StudentReaction(
                profile_name=str(item.get("profile_name", "未命名画像")),
                engagement=str(item.get("engagement", "中")),
                confusion_points=_as_list(item.get("confusion_points"))[:6],
                likely_questions=_as_list(item.get("likely_questions"))[:6],
                error_predictions=_as_list(item.get("error_predictions"))[:6],
                listening_state=str(item.get("listening_state", "基本跟随")),
                distraction_reason=str(item.get("distraction_reason", "")).strip(),
                missed_key_points=_as_list(item.get("missed_key_points"))[:4],
            )
        )

    reactions = _apply_level_variability(reactions, subject, grade)

    diff_obj = parsed.get("difficulty", {}) if isinstance(parsed.get("difficulty"), dict) else {}
    difficulty = DifficultyAssessment(
        overall_level=str(diff_obj.get("overall_level", "中")),
        cognitive_load_score=_as_int(diff_obj.get("cognitive_load_score", 6), 6),
        step_complexity_score=_as_int(diff_obj.get("step_complexity_score", 6), 6),
        concept_span_score=_as_int(diff_obj.get("concept_span_score", 6), 6),
        rationale=_as_list(diff_obj.get("rationale"))[:6],
    )

    confidence = None
    if isinstance(parsed.get("confidence"), dict):
        confidence_obj = parsed.get("confidence", {})
        confidence = ConfidenceAssessment(
            overall_level=str(confidence_obj.get("overall_level", "中")),
            overall_score=max(0, min(100, _as_int(confidence_obj.get("overall_score", 65), 65))),
            rationale=_as_list(confidence_obj.get("rationale"))[:6],
            profile_confidence=_as_list(confidence_obj.get("profile_confidence"))[:12],
        )

    suggestions: list[OptimizationSuggestion] = []
    for item in parsed.get("suggestions", []):
        if not isinstance(item, dict):
            continue
        suggestions.append(
            OptimizationSuggestion(
                priority=str(item.get("priority", "中")),
                issue=str(item.get("issue", "待补充问题")),
                suggestion=str(item.get("suggestion", "待补充建议")),
                expected_impact=str(item.get("expected_impact", "待补充效果")),
            )
        )

    lesson_plan_change_summary = _as_list(parsed.get("lesson_plan_change_summary"))[:10]
    revised_lesson_plan = str(parsed.get("revised_lesson_plan", "")).strip()

    return SimulationReport(
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        analysis_mode=analysis_mode,
        original_lesson_material=original_lesson_material,
        extracted_key_points=key_points,
        reactions=reactions,
        difficulty=difficulty,
        confidence=confidence,
        suggestions=suggestions,
        lesson_plan_change_summary=lesson_plan_change_summary,
        revised_lesson_plan=revised_lesson_plan,
        teacher_script=teacher_script,
        lesson_modules=lesson_modules or [],
        module_interactions=module_interactions or [],
        module_deliberations=module_deliberations or [],
    )


def analyze_with_llm(
    text: str,
    subject: str,
    lesson_topic: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    improvement_focus: str = "all",
) -> SimulationReport:
    system_prompt = f"你是严谨的{subject}教学分析助手，需要结合年级特征给出可执行建议，且必须只输出JSON。"
    user_prompt = _build_prompt(text=text, subject=subject, lesson_topic=lesson_topic, grade=grade, improvement_focus=improvement_focus)

    raw = invoke_llm(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=180,
    )
    parsed = _extract_json_block(raw)
    return build_report_from_parsed(
        parsed,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        original_lesson_material=text,
        analysis_mode="quick",
    )
