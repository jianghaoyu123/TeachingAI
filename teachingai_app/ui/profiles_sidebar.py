from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

from teachingai_app.core.ingestion import ParseError, merge_text_sources, parse_file
from teachingai_app.core.llm_api import generate_topic_adjustments_with_llm
from teachingai_app.core.models import StudentProfile
from teachingai_app.core.profiles import (
    clear_custom_profiles_for_subject,
    export_profiles_for_subject,
    get_builtin_profiles_for_subject,
    get_grade_band_label,
    get_profiles_for_subject,
    get_profile_template_source,
    import_profiles_for_subject,
    save_custom_profiles_for_subject,
)
from teachingai_app.core.topic_profile_adjustments import TopicAdjustmentRule, describe_topic_adjustments
from teachingai_app.ui.constants import (
    PROFILE_LEVEL_FULL_LABELS,
    PROFILE_LEVEL_LABELS,
    PROFILE_LEVEL_OPTIONS,
)


def _parse_multiline_list(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _safe_filename_stem(raw_name: str, *, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", raw_name).strip(" .")
    return cleaned or fallback


def _open_save_json_dialog(*, title: str, default_filename: str) -> str:
    try:
        from tkinter import Tk, filedialog
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("当前环境无法打开系统文件窗口。") from exc

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.asksaveasfilename(
            title=title,
            initialfile=default_filename,
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
    finally:
        root.destroy()
    return str(selected).strip()


def _open_import_json_dialog(*, title: str) -> str:
    try:
        from tkinter import Tk, filedialog
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("当前环境无法打开系统文件窗口，可能因为App运行于服务器上。") from exc

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
    finally:
        root.destroy()
    return str(selected).strip()


def _build_student_profile_payload(item: dict, subject: str, grade: str) -> str:
    payload = {
        "subject": subject,
        "grade": grade,
        "profile": {
            "name": str(item.get("name", "")).strip() or "未命名学生",
            "level": str(item.get("level", "mid")),
            "strengths": list(item.get("strengths", [])),
            "weaknesses": list(item.get("weaknesses", [])),
            "likely_errors": list(item.get("likely_errors", [])),
            "support_needs": list(item.get("support_needs", [])),
            "activity_level": int(item.get("activity_level", 50)),
            "baseline_success_rate": int(item.get("baseline_success_rate", 60)),
            "focus_stability": int(item.get("focus_stability", 60)),
            "knowledge_coverage": int(item.get("knowledge_coverage", 50)),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_imported_student_profile(json_text: str) -> dict:
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("导入文件格式错误：根节点必须是对象。")

    raw_profile = data.get("profile")
    if raw_profile is None:
        raw_profile = data
    if not isinstance(raw_profile, dict):
        raise ValueError("导入文件格式错误：缺少 profile 对象。")

    level = str(raw_profile.get("level", "mid"))
    if level not in PROFILE_LEVEL_OPTIONS:
        level = "mid"

    def _safe_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, min(100, parsed))

    def _safe_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()]

    return {
        "name": str(raw_profile.get("name", "")).strip() or "未命名学生",
        "level": level,
        "strengths": _safe_str_list(raw_profile.get("strengths", [])),
        "weaknesses": _safe_str_list(raw_profile.get("weaknesses", [])),
        "likely_errors": _safe_str_list(raw_profile.get("likely_errors", [])),
        "support_needs": _safe_str_list(raw_profile.get("support_needs", [])),
        "activity_level": _safe_int(raw_profile.get("activity_level", 50), 50),
        "baseline_success_rate": _safe_int(raw_profile.get("baseline_success_rate", 60), 60),
        "focus_stability": _safe_int(raw_profile.get("focus_stability", 60), 60),
        "knowledge_coverage": _safe_int(raw_profile.get("knowledge_coverage", 50), 50),
    }


def _profile_to_editor_item(profile: StudentProfile, student_id: int) -> dict:
    return {
        "id": student_id,
        "name": profile.name,
        "level": profile.level if profile.level in PROFILE_LEVEL_OPTIONS else "mid",
        "strengths": list(profile.strengths),
        "weaknesses": list(profile.weaknesses),
        "likely_errors": list(profile.likely_errors),
        "support_needs": list(profile.support_needs),
        "activity_level": int(profile.activity_level),
        "baseline_success_rate": int(profile.baseline_success_rate),
        "focus_stability": int(profile.focus_stability),
        "knowledge_coverage": int(profile.knowledge_coverage),
    }


def _normalize_lesson_topic(lesson_topic: str) -> str:
    return str(lesson_topic or "").strip()


def _build_editor_scope(subject: str, grade: str, lesson_topic: str) -> str:
    normalized_topic = _normalize_lesson_topic(lesson_topic)
    topic_scope = re.sub(r"\s+", "_", normalized_topic) if normalized_topic else "__empty_topic__"
    return f"{subject}_{grade}_{topic_scope}"


REALTIME_PROFILE_SNAPSHOT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "realtime_profile_snapshots.db"
RUNTIME_SNAPSHOT_USER_ID_KEY = "runtime_snapshot_user_id"
SNAPSHOT_TTL_SECONDS = 30 * 60
SNAPSHOT_MAX_ROWS = 200


def _current_region_curriculum() -> str:
    return str(st.session_state.get("region_curriculum_input", "广东深圳")).strip() or "广东深圳"


def _get_runtime_snapshot_user_id() -> str:
    existing = str(st.session_state.get(RUNTIME_SNAPSHOT_USER_ID_KEY, "")).strip()
    if existing:
        return existing
    generated = uuid.uuid4().hex
    st.session_state[RUNTIME_SNAPSHOT_USER_ID_KEY] = generated
    return generated


def _profile_to_snapshot_dict(profile: StudentProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "level": profile.level,
        "strengths": list(profile.strengths),
        "weaknesses": list(profile.weaknesses),
        "likely_errors": list(profile.likely_errors),
        "support_needs": list(profile.support_needs),
        "activity_level": int(profile.activity_level),
        "baseline_success_rate": int(profile.baseline_success_rate),
        "focus_stability": int(profile.focus_stability),
        "knowledge_coverage": int(profile.knowledge_coverage),
    }


def _profile_from_snapshot_dict(data: dict[str, Any]) -> StudentProfile:
    return StudentProfile(
        name=str(data.get("name", "未命名学生")).strip() or "未命名学生",
        level=str(data.get("level", "mid")),
        strengths=[str(v).strip() for v in data.get("strengths", []) if str(v).strip()],
        weaknesses=[str(v).strip() for v in data.get("weaknesses", []) if str(v).strip()],
        likely_errors=[str(v).strip() for v in data.get("likely_errors", []) if str(v).strip()],
        support_needs=[str(v).strip() for v in data.get("support_needs", []) if str(v).strip()],
        activity_level=int(data.get("activity_level", 50)),
        baseline_success_rate=int(data.get("baseline_success_rate", 60)),
        focus_stability=int(data.get("focus_stability", 60)),
        knowledge_coverage=int(data.get("knowledge_coverage", 50)),
    )


def _build_realtime_snapshot_key(
    subject: str,
    grade: str,
    lesson_topic: str,
    region_curriculum: str | None = None,
    user_id: str | None = None,
) -> str:
    payload = {
        "user_id": str(user_id or _get_runtime_snapshot_user_id()).strip() or "anonymous",
        "subject": subject,
        "grade": grade,
        "lesson_topic": _normalize_lesson_topic(lesson_topic),
        "region_curriculum": str(region_curriculum or _current_region_curriculum()).strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_legacy_realtime_snapshot_key(subject: str, grade: str, lesson_topic: str, region_curriculum: str | None = None) -> str:
    payload = {
        "subject": subject,
        "grade": grade,
        "lesson_topic": _normalize_lesson_topic(lesson_topic),
        "region_curriculum": str(region_curriculum or _current_region_curriculum()).strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _get_snapshot_db_conn() -> sqlite3.Connection:
    REALTIME_PROFILE_SNAPSHOT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REALTIME_PROFILE_SNAPSHOT_DB_PATH, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS realtime_profile_snapshots (
            snapshot_key TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            grade TEXT NOT NULL,
            lesson_topic TEXT NOT NULL,
            region_curriculum TEXT NOT NULL,
            rules_signature TEXT NOT NULL,
            profiles_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_realtime_profile_snapshots_scope
        ON realtime_profile_snapshots(subject, grade, lesson_topic, region_curriculum)
        """
    )
    _cleanup_snapshot_rows(conn)
    return conn


def _cleanup_snapshot_rows(conn: sqlite3.Connection) -> None:
    # Remove stale snapshot records first (TTL cleanup).
    conn.execute(
        """
        DELETE FROM realtime_profile_snapshots
        WHERE updated_at < datetime('now', ?)
        """,
        (f"-{int(SNAPSHOT_TTL_SECONDS)} seconds",),
    )

    # Enforce a hard row cap by dropping the oldest rows.
    row = conn.execute("SELECT COUNT(*) FROM realtime_profile_snapshots").fetchone()
    total_rows = int(row[0]) if row and row[0] is not None else 0
    overflow = total_rows - int(SNAPSHOT_MAX_ROWS)
    if overflow > 0:
        conn.execute(
            """
            DELETE FROM realtime_profile_snapshots
            WHERE snapshot_key IN (
                SELECT snapshot_key
                FROM realtime_profile_snapshots
                ORDER BY datetime(updated_at) ASC
                LIMIT ?
            )
            """,
            (overflow,),
        )


def _save_realtime_profile_snapshot(
    *,
    subject: str,
    grade: str,
    lesson_topic: str,
    region_curriculum: str,
    profiles: list[StudentProfile],
    rules_signature: str,
) -> None:
    if not _normalize_lesson_topic(lesson_topic):
        return
    snapshot_key = _build_realtime_snapshot_key(subject, grade, lesson_topic, region_curriculum)
    profiles_json = json.dumps(
        [_profile_to_snapshot_dict(profile) for profile in profiles],
        ensure_ascii=False,
    )
    with _get_snapshot_db_conn() as conn:
        conn.execute(
            """
            INSERT INTO realtime_profile_snapshots (
                snapshot_key,
                subject,
                grade,
                lesson_topic,
                region_curriculum,
                rules_signature,
                profiles_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(snapshot_key) DO UPDATE SET
                rules_signature = excluded.rules_signature,
                profiles_json = excluded.profiles_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                snapshot_key,
                subject,
                grade,
                _normalize_lesson_topic(lesson_topic),
                str(region_curriculum or _current_region_curriculum()).strip(),
                str(rules_signature or "[]"),
                profiles_json,
            ),
        )


def _load_realtime_profile_snapshot(
    subject: str,
    grade: str,
    lesson_topic: str,
    region_curriculum: str | None = None,
) -> tuple[list[StudentProfile], str] | None:
    snapshot_key = _build_realtime_snapshot_key(subject, grade, lesson_topic, region_curriculum)
    with _get_snapshot_db_conn() as conn:
        row = conn.execute(
            """
            SELECT profiles_json, rules_signature
            FROM realtime_profile_snapshots
            WHERE snapshot_key = ?
            """,
            (snapshot_key,),
        ).fetchone()
        if row is None:
            legacy_snapshot_key = _build_legacy_realtime_snapshot_key(subject, grade, lesson_topic, region_curriculum)
            row = conn.execute(
                """
                SELECT profiles_json, rules_signature
                FROM realtime_profile_snapshots
                WHERE snapshot_key = ?
                """,
                (legacy_snapshot_key,),
            ).fetchone()
    if row is None:
        return None
    raw_profiles_json, rules_signature = row
    try:
        raw_profiles = json.loads(str(raw_profiles_json or "[]"))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_profiles, list) or not raw_profiles:
        return None
    profiles = [_profile_from_snapshot_dict(item) for item in raw_profiles if isinstance(item, dict)]
    if not profiles:
        return None
    return profiles, str(rules_signature or "[]")


def _queue_snapshot_restore(
    *,
    subject: str,
    grade: str,
    lesson_topic: str,
    region_curriculum: str,
) -> bool:
    snapshot = _load_realtime_profile_snapshot(subject, grade, lesson_topic, region_curriculum)
    if snapshot is None:
        return False
    profiles, rules_signature = snapshot
    key_scope = _build_editor_scope(subject, grade, lesson_topic)
    st.session_state[f"profile_editor_pending_restore_{key_scope}"] = {
        "profiles": [_profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(profiles)],
        "rules_signature": rules_signature,
    }
    return True


def _get_profile_editor_material_text() -> str:
    manual_text = str(st.session_state.get("manual_text_input", "")).strip()
    uploaded_files = st.session_state.get("lesson_files_uploader") or []

    file_signatures: list[tuple[str, int]] = []
    text_chunks: list[str] = []
    for file in uploaded_files:
        file_bytes = file.getvalue()
        file_signatures.append((str(file.name), len(file_bytes)))

    cache_payload = (tuple(file_signatures), manual_text)
    cache_key = json.dumps(cache_payload, ensure_ascii=False)
    cache_state_key = "profile_editor_material_cache"
    cache: dict[str, str] = st.session_state.setdefault(cache_state_key, {})
    if cache_key in cache:
        return cache[cache_key]

    if uploaded_files:
        with st.spinner("系统正在解析材料，请稍后..."):
            for file in uploaded_files:
                try:
                    parsed = parse_file(file.name, file.getvalue(), enable_ocr=True)
                except ParseError:
                    continue
                if parsed and parsed.strip():
                    text_chunks.append(parsed)

    if manual_text:
        text_chunks.append(manual_text)

    merged_text = merge_text_sources(text_chunks)
    cache[cache_key] = merged_text
    st.session_state[cache_state_key] = cache
    return merged_text


def _get_profile_editor_topic_rules(
    *,
    subject: str,
    grade: str,
    lesson_topic: str,
    region_curriculum: str,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[TopicAdjustmentRule, ...]:
    normalized_topic = _normalize_lesson_topic(lesson_topic)
    if not normalized_topic:
        return ()
    if get_profile_template_source(subject) == "custom":
        return ()

    material_text = _get_profile_editor_material_text()
    if not material_text.strip():
        return ()
    if not str(api_key or "").strip():
        return ()

    cache_payload = (
        subject,
        grade,
        normalized_topic,
        str(region_curriculum or "").strip(),
        str(provider or "").strip(),
        str(base_url or "").strip(),
        str(model or "").strip(),
        material_text,
    )
    cache_key = json.dumps(cache_payload, ensure_ascii=False)
    cache_state_key = "profile_editor_topic_rules_cache"
    cache: dict[str, tuple[TopicAdjustmentRule, ...]] = st.session_state.setdefault(cache_state_key, {})
    if cache_key in cache:
        return cache[cache_key]

    rules = generate_topic_adjustments_with_llm(
        text=material_text,
        subject=subject,
        lesson_topic=normalized_topic,
        grade=grade,
        region_curriculum=region_curriculum,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    cache[cache_key] = rules
    st.session_state[cache_state_key] = cache
    return rules


def _topic_rules_signature(dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None) -> str:
    if not dynamic_topic_rules:
        return "[]"
    payload = [
        {
            "keywords": list(rule.keywords),
            "label": rule.label,
            "strengths": list(rule.strengths),
            "weaknesses": list(rule.weaknesses),
            "likely_errors": list(rule.likely_errors),
            "support_needs": list(rule.support_needs),
            "activity_delta": rule.activity_delta,
            "baseline_success_delta": rule.baseline_success_delta,
            "focus_delta": rule.focus_delta,
            "coverage_delta": rule.coverage_delta,
            "level_overrides": {
                level: {
                    "strengths": list(adjustment.strengths),
                    "weaknesses": list(adjustment.weaknesses),
                    "likely_errors": list(adjustment.likely_errors),
                    "support_needs": list(adjustment.support_needs),
                    "activity_delta": adjustment.activity_delta,
                    "baseline_success_delta": adjustment.baseline_success_delta,
                    "focus_delta": adjustment.focus_delta,
                    "coverage_delta": adjustment.coverage_delta,
                }
                for level, adjustment in rule.level_overrides
            },
        }
        for rule in dynamic_topic_rules
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _render_topic_adjustment_status(
    *,
    subject: str,
    lesson_topic: str,
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...],
    api_key: str,
) -> None:
    if get_profile_template_source(subject) == "custom":
        st.info("当前学科正在使用你导入或保存的自定义学生画像；课题和材料变化时不会自动更新学生画像。")
        return

    normalized_topic = _normalize_lesson_topic(lesson_topic)
    if not normalized_topic:
        st.warning("请先输入课题名称。")
        return

    material_text = _get_profile_editor_material_text()
    if not material_text.strip():
        st.warning(f"当前课题：{normalized_topic}。上传文件或输入教案/逐字稿文本后，才会实时生成并更新学生画像。")
        return
    if not str(api_key or "").strip():
        st.info(f"当前课题：{normalized_topic}。填写 API Key 后，学生配置面板会基于当前课题和材料实时更新学生画像。")
        return

    matched_labels = describe_topic_adjustments(subject, normalized_topic, dynamic_topic_rules)
    if matched_labels:
        st.success(f"当前课题：{normalized_topic}。主题内容：{'、'.join(matched_labels)}")
        return
    st.info(f"当前课题：{normalized_topic}。本次为根据课题内容更新学生画像，将直接使用基础画像。")


def _ensure_editor_state(
    subject: str,
    grade: str,
    lesson_topic: str = "",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> tuple[list[StudentProfile], list[StudentProfile], dict[str, StudentProfile], str, str, str, list[dict]]:
    profiles = get_profiles_for_subject(subject, grade, lesson_topic, dynamic_topic_rules)
    builtin_profiles = get_builtin_profiles_for_subject(subject, grade, lesson_topic, dynamic_topic_rules)
    level_template_map = {p.level: p for p in builtin_profiles}
    key_scope = _build_editor_scope(subject, grade, lesson_topic)
    editor_key = f"profile_editor_state_{key_scope}"
    next_id_key = f"{editor_key}_next_id"
    rules_signature_key = f"{editor_key}_rules_signature"
    rules_signature = _topic_rules_signature(dynamic_topic_rules)
    pending_restore_key = f"profile_editor_pending_restore_{key_scope}"
    restored_from_pending = False

    pending_restore = st.session_state.pop(pending_restore_key, None)
    if isinstance(pending_restore, dict):
        restored_profiles = pending_restore.get("profiles")
        restored_signature = str(pending_restore.get("rules_signature", rules_signature))
        if isinstance(restored_profiles, list) and restored_profiles:
            st.session_state[editor_key] = restored_profiles
            st.session_state[next_id_key] = len(restored_profiles) + 1
            st.session_state[rules_signature_key] = restored_signature
            restored_from_pending = True

    if (not restored_from_pending) and (
        editor_key not in st.session_state or st.session_state.get(rules_signature_key) != rules_signature
    ):
        st.session_state[editor_key] = [
            _profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(profiles)
        ]
        st.session_state[next_id_key] = len(st.session_state[editor_key]) + 1
        st.session_state[rules_signature_key] = rules_signature

    buffer: list[dict] = st.session_state[editor_key]
    return profiles, builtin_profiles, level_template_map, key_scope, editor_key, next_id_key, buffer


def _add_student_to_editor_state(
    subject: str,
    grade: str,
    lesson_topic: str = "",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> int:
    _, builtin_profiles, level_template_map, _, editor_key, next_id_key, buffer = _ensure_editor_state(
        subject,
        grade,
        lesson_topic,
        dynamic_topic_rules,
    )
    new_id = int(st.session_state.get(next_id_key, len(buffer) + 1))
    st.session_state[next_id_key] = new_id + 1
    default_level = PROFILE_LEVEL_OPTIONS[len(buffer) % len(PROFILE_LEVEL_OPTIONS)]
    template = level_template_map.get(default_level, builtin_profiles[0])
    buffer.append(
        _profile_to_editor_item(
            StudentProfile(
                name=f"学生{new_id}",
                level=default_level,
                strengths=list(template.strengths),
                weaknesses=list(template.weaknesses),
                likely_errors=list(template.likely_errors),
                support_needs=list(template.support_needs),
                activity_level=int(template.activity_level),
                baseline_success_rate=int(template.baseline_success_rate),
                focus_stability=int(template.focus_stability),
                knowledge_coverage=int(template.knowledge_coverage),
            ),
            new_id,
        )
    )
    st.session_state[editor_key] = buffer
    return new_id


def _set_profile_editor_open(subject: str, grade: str, lesson_topic: str, is_open: bool) -> None:
    key_scope = _build_editor_scope(subject, grade, lesson_topic)
    st.session_state[f"profile_editor_open_{key_scope}"] = is_open
    if not is_open:
        st.session_state.pop(f"profile_editor_focus_{key_scope}", None)


def _get_level_switch_template_map(
    subject: str,
    grade: str,
    lesson_topic: str,
    builtin_profiles: list[StudentProfile],
) -> dict[str, StudentProfile]:
    snapshot = _load_realtime_profile_snapshot(subject, grade, lesson_topic)
    if snapshot is not None:
        snapshot_profiles, _ = snapshot
        return {profile.level: profile for profile in snapshot_profiles}
    return {profile.level: profile for profile in builtin_profiles}


def _apply_level_template_to_widget_state(editor_key: str, sid: int, template: StudentProfile) -> None:
    st.session_state[f"{editor_key}_strengths_{sid}"] = "\n".join(template.strengths)
    st.session_state[f"{editor_key}_weaknesses_{sid}"] = "\n".join(template.weaknesses)
    st.session_state[f"{editor_key}_errors_{sid}"] = "\n".join(template.likely_errors)
    st.session_state[f"{editor_key}_support_{sid}"] = "\n".join(template.support_needs)
    st.session_state[f"{editor_key}_activity_{sid}"] = int(template.activity_level)
    st.session_state[f"{editor_key}_success_{sid}"] = int(template.baseline_success_rate)
    st.session_state[f"{editor_key}_focus_{sid}"] = int(template.focus_stability)
    st.session_state[f"{editor_key}_coverage_{sid}"] = int(template.knowledge_coverage)


def _on_profile_editor_dismiss() -> None:
    open_keys = [
        key
        for key in st.session_state.keys()
        if isinstance(key, str) and key.startswith("profile_editor_open_")
    ]
    for key in open_keys:
        st.session_state[key] = False

    focus_keys = [
        key
        for key in st.session_state.keys()
        if isinstance(key, str) and key.startswith("profile_editor_focus_")
    ]
    for key in focus_keys:
        st.session_state.pop(key, None)


def _profile_card_theme(level: str) -> tuple[str, str, str]:
    palette = {
        "low": ("#C2410C", "#FFF7ED", "#FDBA74"),
        "mid-low": ("#B45309", "#FFFBEB", "#FCD34D"),
        "mid": ("#0F766E", "#F0FDFA", "#99F6E4"),
        "mid-high": ("#1D4ED8", "#EFF6FF", "#93C5FD"),
        "high": ("#7C3AED", "#F5F3FF", "#C4B5FD"),
    }
    return palette.get(level, ("#0F766E", "#F8FAFC", "#CBD5E1"))


def _get_template_source_label(subject: str) -> str:
    source = get_profile_template_source(subject)
    if source == "custom":
        return "当前学生画像来源：自定义"
    return "当前学生画像来源：内置实时生成"


def _render_profile_editor_contents(
    subject: str,
    grade: str,
    lesson_topic: str = "",
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...] | None = None,
) -> None:
    profiles, builtin_profiles, level_template_map, key_scope, editor_key, next_id_key, buffer = _ensure_editor_state(
        subject,
        grade,
        lesson_topic,
        dynamic_topic_rules,
    )
    level_switch_template_map = _get_level_switch_template_map(subject, grade, lesson_topic, builtin_profiles)
    focus_student_id = st.session_state.get(f"profile_editor_focus_{key_scope}")
    is_single_student_mode = focus_student_id is not None
    render_buffer = [
        item for item in buffer if focus_student_id is None or int(item["id"]) == int(focus_student_id)
    ]

    st.caption("支持自由增减学生人数，并为每位学生单独指定层级。保存后会覆盖该学科当前模板。")

    edited_rows: list[dict] = []
    for idx, item in enumerate(render_buffer, start=1):
        sid = int(item["id"])
        current_level = str(item.get("level", "mid"))
        student_name = str(item.get("name", f"学生{idx}"))
        level_label = PROFILE_LEVEL_FULL_LABELS.get(
            current_level,
            PROFILE_LEVEL_LABELS.get(current_level, current_level),
        )

        with st.container(border=True):
            if is_single_student_mode:
                st.markdown(f"**{student_name}｜{level_label}**")
                name_col, level_col = st.columns([2, 3])
                with name_col:
                    name = st.text_input(
                        "姓名",
                        value=student_name,
                        key=f"{editor_key}_name_{sid}",
                    )
                with level_col:
                    level_index = (
                        PROFILE_LEVEL_OPTIONS.index(current_level)
                        if current_level in PROFILE_LEVEL_OPTIONS
                        else PROFILE_LEVEL_OPTIONS.index("mid")
                    )
                    level = st.selectbox(
                        "层级",
                        PROFILE_LEVEL_OPTIONS,
                        index=level_index,
                        key=f"{editor_key}_level_{sid}",
                        format_func=lambda lv: str(
                            PROFILE_LEVEL_FULL_LABELS.get(lv, PROFILE_LEVEL_LABELS.get(lv, lv))
                        ),
                    )
                if level != current_level:
                    switched_template = level_switch_template_map.get(level) or level_template_map.get(level)
                    if switched_template is not None:
                        _apply_level_template_to_widget_state(editor_key, sid, switched_template)

                strengths = st.text_area(
                    "优势（每行一项）",
                    value="\n".join(item.get("strengths", [])),
                    key=f"{editor_key}_strengths_{sid}",
                )
                weaknesses = st.text_area(
                    "薄弱点（每行一项）",
                    value="\n".join(item.get("weaknesses", [])),
                    key=f"{editor_key}_weaknesses_{sid}",
                )
                likely_errors = st.text_area(
                    "常见错误（每行一项）",
                    value="\n".join(item.get("likely_errors", [])),
                    key=f"{editor_key}_errors_{sid}",
                )
                support_needs = st.text_area(
                    "需要的教学支持（每行一项）",
                    value="\n".join(item.get("support_needs", [])),
                    key=f"{editor_key}_support_{sid}",
                )

                st.caption("量化画像（0-100）：用于约束模拟稳定性与结果评估")
                metric_col1, metric_col2 = st.columns(2)
                with metric_col1:
                    activity_level = st.slider(
                        "学习活跃度",
                        min_value=0,
                        max_value=100,
                        value=int(item.get("activity_level", 50)),
                        key=f"{editor_key}_activity_{sid}",
                    )
                    st.caption("越高，越可能主动回应、提问、参与。")
                    focus_stability = st.slider(
                        "专注稳定性",
                        min_value=0,
                        max_value=100,
                        value=int(item.get("focus_stability", 60)),
                        key=f"{editor_key}_focus_{sid}",
                    )
                    st.caption("越高，表示更不容易在长讲解里掉线。")
                with metric_col2:
                    baseline_success_rate = st.slider(
                        "基线正确率",
                        min_value=0,
                        max_value=100,
                        value=int(item.get("baseline_success_rate", 60)),
                        key=f"{editor_key}_success_{sid}",
                    )
                    st.caption("越高，表示这类学生在还没被点拨前也更容易答对。")
                    knowledge_coverage = st.slider(
                        "知识覆盖度",
                        min_value=0,
                        max_value=100,
                        value=int(item.get("knowledge_coverage", 50)),
                        key=f"{editor_key}_coverage_{sid}",
                    )
                    st.caption("越高，表示已掌握的前置知识更完整。")

            else:
                with st.expander(
                    f"{student_name}｜{level_label}",
                    expanded=False,
                ):
                    name_col, level_col = st.columns([2, 3])
                    with name_col:
                        name = st.text_input(
                            "姓名",
                            value=student_name,
                            key=f"{editor_key}_name_{sid}",
                        )
                    with level_col:
                        level_index = (
                            PROFILE_LEVEL_OPTIONS.index(current_level)
                            if current_level in PROFILE_LEVEL_OPTIONS
                            else PROFILE_LEVEL_OPTIONS.index("mid")
                        )
                        level = st.selectbox(
                            "层级",
                            PROFILE_LEVEL_OPTIONS,
                            index=level_index,
                            key=f"{editor_key}_level_{sid}",
                            format_func=lambda lv: str(
                                PROFILE_LEVEL_FULL_LABELS.get(lv, PROFILE_LEVEL_LABELS.get(lv, lv))
                            ),
                        )
                    if level != current_level:
                        switched_template = level_switch_template_map.get(level) or level_template_map.get(level)
                        if switched_template is not None:
                            _apply_level_template_to_widget_state(editor_key, sid, switched_template)

                    strengths = st.text_area(
                        "优势（每行一项）",
                        value="\n".join(item.get("strengths", [])),
                        key=f"{editor_key}_strengths_{sid}",
                    )
                    weaknesses = st.text_area(
                        "薄弱点（每行一项）",
                        value="\n".join(item.get("weaknesses", [])),
                        key=f"{editor_key}_weaknesses_{sid}",
                    )
                    likely_errors = st.text_area(
                        "常见错误（每行一项）",
                        value="\n".join(item.get("likely_errors", [])),
                        key=f"{editor_key}_errors_{sid}",
                    )
                    support_needs = st.text_area(
                        "需要的教学支持（每行一项）",
                        value="\n".join(item.get("support_needs", [])),
                        key=f"{editor_key}_support_{sid}",
                    )

                    st.caption("量化画像（0-100）：用于约束模拟稳定性与结果评估")
                    metric_col1, metric_col2 = st.columns(2)
                    with metric_col1:
                        activity_level = st.slider(
                            "学习活跃度",
                            min_value=0,
                            max_value=100,
                            value=int(item.get("activity_level", 50)),
                            key=f"{editor_key}_activity_{sid}",
                        )
                        st.caption("越高，越可能主动回应、提问、参与。")
                        focus_stability = st.slider(
                            "专注稳定性",
                            min_value=0,
                            max_value=100,
                            value=int(item.get("focus_stability", 60)),
                            key=f"{editor_key}_focus_{sid}",
                        )
                        st.caption("越高，表示更不容易在长讲解里掉线。")
                    with metric_col2:
                        baseline_success_rate = st.slider(
                            "基线正确率",
                            min_value=0,
                            max_value=100,
                            value=int(item.get("baseline_success_rate", 60)),
                            key=f"{editor_key}_success_{sid}",
                        )
                        st.caption("越高，表示这类学生在还没被点拨前也更容易答对。")
                        knowledge_coverage = st.slider(
                            "知识覆盖度",
                            min_value=0,
                            max_value=100,
                            value=int(item.get("knowledge_coverage", 50)),
                            key=f"{editor_key}_coverage_{sid}",
                        )
                        st.caption("越高，表示已掌握的前置知识更完整。")

        edited_rows.append(
            {
                "id": sid,
                "name": name.strip() or f"学生{idx}",
                "level": level,
                "strengths": _parse_multiline_list(strengths),
                "weaknesses": _parse_multiline_list(weaknesses),
                "likely_errors": _parse_multiline_list(likely_errors),
                "support_needs": _parse_multiline_list(support_needs),
                "activity_level": int(activity_level),
                "baseline_success_rate": int(baseline_success_rate),
                "focus_stability": int(focus_stability),
                "knowledge_coverage": int(knowledge_coverage),
            }
        )

    if edited_rows:
        edited_by_id = {int(row["id"]): row for row in edited_rows}
        st.session_state[editor_key] = [
            edited_by_id.get(int(row["id"]), row)
            for row in buffer
        ]
        buffer = st.session_state[editor_key]

    if focus_student_id is not None:
        current_student = next(
            (row for row in st.session_state[editor_key] if int(row["id"]) == int(focus_student_id)),
            None,
        )
        if current_student is not None:
            student_name = str(current_student.get("name", "未命名学生")).strip() or "未命名学生"
            single_export_col, single_import_col = st.columns(2)
            with single_export_col:
                safe_name = _safe_filename_stem(student_name, fallback="student")
                st.download_button(
                    "导出当前学生画像",
                    data=_build_student_profile_payload(current_student, subject, grade),
                    file_name=f"student_profile_{safe_name}.json",
                    mime="application/json",
                    key=f"export_single_profile_{key_scope}_{focus_student_id}",
                    use_container_width=True,
                )

            with single_import_col:
                single_import_open_key = f"import_single_profile_open_{key_scope}_{focus_student_id}"
                single_import_file_key = f"import_single_profile_file_{key_scope}_{focus_student_id}"
                if not bool(st.session_state.get(single_import_open_key)):
                    if st.button(
                        "导入学生画像",
                        key=f"open_single_profile_import_{key_scope}_{focus_student_id}",
                        use_container_width=True,
                    ):
                        st.session_state[single_import_open_key] = True
                        st.rerun()
                else:
                    single_import_file = st.file_uploader(
                        "选择学生画像 JSON 文件",
                        type=["json"],
                        key=single_import_file_key,
                    )
                    apply_col, cancel_col = st.columns(2)
                    with apply_col:
                        if st.button(
                            "学生画像导入",
                            key=f"import_single_profile_apply_{key_scope}_{focus_student_id}",
                            use_container_width=True,
                            disabled=single_import_file is None,
                        ):
                            try:
                                if single_import_file is None:
                                    st.info("请先选择一个 JSON 文件。")
                                else:
                                    imported_profile = _parse_imported_student_profile(
                                        single_import_file.getvalue().decode("utf-8")
                                    )
                                    updated_rows: list[dict] = []
                                    for row in st.session_state[editor_key]:
                                        if int(row["id"]) == int(focus_student_id):
                                            merged_row = dict(row)
                                            merged_row.update(imported_profile)
                                            updated_rows.append(merged_row)
                                        else:
                                            updated_rows.append(row)
                                    st.session_state[editor_key] = updated_rows
                                    st.session_state[single_import_open_key] = False
                                    st.session_state.pop(single_import_file_key, None)
                                    st.success("当前学生画像导入成功。")
                                    st.rerun()
                            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                                st.error(f"导入失败: {exc}")
                    with cancel_col:
                        if st.button(
                            "取消",
                            key=f"cancel_single_profile_import_{key_scope}_{focus_student_id}",
                            use_container_width=True,
                        ):
                            st.session_state[single_import_open_key] = False
                            st.session_state.pop(single_import_file_key, None)
                            st.rerun()


def _save_profiles_from_editor_state(subject: str, key_scope: str, editor_key: str, next_id_key: str) -> None:
    profiles_to_save = [
        StudentProfile(
            name=str(item.get("name", "")).strip() or f"学生{idx}",
            level=str(item.get("level", "mid")),
            strengths=list(item.get("strengths", [])),
            weaknesses=list(item.get("weaknesses", [])),
            likely_errors=list(item.get("likely_errors", [])),
            support_needs=list(item.get("support_needs", [])),
            activity_level=int(item.get("activity_level", 50)),
            baseline_success_rate=int(item.get("baseline_success_rate", 60)),
            focus_stability=int(item.get("focus_stability", 60)),
            knowledge_coverage=int(item.get("knowledge_coverage", 50)),
        )
        for idx, item in enumerate(st.session_state[editor_key], start=1)
    ]
    save_custom_profiles_for_subject(subject, profiles_to_save)
    st.session_state[editor_key] = [
        _profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(profiles_to_save)
    ]
    st.session_state[next_id_key] = len(profiles_to_save) + 1
    st.success("学生配置已保存，后续分析会优先使用该自定义模板。")


@st.dialog("当前学科学生配置", width="large", on_dismiss=_on_profile_editor_dismiss)
def _render_profile_editor_dialog(
    subject: str,
    grade: str,
    region_curriculum: str,
    lesson_topic: str,
    dynamic_topic_rules: tuple[TopicAdjustmentRule, ...],
    api_key: str,
) -> None:
    _, _, _, key_scope, editor_key, next_id_key, _ = _ensure_editor_state(
        subject,
        grade,
        lesson_topic,
        dynamic_topic_rules,
    )
    focus_student_id = st.session_state.get(f"profile_editor_focus_{key_scope}")
    st.caption(_get_template_source_label(subject))
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材地区: {region_curriculum}）；"
        "修改年级或学科后或输入材料后内置模板会随之切换。"
    )
    _render_topic_adjustment_status(
        subject=subject,
        lesson_topic=lesson_topic,
        dynamic_topic_rules=dynamic_topic_rules,
        api_key=api_key,
    )
    _render_profile_editor_contents(subject, grade, lesson_topic, dynamic_topic_rules)

    bottom_save_col, bottom_close_col = st.columns(2)
    save_button_label = "保存当前学生配置" if focus_student_id is not None else "保存当前学科学生配置"
    with bottom_save_col:
        if st.button(save_button_label, key=f"save_profiles_{key_scope}", use_container_width=True):
            _save_profiles_from_editor_state(subject, key_scope, editor_key, next_id_key)
    with bottom_close_col:
        if st.button("关闭窗口", key=f"close_profile_editor_{subject}_{grade}", use_container_width=True):
            _set_profile_editor_open(subject, grade, lesson_topic, False)
            st.rerun()


def render_profile_editor(
    subject: str,
    grade: str,
    region_curriculum: str = "广东深圳",
    lesson_topic: str = "",
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> None:
    dynamic_topic_rules = _get_profile_editor_topic_rules(
        subject=subject,
        grade=grade,
        lesson_topic=lesson_topic,
        region_curriculum=region_curriculum,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    profiles, _, _, key_scope, editor_key, next_id_key, buffer = _ensure_editor_state(
        subject,
        grade,
        lesson_topic,
        dynamic_topic_rules,
    )
    if (
        get_profile_template_source(subject) != "custom"
        and _normalize_lesson_topic(lesson_topic)
        and _get_profile_editor_material_text().strip()
        and str(api_key or "").strip()
    ):
        _save_realtime_profile_snapshot(
            subject=subject,
            grade=grade,
            lesson_topic=lesson_topic,
            region_curriculum=region_curriculum,
            profiles=profiles,
            rules_signature=_topic_rules_signature(dynamic_topic_rules),
        )
    focus_student_id = st.session_state.get(f"profile_editor_focus_{key_scope}")
    is_single_student_mode = focus_student_id is not None
    is_dialog_open = bool(st.session_state.get(f"profile_editor_open_{key_scope}")) and focus_student_id is not None

    st.markdown("##### 当前学科待模拟学生")
    st.caption(_get_template_source_label(subject))
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材地区: {region_curriculum}）；"
        "修改年级或学科或输入材料后内置模板会随之切换。"
    )
    _render_topic_adjustment_status(
        subject=subject,
        lesson_topic=lesson_topic,
        dynamic_topic_rules=dynamic_topic_rules,
        api_key=api_key,
    )
    st.markdown(
        """
        <style>
        .student-card {
            position: relative;
            overflow: hidden;
            border-radius: 14px;
            margin: -0.55rem -0.6rem -6.55rem;
            padding: 0.55rem 0.6rem 6.75rem;
            background:
                radial-gradient(180px 90px at 100% 0%, color-mix(in srgb, var(--card-soft) 86%, white) 0%, transparent 70%),
                linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, var(--card-soft) 100%);
        }
        .student-card::before {
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--card-accent) 0%, var(--card-accent-soft) 100%);
        }
        .student-card-head {
            display: flex;
            align-items: center;
            gap: 9px;
            margin-bottom: 6px;
        }
        .student-card-avatar {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 800;
            color: var(--card-accent);
            background: linear-gradient(135deg, var(--card-soft) 0%, white 100%);
            border: 1px solid color-mix(in srgb, var(--card-accent-soft) 65%, white);
        }
        .student-card-meta {
            min-width: 0;
            flex: 1;
        }
        .student-card-name {
            font-size: 14px;
            font-weight: 800;
            color: #1F2937;
            line-height: 1.15;
            margin-bottom: 4px;
        }
        .student-card-level {
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            color: var(--card-accent);
            background: color-mix(in srgb, var(--card-soft) 80%, white);
            border: 1px solid color-mix(in srgb, var(--card-accent-soft) 72%, white);
            border-radius: 999px;
            padding: 2px 8px;
        }
        .student-card-divider {
            height: 1px;
            margin: 8px 0 8px;
            background: linear-gradient(90deg, rgba(148, 163, 184, 0.12) 0%, rgba(148, 163, 184, 0.34) 50%, rgba(148, 163, 184, 0.12) 100%);
        }
        div[data-testid="column"] div[data-testid="stButton"] > button[kind="secondary"] {
            min-height: 2rem;
            padding: 0.15rem 0.5rem;
            font-size: 0.8rem;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.18);
            backdrop-filter: blur(4px);
        }
        div[data-testid="column"] div[data-testid="stButton"] > button[kind="secondary"] p {
            font-size: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for row_start in range(0, len(buffer), 5):
        card_columns = st.columns(5)
        for col_idx, item in enumerate(buffer[row_start: row_start + 5]):
            idx = row_start + col_idx
            sid = int(item["id"])
            student_name = str(item.get("name", f"学生{idx + 1}"))
            level = str(item.get("level", "mid"))
            level_label = PROFILE_LEVEL_FULL_LABELS.get(level, PROFILE_LEVEL_LABELS.get(level, level))
            accent, soft, accent_soft = _profile_card_theme(level)
            avatar_text = student_name[:1] if student_name else "学"
            with card_columns[col_idx]:
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div class="student-card" style="--card-accent:{accent};--card-soft:{soft};--card-accent-soft:{accent_soft};">
                            <div class="student-card-head">
                                <div class="student-card-avatar">{avatar_text}</div>
                                <div class="student-card-meta">
                                    <div class="student-card-name">{student_name}</div>
                                    <div class="student-card-level">{level_label}</div>
                                </div>
                            </div>
                            <div class="student-card-divider"></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "配置",
                        key=f"open_profile_editor_{key_scope}_{sid}",
                        use_container_width=True,
                    ):
                        st.session_state[f"profile_editor_focus_{key_scope}"] = sid
                        _set_profile_editor_open(subject, grade, lesson_topic, True)
                        st.rerun()
                    if st.button(
                        "删除",
                        key=f"delete_profile_card_{key_scope}_{sid}",
                        use_container_width=True,
                        disabled=len(buffer) <= 1,
                    ):
                        st.session_state[editor_key] = [row for row in buffer if int(row["id"]) != sid]
                        _set_profile_editor_open(subject, grade, lesson_topic, False)
                        if st.session_state.get(f"profile_editor_focus_{key_scope}") == sid:
                            st.session_state.pop(f"profile_editor_focus_{key_scope}", None)
                        st.rerun()
    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("新增学生", key=f"add_student_{key_scope}", use_container_width=True):
            new_id = _add_student_to_editor_state(subject, grade, lesson_topic, dynamic_topic_rules)
            st.session_state[f"profile_editor_focus_{key_scope}"] = new_id
            _set_profile_editor_open(subject, grade, lesson_topic, True)
            st.rerun()
    with action_col2:
        if st.button(
            "学生画像重置为默认模板",
            key=f"restore_profiles_{key_scope}_main",
            use_container_width=True,
        ):
            clear_custom_profiles_for_subject(subject)
            restored_from_snapshot = _queue_snapshot_restore(
                subject=subject,
                grade=grade,
                lesson_topic=lesson_topic,
                region_curriculum=region_curriculum,
            )
            st.session_state.pop(editor_key, None)
            st.session_state.pop(next_id_key, None)
            if restored_from_snapshot:
                st.success("已从临时实时学生画像快照恢复。")
            else:
                st.success("已恢复为内置模板。")
            st.rerun()

    batch_export_col, batch_import_col = st.columns(2)
    with batch_export_col:
        safe_subject = _safe_filename_stem(subject, fallback="subject")
        st.download_button(
            "批量导出画像模板",
            data=export_profiles_for_subject(subject, grade),
            file_name=f"profile_template_{safe_subject}.json",
            mime="application/json",
            key=f"export_profiles_{key_scope}",
            use_container_width=True,
        )

    with batch_import_col:
        batch_import_open_key = f"apply_profile_import_open_{key_scope}"
        batch_import_file_key = f"apply_profile_import_file_{key_scope}"
        if not bool(st.session_state.get(batch_import_open_key)):
            if st.button(
                "导入画像模板",
                key=f"open_profile_import_{key_scope}",
                use_container_width=True,
            ):
                st.session_state[batch_import_open_key] = True
                st.rerun()
        else:
            batch_import_file = st.file_uploader(
                "选择画像模板 JSON 文件",
                type=["json"],
                key=batch_import_file_key,
            )
            apply_col, cancel_col = st.columns(2)
            with apply_col:
                if st.button(
                    "学生模板批量导入",
                    key=f"apply_profile_import_{key_scope}",
                    use_container_width=True,
                    disabled=batch_import_file is None,
                ):
                    try:
                        if batch_import_file is None:
                            st.info("请先选择一个 JSON 文件。")
                        else:
                            import_profiles_for_subject(
                                subject=subject,
                                json_text=batch_import_file.getvalue().decode("utf-8"),
                            )
                            st.session_state.pop(editor_key, None)
                            st.session_state.pop(next_id_key, None)
                            st.session_state[batch_import_open_key] = False
                            st.session_state.pop(batch_import_file_key, None)
                            st.success("导入成功，当前学科已更新为导入模板。")
                            st.rerun()
                    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                        st.error(f"导入失败: {exc}")
            with cancel_col:
                if st.button(
                    "取消",
                    key=f"cancel_profile_import_{key_scope}",
                    use_container_width=True,
                ):
                    st.session_state[batch_import_open_key] = False
                    st.session_state.pop(batch_import_file_key, None)
                    st.rerun()

    if is_dialog_open:
        _render_profile_editor_dialog(
            subject,
            grade,
            region_curriculum,
            lesson_topic,
            dynamic_topic_rules,
            api_key,
        )
