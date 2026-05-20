from __future__ import annotations

from collections.abc import Callable

from .deep_simulation import analyze_deep_with_llm
from .llm_api import analyze_with_llm
from .models import SimulationReport

ProgressCallback = Callable[[str, int, int], None]


def analyze_with_model_api(
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
    return analyze_with_llm(
        text=text,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        improvement_focus=improvement_focus,
    )


def analyze_deep_with_model_api(
    text: str,
    subject: str,
    lesson_topic: str,
    grade: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    progress_callback: ProgressCallback | None = None,
    improvement_focus: str = "all",
) -> SimulationReport:
    return analyze_deep_with_llm(
        text=text,
        subject=subject,
        lesson_topic=lesson_topic,
        grade=grade,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        progress_callback=progress_callback,
        improvement_focus=improvement_focus,
    )
