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
    }


def _render_profile_editor_contents(subject: str, grade: str) -> None:
    profiles = get_profiles_for_subject(subject, grade)
    builtin_profiles = get_builtin_profiles_for_subject(subject, grade)
    level_template_map = {p.level: p for p in builtin_profiles}
    editor_key = f"profile_editor_state_{subject}"
    next_id_key = f"{editor_key}_next_id"

    st.caption("支持自由增减学生人数，并为每位学生单独指定层级。保存后会覆盖该学科当前模板。")

    if editor_key not in st.session_state:
        st.session_state[editor_key] = [
            _profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(profiles)
        ]
        st.session_state[next_id_key] = len(st.session_state[editor_key]) + 1

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
        key=f"profile_import_{subject}",
    )
    if uploaded_profile_json is not None and st.button(
        "应用导入模板", key=f"apply_profile_import_{subject}", use_container_width=True
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

    buffer: list[dict] = st.session_state[editor_key]
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新增学生", key=f"add_student_{subject}", use_container_width=True):
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
                    ),
                    new_id,
                )
            )
            st.session_state[editor_key] = buffer
            st.rerun()
    with col2:
        if st.button(
            "删除最后一位",
            key=f"remove_last_student_{subject}",
            use_container_width=True,
            disabled=len(buffer) <= 1,
        ):
            buffer.pop()
            st.session_state[editor_key] = buffer
            st.rerun()

    edited_profiles: list[StudentProfile] = []
    removed_student_id: int | None = None
    for idx, item in enumerate(buffer, start=1):
        sid = int(item["id"])
        current_level = str(item.get("level", "mid"))
        student_name = str(item.get("name", f"学生{idx}"))
        level_label = PROFILE_LEVEL_FULL_LABELS.get(
            current_level,
            PROFILE_LEVEL_LABELS.get(current_level, current_level),
        )

        with st.container(border=True):
            with st.expander(f"学生{idx}｜{student_name}｜{level_label}", expanded=False):
                name_col, level_col = st.columns([2, 3])
                with name_col:
                    name = st.text_input(
                        f"姓名{idx}",
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
                        f"层级{idx}",
                        PROFILE_LEVEL_OPTIONS,
                        index=level_index,
                        key=f"{editor_key}_level_{sid}",
                        format_func=lambda lv: PROFILE_LEVEL_FULL_LABELS.get(
                            lv, PROFILE_LEVEL_LABELS.get(lv, lv)
                        ),
                    )

                strengths = st.text_area(
                    f"优势{idx}（每行一项）",
                    value="\n".join(item.get("strengths", [])),
                    key=f"{editor_key}_strengths_{sid}",
                )
                weaknesses = st.text_area(
                    f"薄弱点{idx}（每行一项）",
                    value="\n".join(item.get("weaknesses", [])),
                    key=f"{editor_key}_weaknesses_{sid}",
                )
                likely_errors = st.text_area(
                    f"常见错误{idx}（每行一项）",
                    value="\n".join(item.get("likely_errors", [])),
                    key=f"{editor_key}_errors_{sid}",
                )
                support_needs = st.text_area(
                    f"需要的教学支持{idx}（每行一项）",
                    value="\n".join(item.get("support_needs", [])),
                    key=f"{editor_key}_support_{sid}",
                )

                reset_col, remove_col = st.columns(2)
                with reset_col:
                    if st.button("按层级恢复默认项", key=f"{editor_key}_reset_{sid}", use_container_width=True):
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
                                        }
                                    )
                                else:
                                    updated.append(row)
                            st.session_state[editor_key] = updated
                        st.rerun()
                with remove_col:
                    if st.button(
                        "删除该学生",
                        key=f"{editor_key}_remove_{sid}",
                        use_container_width=True,
                        disabled=len(buffer) <= 1,
                    ):
                        removed_student_id = sid

        edited_profiles.append(
            StudentProfile(
                name=name.strip() or f"学生{idx}",
                level=level,
                strengths=_parse_multiline_list(strengths),
                weaknesses=_parse_multiline_list(weaknesses),
                likely_errors=_parse_multiline_list(likely_errors),
                support_needs=_parse_multiline_list(support_needs),
            )
        )


    if removed_student_id is not None:
        st.session_state[editor_key] = [s for s in buffer if int(s["id"]) != removed_student_id]
        st.rerun()

    if st.button("保存当前学科学生配置", key=f"save_profiles_{subject}", use_container_width=True):
        save_custom_profiles_for_subject(subject, edited_profiles)
        st.session_state[editor_key] = [
            _profile_to_editor_item(profile, idx + 1) for idx, profile in enumerate(edited_profiles)
        ]
        st.session_state[next_id_key] = len(edited_profiles) + 1
        st.success("学生配置已保存，后续分析会优先使用该自定义模板。")

    if st.button("恢复该学科内置模板", key=f"restore_profiles_{subject}", use_container_width=True):
        clear_custom_profiles_for_subject(subject)
        st.session_state.pop(editor_key, None)
        st.session_state.pop(next_id_key, None)
        st.success("已恢复为内置模板。")
        st.rerun()


@st.dialog("当前学科学生配置", width="large")
def _render_profile_editor_dialog(subject: str, grade: str) -> None:
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材进度参照广东深圳）；"
        "修改年级后内置模板会随之切换。"
    )
    _render_profile_editor_contents(subject, grade)

    if st.button("关闭窗口", key=f"close_profile_editor_{subject}", use_container_width=True):
        st.rerun()


def render_profile_editor(subject: str, grade: str) -> None:
    profiles = get_profiles_for_subject(subject, grade)
    legacy_dialog_open_key = f"profile_editor_dialog_open_{subject}"

    st.markdown("##### 当前学科待模拟学生")
    st.caption(
        f"内置画像已按「{get_grade_band_label(grade)}」×「{subject}」匹配（教材进度参照广东深圳）；"
        "修改年级后内置模板会随之切换。"
    )
    st.markdown(
        "**"
        + " / ".join(
            [f"{p.name}（{PROFILE_LEVEL_FULL_LABELS.get(p.level, p.level)}）" for p in profiles]
        )
        + "**"
    )

    # Legacy compatibility: clear old persistent open-state key so the dialog
    # doesn't reopen on unrelated reruns (e.g., changing provider/model).
    st.session_state.pop(legacy_dialog_open_key, None)

    if st.button("打开学生配置窗口", key=f"open_profile_editor_{subject}", use_container_width=True):
        _render_profile_editor_dialog(subject, grade)
