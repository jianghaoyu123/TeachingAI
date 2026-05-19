from __future__ import annotations

from ..models import StudentProfile
from ._bands import BAND_LABELS, resolve_grade_band
from .biology import PROFILES_BY_BAND as BIOLOGY_PROFILES
from .chemistry import PROFILES_BY_BAND as CHEMISTRY_PROFILES
from .chinese import PROFILES_BY_BAND as CHINESE_PROFILES
from .english import PROFILES_BY_BAND as ENGLISH_PROFILES
from .geography import PROFILES_BY_BAND as GEOGRAPHY_PROFILES
from .history import PROFILES_BY_BAND as HISTORY_PROFILES
from .math import PROFILES_BY_BAND as MATH_PROFILES
from .physics import PROFILES_BY_BAND as PHYSICS_PROFILES
from .politics import PROFILES_BY_BAND as POLITICS_PROFILES

SUBJECT_CATALOG: dict[str, dict[str, list[StudentProfile]]] = {
    "数学": MATH_PROFILES,
    "语文": CHINESE_PROFILES,
    "英语": ENGLISH_PROFILES,
    "物理": PHYSICS_PROFILES,
    "化学": CHEMISTRY_PROFILES,
    "生物": BIOLOGY_PROFILES,
    "历史": HISTORY_PROFILES,
    "地理": GEOGRAPHY_PROFILES,
    "政治": POLITICS_PROFILES,
}


def get_catalog_profiles(subject: str, grade: str) -> list[StudentProfile]:
    band = resolve_grade_band(grade)
    catalog = SUBJECT_CATALOG.get(subject)
    if catalog is None:
        catalog = MATH_PROFILES
    profiles = catalog.get(band)
    if profiles is None:
        profiles = catalog.get("junior_8", [])
    return profiles


def get_grade_band_label(grade: str) -> str:
    return BAND_LABELS.get(resolve_grade_band(grade), "初二（八年级）·深圳")
