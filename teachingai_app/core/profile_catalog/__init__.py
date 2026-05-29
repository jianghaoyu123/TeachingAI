from __future__ import annotations

import json
from pathlib import Path

from ..models import StudentProfile
from ._bands import BAND_LABELS, resolve_grade_band

_JSON_PROFILE_CATALOG_DIR = Path(__file__).resolve().parent.parent / "profile_catalog_json"


def _profile_from_json(item: dict) -> StudentProfile:
    def _bounded_int(value: object, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, min(100, parsed))

    return StudentProfile(
        name=str(item.get("name", "未命名画像")).strip() or "未命名画像",
        level=str(item.get("level", "mid")).strip() or "mid",
        strengths=[str(v).strip() for v in item.get("strengths", []) if str(v).strip()],
        weaknesses=[str(v).strip() for v in item.get("weaknesses", []) if str(v).strip()],
        likely_errors=[str(v).strip() for v in item.get("likely_errors", []) if str(v).strip()],
        support_needs=[str(v).strip() for v in item.get("support_needs", []) if str(v).strip()],
        activity_level=_bounded_int(item.get("activity_level", 50), 50),
        baseline_success_rate=_bounded_int(item.get("baseline_success_rate", 60), 60),
        focus_stability=_bounded_int(item.get("focus_stability", 60), 60),
        knowledge_coverage=_bounded_int(item.get("knowledge_coverage", 50), 50),
    )


def _load_json_subject_catalog() -> dict[str, dict[str, list[StudentProfile]]]:
    index_path = _JSON_PROFILE_CATALOG_DIR / "index.json"
    if not index_path.exists():
        raise RuntimeError(f"默认画像 JSON 索引不存在: {index_path}")

    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"默认画像 JSON 索引解析失败: {index_path}") from exc
    except OSError as exc:
        raise RuntimeError(f"默认画像 JSON 索引读取失败: {index_path}") from exc

    subjects = index_data.get("subjects") if isinstance(index_data, dict) else None
    if not isinstance(subjects, dict) or not subjects:
        raise RuntimeError(f"默认画像 JSON 索引缺少 subjects 映射: {index_path}")

    catalog: dict[str, dict[str, list[StudentProfile]]] = {}
    for subject, relative_path in subjects.items():
        if not isinstance(subject, str) or not isinstance(relative_path, str):
            continue
        file_path = _JSON_PROFILE_CATALOG_DIR / relative_path
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"默认画像 JSON 解析失败: {file_path}") from exc
        except OSError as exc:
            raise RuntimeError(f"默认画像 JSON 读取失败: {file_path}") from exc
        if not isinstance(payload, dict):
            continue
        bands = payload.get("bands")
        if not isinstance(bands, dict):
            continue

        band_profiles: dict[str, list[StudentProfile]] = {}
        for band, raw_profiles in bands.items():
            if not isinstance(band, str) or not isinstance(raw_profiles, list):
                continue
            parsed = [
                _profile_from_json(item)
                for item in raw_profiles
                if isinstance(item, dict)
            ]
            if parsed:
                band_profiles[band] = parsed

        if band_profiles:
            catalog[subject] = band_profiles

    if not catalog:
        raise RuntimeError("默认画像 JSON 加载后为空，请检查 profile_catalog_json 目录内容。")
    return catalog


SUBJECT_CATALOG: dict[str, dict[str, list[StudentProfile]]] = _load_json_subject_catalog()


def get_catalog_profiles(subject: str, grade: str) -> list[StudentProfile]:
    band = resolve_grade_band(grade)
    catalog = SUBJECT_CATALOG.get(subject)
    if catalog is None:
        catalog = SUBJECT_CATALOG.get("数学")
        if catalog is None and SUBJECT_CATALOG:
            catalog = next(iter(SUBJECT_CATALOG.values()))
        if catalog is None:
            return []
    profiles = catalog.get(band)
    if profiles is None:
        profiles = catalog.get("junior_8", [])
    return profiles


def get_grade_band_label(grade: str) -> str:
    return BAND_LABELS.get(resolve_grade_band(grade), "初二（八年级）·深圳")
