from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .models import StudentProfile
from .profile_catalog import get_catalog_profiles, get_grade_band_label

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
    }


def _profile_from_dict(data: dict) -> StudentProfile:
    return StudentProfile(
        name=str(data.get("name", "未命名画像")),
        level=str(data.get("level", "mid")),
        strengths=[str(v) for v in data.get("strengths", []) if str(v).strip()],
        weaknesses=[str(v) for v in data.get("weaknesses", []) if str(v).strip()],
        likely_errors=[str(v) for v in data.get("likely_errors", []) if str(v).strip()],
        support_needs=[str(v) for v in data.get("support_needs", []) if str(v).strip()],
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


def get_builtin_profiles_for_subject(subject: str, grade: str = "七年级") -> list[StudentProfile]:
    profiles = get_catalog_profiles(subject, grade)
    return _apply_default_student_names(profiles)


def get_profiles_for_subject(subject: str, grade: str = "七年级") -> list[StudentProfile]:
    custom = _read_custom_templates()
    if subject in custom and custom[subject]:
        return custom[subject]
    return get_builtin_profiles_for_subject(subject, grade)
