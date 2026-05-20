from __future__ import annotations

from collections import defaultdict
from typing import Any

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


def _mount_virtual_classroom_theme() -> None:
    st.markdown(
        """
        <style>
        .vc-shell {
            position: relative;
            border-radius: 16px;
            padding: 16px;
            background:
                radial-gradient(1200px 220px at 20% -10%, rgba(78, 120, 87, 0.15), transparent 60%),
                radial-gradient(900px 180px at 85% 0%, rgba(196, 122, 46, 0.14), transparent 64%),
                linear-gradient(180deg, #FCFBF7 0%, #F7F4EB 100%);
            border: 1px solid #E6E2D8;
            margin-bottom: 14px;
        }
        .vc-title {
            font-size: 22px;
            font-weight: 700;
            color: #1E3A2E;
            margin-bottom: 6px;
        }
        .vc-subtitle {
            color: #5C5A53;
            font-size: 13px;
            margin-bottom: 8px;
        }
        .vc-board {
            border-radius: 12px;
            background: #203F33;
            color: #F5F8F2;
            padding: 10px 12px;
            font-size: 13px;
            border: 1px solid #305444;
            margin-top: 8px;
        }
        .vc-seat {
            border: 1px solid #E3DED1;
            background: #FFFDF8;
            border-radius: 12px;
            padding: 10px;
            min-height: 120px;
            box-shadow: 0 1px 0 rgba(30, 58, 46, 0.04);
            margin-bottom: 10px;
        }
        .vc-seat-name {
            font-weight: 700;
            color: #2E2C27;
            margin-bottom: 6px;
        }
        .vc-seat-meta {
            font-size: 12px;
            color: #5F5B4F;
            margin-bottom: 2px;
        }
        .vc-chip {
            display: inline-block;
            font-size: 11px;
            border-radius: 999px;
            padding: 2px 8px;
            background: #EEF4ED;
            color: #2A4F3C;
            border: 1px solid #CFDCCC;
            margin-right: 5px;
            margin-bottom: 5px;
        }
        .vc-timeline-title {
            font-size: 16px;
            font-weight: 700;
            color: #243A30;
            margin-top: 10px;
            margin-bottom: 4px;
        }
        .vc-qa {
            border-left: 3px solid #9FB9AA;
            padding-left: 10px;
            margin-bottom: 8px;
        }
        .vc-qa-teacher {
            border-left-color: #4A7AA1;
            background: #F3F8FD;
            border-radius: 8px;
            padding: 8px 10px;
        }
        .vc-qa-student {
            border-left-color: #8EA18F;
            background: #F7FBF5;
            border-radius: 8px;
            padding: 8px 10px;
        }
        .vc-qa-who {
            font-size: 13px;
            font-weight: 700;
            color: #1F3D31;
        }
        .vc-qa-text {
            font-size: 13px;
            color: #3F3A32;
        }
        .vc-control-shell {
            border: 1px solid #E4DECF;
            border-radius: 12px;
            padding: 10px;
            background: #FBF9F2;
            margin-bottom: 10px;
        }
        .vc-control-note {
            font-size: 12px;
            color: #5F5A4D;
            margin-top: 4px;
        }
        @media (max-width: 900px) {
            .vc-shell {
                padding: 12px;
            }
            .vc-title {
                font-size: 19px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _collect_student_names(report: SimulationReport) -> list[str]:
    names: list[str] = []
    for reaction in report.reactions:
        if reaction.profile_name and reaction.profile_name not in names:
            names.append(reaction.profile_name)
    for inter in report.module_interactions:
        if inter.profile_name and inter.profile_name not in names:
            names.append(inter.profile_name)
    return names


def _latest_module_interactions(report: SimulationReport) -> list:
    if not report.lesson_modules or not report.module_interactions:
        return []
    latest_module = max(report.lesson_modules, key=lambda m: m.order)
    return [i for i in report.module_interactions if i.module_id == latest_module.module_id]


def _aggregate_interaction_counts(report: SimulationReport) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    confusion_buckets: dict[str, set[str]] = {}
    error_buckets: dict[str, set[str]] = {}

    for inter in report.module_interactions:
        confusion_buckets.setdefault(inter.profile_name, set()).update(
            [item.strip() for item in inter.confusion_points if item.strip()]
        )
        error_buckets.setdefault(inter.profile_name, set()).update(
            [item.strip() for item in inter.error_predictions if item.strip()]
        )

    for name in set([*confusion_buckets.keys(), *error_buckets.keys()]):
        stats[name] = {
            "confusion_total": len(confusion_buckets.get(name, set())),
            "error_total": len(error_buckets.get(name, set())),
        }
    return stats


def _render_virtual_classroom_overview(report: SimulationReport) -> None:
    student_names = _collect_student_names(report)

    st.markdown(
        """
        <div class="vc-shell">
            <div class="vc-title">虚拟课堂总览</div>
            <div class="vc-subtitle">按“模块 -> 学生 -> 讨论裁决”追踪课堂互动，学生数量按自定义画像动态展示。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    with kpi_col1:
        st.metric("参与学生数", len(student_names))
    with kpi_col2:
        st.metric("教学模块数", len(report.lesson_modules))
    with kpi_col3:
        discussion_points = sum(
            len(d.consensus) + len(d.disagreements) for d in report.module_deliberations
        )
        st.metric("讨论要点", discussion_points)


def _render_virtual_timeline(report: SimulationReport) -> None:
    if report.analysis_mode != "deep":
        return

    interactions_by_module = defaultdict(list)
    for item in report.module_interactions:
        interactions_by_module[item.module_id].append(item)

    deliberation_by_module = {d.module_id: d for d in report.module_deliberations}

    st.markdown("#### 课堂时间线")
    if not report.lesson_modules:
        st.info("未返回分模块记录。")
        return

    all_modules = sorted(report.lesson_modules, key=lambda m: m.order)
    module_options = [f"第{m.order}环节 · {m.title}" for m in all_modules]
    module_by_label = {f"第{m.order}环节 · {m.title}": m for m in all_modules}
    student_names = _collect_student_names(report)

    control_col1, control_col2 = st.columns(2)
    with control_col1:
        selected_students = st.multiselect(
            "筛选学生",
            options=student_names,
            default=student_names,
            key="timeline_student_filter",
        )
    with control_col2:
        selected_module_labels = st.multiselect(
            "筛选环节",
            options=module_options,
            default=module_options,
            key="timeline_module_filter",
        )

    filtered_modules = [module_by_label[label] for label in selected_module_labels if label in module_by_label]
    if not filtered_modules:
        st.info("请至少选择一个环节。")
        return
    st.caption("当前为静态课堂时间线视图：按筛选条件展示全部已生成环节。")

    modules_to_render = filtered_modules

    selected_student_set = set(selected_students)

    def teacher_guiding_questions(module: Any) -> list[str]:
        if module.key_points:
            return [f"这个知识点在什么条件下成立：{point}？" for point in module.key_points[:2]]
        return ["这一步和上一环节如何衔接？", "如果条件变化，结论会怎样变化？"]

    for module in modules_to_render:
        with st.expander(f"第 {module.order} 环节 · {module.title}", expanded=(module.order == 1)):
            st.markdown("<div class='vc-timeline-title'>教师讲解</div>", unsafe_allow_html=True)
            if module.key_points:
                st.markdown(
                    "".join([f"<span class='vc-chip'>{point}</span>" for point in module.key_points]),
                    unsafe_allow_html=True,
                )
            st.text_area(
                f"模块讲解_{module.module_id}",
                value=module.teacher_script,
                height=120,
                disabled=True,
                label_visibility="collapsed",
            )

            st.markdown("<div class='vc-timeline-title'>老师引导问题</div>", unsafe_allow_html=True)
            for question in teacher_guiding_questions(module):
                st.markdown(
                    f"""
                    <div class="vc-qa vc-qa-teacher">
                        <div class="vc-qa-who">🎙️ 教师引导</div>
                        <div class="vc-qa-text">{question}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown("<div class='vc-timeline-title'>学生提问与讨论</div>", unsafe_allow_html=True)
            module_items = [
                item
                for item in interactions_by_module.get(module.module_id, [])
                if not selected_student_set or item.profile_name in selected_student_set
            ]
            if not module_items:
                st.caption("该环节暂无学生互动记录。")
            for inter in module_items:
                question_preview = "；".join(inter.likely_questions[:2]) if inter.likely_questions else "暂无明确提问"
                response_preview = inter.verbal_response or "（无发言文本）"
                missed_preview = "；".join(inter.missed_key_points[:2]) if inter.missed_key_points else "无"
                st.markdown(
                    f"""
                    <div class="vc-qa vc-qa-student">
                        <div class="vc-qa-who">🙋 {inter.profile_name} · 参与度 {inter.engagement} · 置信度 {inter.confidence_score}</div>
                        <div class="vc-qa-text">听课状态: {inter.listening_state}</div>
                        <div class="vc-qa-text">分心原因: {inter.distraction_reason or '无'}</div>
                        <div class="vc-qa-text">漏听要点: {missed_preview}</div>
                        <div class="vc-qa-text">发言: {response_preview}</div>
                        <div class="vc-qa-text">提问: {question_preview}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            deliberation = deliberation_by_module.get(module.module_id)
            st.markdown("<div class='vc-timeline-title'>讨论裁决黑板 (学生、反方挑战者、教学观察员参与)</div>", unsafe_allow_html=True)
            if deliberation is None:
                st.caption("该环节暂无裁决记录。")
                continue

            board_col1, board_col2 = st.columns(2)
            with board_col1:
                st.markdown("<div class='vc-board'><b>共识（大家基本都同意的判断）</b><br/>" + "<br/>".join(deliberation.consensus or ["暂无"]) + "</div>", unsafe_allow_html=True)
                st.markdown(
                    "<div class='vc-board'><b>即时调整（老师当下就可以立刻改的做法）</b><br/>"
                    + "<br/>".join(deliberation.teaching_adjustments or ["暂无"])
                    + "</div>",
                    unsafe_allow_html=True,
                )
            with board_col2:
                st.markdown("<div class='vc-board'><b>分歧（大家意见不一致的地方）</b><br/>" + "<br/>".join(deliberation.disagreements or ["暂无"]) + "</div>", unsafe_allow_html=True)
                st.markdown(
                    "<div class='vc-board'><b>记忆更新（学生更新的知识点或信息）</b><br/>"
                    + "<br/>".join(deliberation.memory_updates or ["暂无"])
                    + "</div>",
                    unsafe_allow_html=True,
                )
    st.markdown("---")


def render_deep_simulation_trace(report: SimulationReport) -> None:
    if report.analysis_mode != "deep":
        return

    _mount_virtual_classroom_theme()
    _render_virtual_classroom_overview(report)

    with st.expander("整课讲稿（可折叠）", expanded=False):
        script_len = len((report.teacher_script or "").strip())
        st.markdown("**整课讲稿（模型返回或由分模块讲稿拼接）**")
        st.caption(f"当前文本长度: {script_len} 字。若偏短，通常表示模型返回的是摘要式总稿。")
        st.text_area(
            "整课讲稿",
            value=report.teacher_script or "（未生成）",
            height=280,
            disabled=True,
            label_visibility="collapsed",
        )

    _render_virtual_timeline(report)


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
    st.caption("关注程度说明：")
    st.markdown("- 高关注：该学生需要优先教学干预")
    st.markdown("- 中关注：该学生有明显风险，建议老师跟进")
    st.markdown("- 常规关注：该学生当前风险较低，常规照看即可")
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
                    st.caption(f"听课状态: {reaction.listening_state}")
                    st.markdown(
                        f"<div style='font-size:13px;font-weight:600;color:{attention_color};'>{attention_label}</div>",
                        unsafe_allow_html=True,
                    )
                with top_col2:
                    if reaction.distraction_reason:
                        st.markdown(f"**走神/注意力说明**：{reaction.distraction_reason}")
                    if reaction.missed_key_points:
                        st.markdown("**可能漏听的关键点**")
                        st.markdown("\n".join(f"- {item}" for item in reaction.missed_key_points[:4]))
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
    st.markdown("---")
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