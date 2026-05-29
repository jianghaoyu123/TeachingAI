from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .models import StudentProfile
from .profile_runtime import get_catalog_profiles, get_grade_band_label
from .topic_profile_adjustments import TopicAdjustmentRule, apply_topic_adjustments

DEFAULT_STUDENT_NAMES_BY_LEVEL = {
    "low": "李明",
    "mid-low": "王悦",
    "mid": "张晨",
    "mid-high": "陈睿",
    "high": "赵晴",
}

# 兼容旧代码引用：默认指向初中数学画像
DEFAULT_PROFILES = get_catalog_profiles("数学", "七年级")

CUSTOM_PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "custom_profiles.json"


def _profile_to_dict(profile: StudentProfile) -> dict:
    return {
        "name": profile.name,
        "level": profile.level,
        "strengths": profile.strengths,
        "weaknesses": profile.weaknesses,
        "likely_errors": profile.likely_errors,
        "support_needs": profile.support_needs,
        "activity_level": int(profile.activity_level),
        "baseline_success_rate": int(profile.baseline_success_rate),
        "focus_stability": int(profile.focus_stability),
        "knowledge_coverage": int(profile.knowledge_coverage),
    }


def _profile_from_dict(data: dict) -> StudentProfile:
    def _bounded_int(value: object, default: int, *, allow_missing_sentinel: bool = False) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if allow_missing_sentinel and parsed < 0:
            return -1
        return max(0, min(100, parsed))

    return StudentProfile(
        name=str(data.get("name", "未命名画像")),
        level=str(data.get("level", "mid")),
        strengths=[str(v) for v in data.get("strengths", []) if str(v).strip()],
        weaknesses=[str(v) for v in data.get("weaknesses", []) if str(v).strip()],
        likely_errors=[str(v) for v in data.get("likely_errors", []) if str(v).strip()],
        support_needs=[str(v) for v in data.get("support_needs", []) if str(v).strip()],
        activity_level=_bounded_int(data.get("activity_level", -1), -1, allow_missing_sentinel=True),
        baseline_success_rate=_bounded_int(data.get("baseline_success_rate", -1), -1, allow_missing_sentinel=True),
        focus_stability=_bounded_int(data.get("focus_stability", -1), -1, allow_missing_sentinel=True),
        knowledge_coverage=_bounded_int(data.get("knowledge_coverage", -1), -1, allow_missing_sentinel=True),
    )


def _read_custom_templates() -> dict[str, list[StudentProfile]]:
    if not CUSTOM_PROFILE_PATH.exists():
        return {}

    try:
        raw = json.loads(CUSTOM_PROFILE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    result: dict[str, list[StudentProfile]] = {}
    for subject, items in raw.items():
        if not isinstance(subject, str) or not isinstance(items, list):
            continue
        result[subject] = [_profile_from_dict(item) for item in items if isinstance(item, dict)]
    return result


def _write_custom_templates(templates: dict[str, list[StudentProfile]]) -> None:
    payload: dict[str, list[dict]] = {}
    for subject, profiles in templates.items():
        payload[subject] = [_profile_to_dict(p) for p in profiles]

    CUSTOM_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_PROFILE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_profiles_for_subject(subject: str, grade: str = "七年级") -> str:
    profiles = get_profiles_for_subject(subject, grade)
    payload = {
        "subject": subject,
        "grade": grade,
        "grade_band": get_grade_band_label(grade),
        "profiles": [_profile_to_dict(p) for p in profiles],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_profiles_for_subject(subject: str, json_text: str) -> None:
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("模板文件格式错误：根节点必须是对象。")

    if "profiles" in data and isinstance(data["profiles"], list):
        raw_profiles = data["profiles"]
    elif "subject" in data and "profiles" in data:
        raw_profiles = data.get("profiles", [])
    else:
        raise ValueError("模板文件格式错误：缺少 profiles 字段。")

    profiles = [_profile_from_dict(item) for item in raw_profiles if isinstance(item, dict)]
    if not profiles:
        raise ValueError("模板文件中没有可用画像。")

    save_custom_profiles_for_subject(subject, profiles)


def save_custom_profiles_for_subject(subject: str, profiles: list[StudentProfile]) -> None:
    templates = _read_custom_templates()
    templates[subject] = profiles
    _write_custom_templates(templates)


def clear_custom_profiles_for_subject(subject: str) -> None:
    templates = _read_custom_templates()
    if subject in templates:
        del templates[subject]
        _write_custom_templates(templates)


def get_profile_template_source(subject: str) -> str:
    custom = _read_custom_templates()
    if subject in custom and custom[subject]:
        return "custom"
    return "builtin"


def _apply_default_student_names(profiles: list[StudentProfile]) -> list[StudentProfile]:
    named = deepcopy(profiles)
    for idx, profile in enumerate(named, start=1):
        fallback_name = f"学生{idx}"
        profile.name = DEFAULT_STUDENT_NAMES_BY_LEVEL.get(profile.level, fallback_name)
    return named


def _apply_quant_defaults(profiles: list[StudentProfile]) -> list[StudentProfile]:
    return _apply_quant_defaults_by_level(profiles, force_by_level=False)


def _level_quant_defaults(level: str) -> tuple[int, int, int, int]:
    # (activity_level, baseline_success_rate, focus_stability, knowledge_coverage)
    level_defaults = {
        "low": (42, 38, 40, 35),
        "mid-low": (52, 50, 48, 46),
        "mid": (62, 62, 60, 58),
        "mid-high": (72, 74, 72, 68),
        "high": (82, 86, 82, 78),
    }
    return level_defaults.get(level, level_defaults["mid"])


def _apply_quant_defaults_by_level(
    profiles: list[StudentProfile], *, force_by_level: bool
) -> list[StudentProfile]:
    named = deepcopy(profiles)
    for profile in named:
        activity_default, success_default, focus_default, coverage_default = _level_quant_defaults(profile.level)

        def _normalize(value: int, default_value: int) -> int:
            if force_by_level:
                return default_value
            if int(value) < 0:
                return default_value
            return max(0, min(100, int(value)))

        profile.activity_level = _normalize(profile.activity_level, activity_default)
        profile.baseline_success_rate = _normalize(profile.baseline_success_rate, success_default)
        profile.focus_stability = _normalize(profile.focus_stability, focus_default)
        profile.knowledge_coverage = _normalize(profile.knowledge_coverage, coverage_default)
    return named


def get_builtin_profiles_for_subject(
    subject: str,
    grade: str = "七年级",
    lesson_topic: str = "",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> list[StudentProfile]:
    profiles = get_catalog_profiles(subject, grade)
    builtin_profiles = _apply_quant_defaults_by_level(_apply_default_student_names(profiles), force_by_level=True)
    return apply_topic_adjustments(builtin_profiles, subject, lesson_topic, dynamic_topic_rules)


def get_profiles_for_subject(
    subject: str,
    grade: str = "七年级",
    lesson_topic: str = "",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> list[StudentProfile]:
    custom = _read_custom_templates()
    if subject in custom and custom[subject]:
        return apply_topic_adjustments(
            _apply_quant_defaults(custom[subject]),
            subject,
            lesson_topic,
            dynamic_topic_rules,
        )
    return get_builtin_profiles_for_subject(subject, grade, lesson_topic, dynamic_topic_rules)
