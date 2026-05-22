from __future__ import annotations

import streamlit as st

from teachingai_app.core.models import StudentProfile
from teachingai_app.core.profiles import (
    clear_custom_profiles_for_subject,
    export_profiles_for_subject,
    get_builtin_profiles_for_subject,
    get_grade_band_label,
    get_profiles_for_subject,
    import_profiles_for_subject,
    save_custom_profiles_for_subject,
)
from teachingai_app.ui.constants import (
    PROFILE_LEVEL_FULL_LABELS,
    PROFILE_LEVEL_LABELS,
    PROFILE_LEVEL_OPTIONS,
)


def _parse_multiline_list(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


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


def _ensure_editor_state(subject: str, grade: str) -> tuple[list[StudentProfile], list[StudentProfile], dict[str, StudentProfile], str, str, str, list[dict]]:
    profiles = get_profiles_for_subject(subject, grade)
    builtin_profiles = get_builtin_profiles_for_subject(subject, grade)
    level_template_map = {p.level: p for p in builtin_profiles}
    key_scope = f"{subject}_{grade}"
    editor_key = f"profile_editor_state_{key_scope}"
    next_id_key = f"{editor_key}_next_id"

    if editor_key not in st.session_state:
        st.session_state[editor_key] = [
            _profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(profiles)
        ]
        st.session_state[next_id_key] = len(st.session_state[editor_key]) + 1

    buffer: list[dict] = st.session_state[editor_key]
    return profiles, builtin_profiles, level_template_map, key_scope, editor_key, next_id_key, buffer


def _add_student_to_editor_state(subject: str, grade: str) -> int:
    _, builtin_profiles, level_template_map, _, editor_key, next_id_key, buffer = _ensure_editor_state(subject, grade)
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


def _set_profile_editor_open(subject: str, grade: str, is_open: bool) -> None:
    key_scope = f"{subject}_{grade}"
    st.session_state[f"profile_editor_open_{key_scope}"] = is_open
    if not is_open:
        st.session_state.pop(f"profile_editor_focus_{key_scope}", None)


def _profile_card_theme(level: str) -> tuple[str, str, str]:
    palette = {
        "low": ("#C2410C", "#FFF7ED", "#FDBA74"),
        "mid-low": ("#B45309", "#FFFBEB", "#FCD34D"),
        "mid": ("#0F766E", "#F0FDFA", "#99F6E4"),
        "mid-high": ("#1D4ED8", "#EFF6FF", "#93C5FD"),
        "high": ("#7C3AED", "#F5F3FF", "#C4B5FD"),
    }
    return palette.get(level, ("#0F766E", "#F8FAFC", "#CBD5E1"))


def _render_profile_editor_contents(subject: str, grade: str) -> None:
    profiles, builtin_profiles, level_template_map, key_scope, editor_key, next_id_key, buffer = _ensure_editor_state(subject, grade)
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

                if st.button("恢复该学生为当前层级默认项", key=f"{editor_key}_reset_{sid}", use_container_width=True):
                    template = level_template_map.get(level)
                    if template is not None:
                        updated: list[dict] = []
                        for row in buffer:
                            if int(row["id"]) == sid:
                                updated.append(
                                    {
                                        "id": sid,
                                        "name": name.strip() or f"学生{idx}",
                                        "level": level,
                                        "strengths": list(template.strengths),
                                        "weaknesses": list(template.weaknesses),
                                        "likely_errors": list(template.likely_errors),
                                        "support_needs": list(template.support_needs),
                                        "activity_level": int(template.activity_level),
                                        "baseline_success_rate": int(template.baseline_success_rate),
                                        "focus_stability": int(template.focus_stability),
                                        "knowledge_coverage": int(template.knowledge_coverage),
                                    }
                                )
                            else:
                                updated.append(row)
                        st.session_state[editor_key] = updated
                    st.rerun()

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

                    if st.button("恢复该学生为当前层级默认项", key=f"{editor_key}_reset_{sid}", use_container_width=True):
                        template = level_template_map.get(level)
                        if template is not None:
                            updated: list[dict] = []
                            for row in buffer:
                                if int(row["id"]) == sid:
                                    updated.append(
                                        {
                                            "id": sid,
                                            "name": name.strip() or f"学生{idx}",
                                            "level": level,
                                            "strengths": list(template.strengths),
                                            "weaknesses": list(template.weaknesses),
                                            "likely_errors": list(template.likely_errors),
                                            "support_needs": list(template.support_needs),
                                            "activity_level": int(template.activity_level),
                                            "baseline_success_rate": int(template.baseline_success_rate),
                                            "focus_stability": int(template.focus_stability),
                                            "knowledge_coverage": int(template.knowledge_coverage),
                                        }
                                    )
                                else:
                                    updated.append(row)
                            st.session_state[editor_key] = updated
                        st.rerun()

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

    save_button_label = "保存当前学生配置" if focus_student_id is not None else "保存当前学科学生配置"
    if st.button(save_button_label, key=f"save_profiles_{key_scope}", use_container_width=True):
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


@st.dialog("当前学科学生配置", width="large")
def _render_profile_editor_dialog(subject: str, grade: str) -> None:
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材进度参照广东深圳）；"
        "修改年级或学科后内置模板会随之切换。"
    )
    _render_profile_editor_contents(subject, grade)

    if st.button("关闭窗口", key=f"close_profile_editor_{subject}_{grade}", use_container_width=True):
        _set_profile_editor_open(subject, grade, False)
        st.rerun()


def render_profile_editor(subject: str, grade: str) -> None:
    _, _, _, key_scope, editor_key, next_id_key, buffer = _ensure_editor_state(subject, grade)
    is_single_student_mode = st.session_state.get(f"profile_editor_focus_{key_scope}") is not None
    is_dialog_open = bool(st.session_state.get(f"profile_editor_open_{key_scope}"))

    st.markdown("##### 当前学科待模拟学生")
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材进度参照广东深圳）；"
        "修改年级或学科后内置模板会随之切换。"
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
                        _set_profile_editor_open(subject, grade, True)
                        st.rerun()
                    if st.button(
                        "删除",
                        key=f"delete_profile_card_{key_scope}_{sid}",
                        use_container_width=True,
                        disabled=len(buffer) <= 1,
                    ):
                        st.session_state[editor_key] = [row for row in buffer if int(row["id"]) != sid]
                        _set_profile_editor_open(subject, grade, False)
                        if st.session_state.get(f"profile_editor_focus_{key_scope}") == sid:
                            st.session_state.pop(f"profile_editor_focus_{key_scope}", None)
                        st.rerun()
    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("新增学生", key=f"add_student_{key_scope}", use_container_width=True):
            new_id = _add_student_to_editor_state(subject, grade)
            st.session_state[f"profile_editor_focus_{key_scope}"] = new_id
            _set_profile_editor_open(subject, grade, True)
            st.rerun()
    with action_col2:
        if st.button(
            "学生画像重置为默认模板",
            key=f"restore_profiles_{key_scope}_main",
            use_container_width=True,
        ):
            clear_custom_profiles_for_subject(subject)
            st.session_state.pop(editor_key, None)
            st.session_state.pop(next_id_key, None)
            st.success("已恢复为内置模板。")
            st.rerun()

    st.download_button(
        label="导出当前学科画像模板(JSON)",
        data=export_profiles_for_subject(subject, grade),
        file_name=f"profile_template_{subject}.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded_profile_json = st.file_uploader(
        "导入画像模板(JSON，覆盖当前学科)",
        type=["json"],
        key=f"profile_import_{key_scope}",
    )
    if uploaded_profile_json is not None and st.button(
        "应用导入模板",
        key=f"apply_profile_import_{key_scope}",
        use_container_width=True,
    ):
        try:
            import_profiles_for_subject(
                subject=subject,
                json_text=uploaded_profile_json.getvalue().decode("utf-8", errors="ignore"),
            )
            st.session_state.pop(editor_key, None)
            st.session_state.pop(next_id_key, None)
            st.success("导入成功，当前学科已更新为导入模板。")
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f"导入失败: {exc}")

    if is_dialog_open:
        _render_profile_editor_dialog(subject, grade)
