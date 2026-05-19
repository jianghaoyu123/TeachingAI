from __future__ import annotations

import streamlit as st

from teachingai_app.core.models import SimulationReport
from teachingai_app.core.profiles import get_profiles_for_subject
from teachingai_app.core.reporting import build_revised_plan_payload, build_student_report_payload
from teachingai_app.ui.constants import PROFILE_LEVEL_FULL_LABELS


def reaction_attention_level(
    engagement: str, confusion_count: int, error_count: int
) -> tuple[str, str, str]:
    score = confusion_count + error_count
    if engagement in {"低", "中低"}:
        score += 2
    elif engagement == "中":
        score += 1
    if score >= 9:
        return "高关注", "#B91C1C", "🔴"
    if score >= 6:
        return "中关注", "#B45309", "🟠"
    return "常规关注", "#047857", "🟢"


def render_deep_simulation_trace(report: SimulationReport) -> None:
    if report.analysis_mode != "deep":
        return

    with st.expander("深度预演：教师讲稿与分模块互动", expanded=True):
        st.markdown("**完整课堂讲稿**")
        st.text_area(
            "课堂讲稿",
            value=report.teacher_script or "（未生成）",
            height=280,
            disabled=True,
            label_visibility="collapsed",
        )
        if not report.lesson_modules:
            st.info("未返回分模块记录。")
            return

        profiles_for_display = get_profiles_for_subject(report.subject, report.grade)
        profile_level_by_name = {p.name: p.level for p in profiles_for_display}

        def level_label(name: str) -> str:
            level = profile_level_by_name.get(name, "mid")
            return PROFILE_LEVEL_FULL_LABELS.get(level, "中等稳定型")

        for module in sorted(report.lesson_modules, key=lambda m: m.order):
            st.markdown(f"#### 模块 {module.order}：{module.title}")
            st.caption(" · ".join(module.key_points) if module.key_points else "本模块讲解")
            st.text_area(
                f"模块讲解_{module.module_id}",
                value=module.teacher_script,
                height=160,
                disabled=True,
                label_visibility="collapsed",
            )
            module_items = [i for i in report.module_interactions if i.module_id == module.module_id]
            module_deliberation = next(
                (d for d in report.module_deliberations if d.module_id == module.module_id),
                None,
            )
            if module_deliberation is not None:
                st.markdown("### 讨论裁决结果（这一模块里学生、教研员讨论后，系统给出的最终归纳）")

                st.markdown("#### 模块共识（大家基本都同意的判断，可信度最高）")
                if module_deliberation.consensus:
                    st.markdown("\n".join(f"- {idx}. {item}" for idx, item in enumerate(module_deliberation.consensus, start=1)))
                else:
                    st.markdown("- 1. 本模块暂无明确共识。")

                st.markdown("#### 即时调整（老师这节课当下就可以立刻改的做法）")
                if module_deliberation.teaching_adjustments:
                    st.markdown(
                        "\n".join(
                            f"- {idx}. {item}"
                            for idx, item in enumerate(module_deliberation.teaching_adjustments, start=1)
                        )
                    )
                else:
                    st.markdown("- 1. 本模块暂无即时调整建议。")

                st.markdown("#### 模块分歧（大家意见不一致的地方，说明这里还不确定）")
                if module_deliberation.disagreements:
                    st.markdown(
                        "\n".join(
                            f"- {idx}. {item}" for idx, item in enumerate(module_deliberation.disagreements, start=1)
                        )
                    )
                else:
                    st.markdown("- 1. 本模块暂无显著分歧。")

                st.markdown("#### 记忆更新（学生状态变化，会带到下一模块继续影响表现）")
                if module_deliberation.memory_updates:
                    st.markdown(
                        "\n".join(
                            f"- {idx}. {item}" for idx, item in enumerate(module_deliberation.memory_updates, start=1)
                        )
                    )
                else:
                    st.markdown("- 1. 本模块暂无记忆状态更新。")
            if not module_items:
                continue
            student_tabs = st.tabs(
                [f"{item.profile_name}（{level_label(item.profile_name)}）" for item in module_items]
            )
            for tab, inter in zip(student_tabs, module_items):
                with tab:
                    st.markdown(f"**参与度：** {inter.engagement}")
                    st.markdown(f"**置信度：** {inter.confidence_score}/100")
                    if inter.consistency_note:
                        st.caption(f"一致性说明：{inter.consistency_note}")
                    if inter.verbal_response:
                        st.markdown(f"**课堂发言：** {inter.verbal_response}")
                    if inter.confusion_points:
                        st.markdown("**困惑点**")
                        st.markdown("\n".join(f"- {p}" for p in inter.confusion_points))
                    if inter.likely_questions:
                        st.markdown("**可能提问**")
                        st.markdown("\n".join(f"- {q}" for q in inter.likely_questions))
                    if inter.error_predictions:
                        st.markdown("**典型错误**")
                        st.markdown("\n".join(f"- {e}" for e in inter.error_predictions))


def render_simulation_results(
    report: SimulationReport,
    report_export_format: str,
    revised_export_format: str,
    revised_pptx_payload: tuple[bytes, str, str] | None = None,
) -> None:
    mode_label = "深度思考模式" if report.analysis_mode == "deep" else "快速模式"
    st.success(f"分析完成（{mode_label}）")
    render_deep_simulation_trace(report)

    st.subheader("学生反应模拟（整课汇总）")
    if report.reactions:
        profiles_for_display = get_profiles_for_subject(report.subject, report.grade)
        profile_level_by_name = {p.name: p.level for p in profiles_for_display}

        def display_name_with_level(profile_name: str) -> str:
            level = profile_level_by_name.get(profile_name, "mid")
            level_cn = PROFILE_LEVEL_FULL_LABELS.get(level, "中等稳定型")
            return f"{profile_name}（{level_cn}）"

        summary_cols = st.columns(len(report.reactions))
        for col, reaction in zip(summary_cols, report.reactions):
            attention_label, attention_color, attention_icon = reaction_attention_level(
                reaction.engagement,
                len(reaction.confusion_points),
                len(reaction.error_predictions),
            )
            with col:
                st.markdown(
                    f"<div style='border:1px solid #E5E7EB;border-radius:10px;padding:10px 12px;background:#FAFAFA;'>"
                    f"<div style='font-weight:600;margin-bottom:6px;'>{display_name_with_level(reaction.profile_name)}</div>"
                    f"<div style='font-size:13px;color:#374151;'>参与度: {reaction.engagement}</div>"
                    f"<div style='font-size:13px;color:#374151;'>困惑点: {len(reaction.confusion_points)} | 典型错误: {len(reaction.error_predictions)}</div>"
                    f"<div style='font-size:13px;color:{attention_color};font-weight:600;margin-top:4px;'>{attention_icon} {attention_label}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        reaction_tabs = st.tabs(
            [
                f"{reaction_attention_level(r.engagement, len(r.confusion_points), len(r.error_predictions))[2]} {display_name_with_level(r.profile_name)}"
                for r in report.reactions
            ]
        )
        for tab, reaction in zip(reaction_tabs, report.reactions):
            with tab:
                attention_label, attention_color, _ = reaction_attention_level(
                    reaction.engagement,
                    len(reaction.confusion_points),
                    len(reaction.error_predictions),
                )
                top_col1, top_col2 = st.columns([1, 3])
                with top_col1:
                    st.metric("参与度", reaction.engagement)
                    st.markdown(
                        f"<div style='font-size:13px;font-weight:600;color:{attention_color};'>{attention_label}</div>",
                        unsafe_allow_html=True,
                    )
                with top_col2:
                    st.markdown("**可能困惑点**")
                    st.markdown("\n".join(f"- {item}" for item in reaction.confusion_points[:6]))
                bottom_col1, bottom_col2 = st.columns(2)
                with bottom_col1:
                    st.markdown("**可能提问**")
                    st.markdown("\n".join(f"- {item}" for item in reaction.likely_questions[:6]))
                with bottom_col2:
                    st.markdown("**典型错误**")
                    st.markdown("\n".join(f"- {item}" for item in reaction.error_predictions[:6]))
    else:
        st.info("未返回学生反应模拟结果。")

    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("基本信息")
        st.write(f"学科: {report.subject} | 年级: {report.grade} | 课题: {report.lesson_topic}")
        st.write(f"分析模式: {mode_label}")
        st.subheader("关键知识点")
        st.write("、".join(report.extracted_key_points) if report.extracted_key_points else "未提取到")
        st.subheader("题目难度判断")
        if report.difficulty:
            st.metric("综合难度", report.difficulty.overall_level)
            st.write(
                f"认知负荷: {report.difficulty.cognitive_load_score}/10 | "
                f"步骤复杂度: {report.difficulty.step_complexity_score}/10 | "
                f"概念跨度: {report.difficulty.concept_span_score}/10"
            )
            for item in report.difficulty.rationale:
                st.write(f"- {item}")
        else:
            st.info("未返回难度评估结果。")

        if report.analysis_mode == "deep":
            st.subheader("结果置信度")
            if report.confidence:
                st.metric("总体置信度", f"{report.confidence.overall_score}/100")
                st.write(f"置信等级: {report.confidence.overall_level}")
                for item in report.confidence.rationale:
                    st.write(f"- {item}")
                if report.confidence.profile_confidence:
                    st.markdown("**分学生置信说明**")
                    st.markdown("\n".join(f"- {item}" for item in report.confidence.profile_confidence))
            else:
                st.info("未返回置信度结果。")
        else:
            st.caption("ℹ️ 置信度评估仅在深度思考模式下可用")
    with col2:
        st.subheader("优化建议")
        for item in report.suggestions:
            st.markdown(
                f"**[{item.priority}] {item.issue}**  \n"
                f"建议：{item.suggestion}  \n"
                f"预期效果：{item.expected_impact}"
            )

    if report.lesson_plan_change_summary:
        st.subheader("AI做了哪些修改")
        for idx, item in enumerate(report.lesson_plan_change_summary, start=1):
            st.write(f"{idx}. {item}")

    if report.original_lesson_material.strip() or report.revised_lesson_plan.strip():
        st.subheader("原教案与修订后教案对照")
        compare_col1, compare_col2 = st.columns(2)
        with compare_col1:
            st.markdown("**原教案**")
            st.text_area(
                "原教案",
                value=report.original_lesson_material,
                height=420,
                disabled=True,
                label_visibility="collapsed",
            )
        with compare_col2:
            st.markdown("**修订后教案**")
            st.text_area(
                "修订后教案",
                value=report.revised_lesson_plan,
                height=420,
                disabled=True,
                label_visibility="collapsed",
            )

    if revised_pptx_payload is None:
        download_col1, download_col2 = st.columns(2)
        download_col3 = None
    else:
        download_col1, download_col2, download_col3 = st.columns(3)
    with download_col1:
        report_data, report_file_name, report_mime = build_student_report_payload(
            report, report_export_format
        )
        st.download_button(
            label=f"下载学生反应报告（{report_export_format}）",
            data=report_data,
            file_name=report_file_name,
            mime=report_mime,
            use_container_width=True,
        )
    with download_col2:
        revised_data, revised_file_name, revised_mime = build_revised_plan_payload(
            report, revised_export_format
        )
        st.download_button(
            label=f"下载修订后教案（{revised_export_format}）",
            data=revised_data,
            file_name=revised_file_name,
            mime=revised_mime,
            use_container_width=True,
        )

    if download_col3 is not None and revised_pptx_payload is not None:
        pptx_data, pptx_file_name, pptx_mime = revised_pptx_payload
        with download_col3:
            st.download_button(
                label="下载AI修订建议版PPT（.pptx）",
                data=pptx_data,
                file_name=pptx_file_name,
                mime=pptx_mime,
                use_container_width=True,
            )
            st.caption("说明：当前版本会在原PPT末尾追加“AI修订建议”页，并把模块即时调整写入对应页备注区；原始页面正文不被覆盖。")
