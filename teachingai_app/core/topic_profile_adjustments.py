from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import StudentProfile


PROFILE_LEVELS = ("low", "mid-low", "mid", "mid-high", "high")


@dataclass(frozen=True)
class LevelAdjustment:
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    likely_errors: tuple[str, ...] = ()
    support_needs: tuple[str, ...] = ()
    activity_delta: int = 0
    baseline_success_delta: int = 0
    focus_delta: int = 0
    coverage_delta: int = 0


@dataclass(frozen=True)
class TopicAdjustmentRule:
    keywords: tuple[str, ...]
    label: str
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    likely_errors: tuple[str, ...] = ()
    support_needs: tuple[str, ...] = ()
    activity_delta: int = 0
    baseline_success_delta: int = 0
    focus_delta: int = 0
    coverage_delta: int = 0
    level_overrides: tuple[tuple[str, LevelAdjustment], ...] = ()

def _normalize_topic(text: str) -> str:
    return (text or "").strip().lower()


def _append_unique(items: list[str], additions: tuple[str, ...]) -> list[str]:
    seen = {item.strip() for item in items if item.strip()}
    result = [item for item in items if item.strip()]
    for addition in additions:
        normalized = addition.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _bounded_delta(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-12, min(12, parsed))


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return tuple(items)


def _normalize_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    return level if level in PROFILE_LEVELS else ""


def _build_level_adjustment(value: Any) -> LevelAdjustment:
    if not isinstance(value, dict):
        return LevelAdjustment()
    return LevelAdjustment(
        strengths=_as_str_tuple(value.get("strengths")),
        weaknesses=_as_str_tuple(value.get("weaknesses")),
        likely_errors=_as_str_tuple(value.get("likely_errors")),
        support_needs=_as_str_tuple(value.get("support_needs")),
        activity_delta=_bounded_delta(value.get("activity_delta", 0)),
        baseline_success_delta=_bounded_delta(value.get("baseline_success_delta", 0)),
        focus_delta=_bounded_delta(value.get("focus_delta", 0)),
        coverage_delta=_bounded_delta(value.get("coverage_delta", 0)),
    )


def _parse_level_overrides(value: Any) -> tuple[tuple[str, LevelAdjustment], ...]:
    if not isinstance(value, dict):
        return ()
    parsed: list[tuple[str, LevelAdjustment]] = []
    for raw_level, raw_adjustment in value.items():
        level = _normalize_level(raw_level)
        if not level:
            continue
        parsed.append((level, _build_level_adjustment(raw_adjustment)))
    return tuple(parsed)


def _pick_adjustment_for_level(rule: TopicAdjustmentRule, level: str) -> LevelAdjustment:
    normalized_level = _normalize_level(level)
    if normalized_level:
        for override_level, override_adjustment in rule.level_overrides:
            if override_level == normalized_level:
                return override_adjustment
    return LevelAdjustment(
        strengths=rule.strengths,
        weaknesses=rule.weaknesses,
        likely_errors=rule.likely_errors,
        support_needs=rule.support_needs,
        activity_delta=rule.activity_delta,
        baseline_success_delta=rule.baseline_success_delta,
        focus_delta=rule.focus_delta,
        coverage_delta=rule.coverage_delta,
    )


def build_rule_from_dict(data: dict[str, Any]) -> TopicAdjustmentRule | None:
    if not isinstance(data, dict):
        return None
    keywords = _as_str_tuple(data.get("keywords"))
    label = str(data.get("label", "")).strip()
    if not keywords or not label:
        return None
    return TopicAdjustmentRule(
        keywords=keywords,
        label=label,
        strengths=_as_str_tuple(data.get("strengths")),
        weaknesses=_as_str_tuple(data.get("weaknesses")),
        likely_errors=_as_str_tuple(data.get("likely_errors")),
        support_needs=_as_str_tuple(data.get("support_needs")),
        activity_delta=_bounded_delta(data.get("activity_delta", 0)),
        baseline_success_delta=_bounded_delta(data.get("baseline_success_delta", 0)),
        focus_delta=_bounded_delta(data.get("focus_delta", 0)),
        coverage_delta=_bounded_delta(data.get("coverage_delta", 0)),
        level_overrides=_parse_level_overrides(data.get("level_overrides")),
    )


def match_topic_adjustments(
    subject: str,
    lesson_topic: str,
    dynamic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> tuple[TopicAdjustmentRule, ...]:
    topic = _normalize_topic(lesson_topic)
    if not topic:
        return ()

    # Dynamic-only mode: if no dynamic rules are generated/passed in, do not apply any topic correction.
    if not dynamic_rules:
        return ()
    rules = list(dynamic_rules)
    matched: list[TopicAdjustmentRule] = []
    for rule in rules:
        if any(keyword.lower() in topic for keyword in rule.keywords):
            matched.append(rule)
    return tuple(matched)


def describe_topic_adjustments(
    subject: str,
    lesson_topic: str,
    dynamic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> list[str]:
    return [rule.label for rule in match_topic_adjustments(subject, lesson_topic, dynamic_rules)]


def apply_topic_adjustments(
    profiles: list[StudentProfile],
    subject: str,
    lesson_topic: str,
    dynamic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> list[StudentProfile]:
    rules = match_topic_adjustments(subject, lesson_topic, dynamic_rules)
    if not rules:
        return profiles

    adjusted: list[StudentProfile] = []
    for profile in profiles:
        current = StudentProfile(
            name=profile.name,
            level=profile.level,
            strengths=list(profile.strengths),
            weaknesses=list(profile.weaknesses),
            likely_errors=list(profile.likely_errors),
            support_needs=list(profile.support_needs),
            activity_level=profile.activity_level,
            baseline_success_rate=profile.baseline_success_rate,
            focus_stability=profile.focus_stability,
            knowledge_coverage=profile.knowledge_coverage,
        )
        for rule in rules:
            adjustment = _pick_adjustment_for_level(rule, profile.level)
            current.strengths = _append_unique(current.strengths, adjustment.strengths)
            current.weaknesses = _append_unique(current.weaknesses, adjustment.weaknesses)
            current.likely_errors = _append_unique(current.likely_errors, adjustment.likely_errors)
            current.support_needs = _append_unique(current.support_needs, adjustment.support_needs)
            current.activity_level = _clamp_score(current.activity_level + adjustment.activity_delta)
            current.baseline_success_rate = _clamp_score(
                current.baseline_success_rate + adjustment.baseline_success_delta
            )
            current.focus_stability = _clamp_score(current.focus_stability + adjustment.focus_delta)
            current.knowledge_coverage = _clamp_score(
                current.knowledge_coverage + adjustment.coverage_delta
            )
        adjusted.append(current)
    return adjusted