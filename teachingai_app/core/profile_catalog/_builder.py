from __future__ import annotations

from copy import deepcopy

from ..models import StudentProfile

LEVEL_ORDER = ["low", "mid-low", "mid", "mid-high", "high"]
LEVEL_FIELDS = ("strengths", "weaknesses", "likely_errors", "support_needs")

LEVEL_TYPE_NAMES = {
    "low": "基础薄弱型",
    "mid-low": "中等偏下型",
    "mid": "中等稳定型",
    "mid-high": "中等偏上型",
    "high": "拔高拓展型",
}


def build_profiles(level_specs: dict[str, dict[str, list[str]]]) -> list[StudentProfile]:
    profiles: list[StudentProfile] = []
    for level in LEVEL_ORDER:
        spec = level_specs.get(level)
        if spec is None:
            continue
        profiles.append(
            StudentProfile(
                name=LEVEL_TYPE_NAMES[level],
                level=level,
                strengths=list(spec.get("strengths", [])),
                weaknesses=list(spec.get("weaknesses", [])),
                likely_errors=list(spec.get("likely_errors", [])),
                support_needs=list(spec.get("support_needs", [])),
            )
        )
    return profiles


def _inject_band_scope(
    specs: dict[str, dict[str, list[str]]], scope_lines: list[str]
) -> None:
    if not scope_lines:
        return
    scope_text = " ".join(scope_lines)
    for level_spec in specs.values():
        level_spec.setdefault("strengths", []).append(
            f"【深圳学段教材】{scope_lines[0]}"
        )
        level_spec.setdefault("support_needs", []).insert(
            0,
            f"教学预演请对齐深圳本地进度：{scope_text}",
        )


def _apply_band_overlay(
    specs: dict[str, dict[str, list[str]]], overlay: dict[str, list[str]]
) -> None:
    if not overlay:
        return
    for level_spec in specs.values():
        for field, items in overlay.items():
            if field in LEVEL_FIELDS and items:
                level_spec.setdefault(field, []).extend(items)


def build_secondary_band_specs(
    base_specs: dict[str, dict[str, list[str]]],
    subject: str,
    band: str,
) -> dict[str, dict[str, list[str]]]:
    from ._sz_curriculum import SUBJECT_BAND_OVERLAY, SUBJECT_BAND_SCOPE

    specs = deepcopy(base_specs)
    scopes = SUBJECT_BAND_SCOPE.get(subject, SUBJECT_BAND_SCOPE["_default"])
    overlays = SUBJECT_BAND_OVERLAY.get(subject, {})
    _inject_band_scope(specs, scopes.get(band, []))
    _apply_band_overlay(specs, overlays.get(band, {}))
    return specs


def build_full_catalog(
    primary_lower: dict[str, dict[str, list[str]]],
    primary_upper: dict[str, dict[str, list[str]]],
    junior_base: dict[str, dict[str, list[str]]],
    senior_base: dict[str, dict[str, list[str]]],
    subject: str,
) -> dict[str, list[StudentProfile]]:
    from ._bands import JUNIOR_BANDS, SENIOR_BANDS

    catalog: dict[str, list[StudentProfile]] = {
        "primary_lower": build_profiles(primary_lower),
        "primary_upper": build_profiles(primary_upper),
    }
    for band in JUNIOR_BANDS:
        catalog[band] = build_profiles(build_secondary_band_specs(junior_base, subject, band))
    for band in SENIOR_BANDS:
        catalog[band] = build_profiles(build_secondary_band_specs(senior_base, subject, band))
    return catalog
