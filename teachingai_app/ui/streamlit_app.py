from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from teachingai_app.core.analysis_pipeline import analyze_deep_with_model_api, analyze_with_model_api
from teachingai_app.core.ingestion import ParseError, merge_text_sources, parse_file
from teachingai_app.core.llm_api import LLMApiError, PROVIDER_DEFAULTS
from teachingai_app.core.models import SimulationReport
from teachingai_app.core.pptx_revision import PptxRevisionError, build_revised_pptx_payload
from teachingai_app.ui.constants import (
    EXPORT_OPTIONS,
    GRADE_DISPLAY_LABELS,
    GRADE_OPTIONS,
    MODEL_DESCRIPTION_LABELS,
    MODEL_OPTIONS_BY_PROVIDER,
    SUBJECT_OPTIONS,
)
from teachingai_app.ui.profiles_sidebar import render_profile_editor
from teachingai_app.ui.render import render_simulation_results


def _ensure_api_settings() -> None:
    if "api_provider" not in st.session_state:
        st.session_state["api_provider"] = "deepseek"

    provider = str(st.session_state.get("api_provider", "deepseek"))
    if provider not in PROVIDER_DEFAULTS:
        provider = "deepseek"
        st.session_state["api_provider"] = provider

    defaults = PROVIDER_DEFAULTS[provider]
    if "api_key" not in st.session_state:
        st.session_state["api_key"] = ""
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = defaults["base_url"]
    if "api_model_choice" not in st.session_state:
        st.session_state["api_model_choice"] = defaults["model"]
    if "api_model_name" not in st.session_state:
        st.session_state["api_model_name"] = defaults["model"]
    if "api_provider_last" not in st.session_state:
        st.session_state["api_provider_last"] = provider

    # Backfill defaults when users clear fields manually.
    if not str(st.session_state.get("api_base_url", "")).strip():
        st.session_state["api_base_url"] = defaults["base_url"]
    if not str(st.session_state.get("api_model_name", "")).strip():
        st.session_state["api_model_name"] = defaults["model"]

    last_provider = str(st.session_state.get("api_provider_last", provider))
    if provider != last_provider:
        new_defaults = PROVIDER_DEFAULTS[provider]
        st.session_state["api_base_url"] = new_defaults["base_url"]
        st.session_state["api_model_choice"] = new_defaults["model"]
        st.session_state["api_model_name"] = new_defaults["model"]
        st.session_state["api_provider_last"] = provider


def _reset_api_settings_draft_from_saved() -> None:
    _ensure_api_settings()
    st.session_state["api_provider_draft"] = st.session_state["api_provider"]
    st.session_state["api_key_draft"] = st.session_state["api_key"]
    st.session_state["api_base_url_draft"] = st.session_state["api_base_url"]
    st.session_state["api_model_choice_draft"] = st.session_state["api_model_choice"]
    st.session_state["api_model_name_draft"] = st.session_state["api_model_name"]
    st.session_state["api_provider_draft_last"] = st.session_state["api_provider"]


@st.dialog("模型提供商与API设置", width="large")
def _render_api_settings_dialog() -> None:
    _ensure_api_settings()

    required_draft_keys = [
        "api_provider_draft",
        "api_key_draft",
        "api_base_url_draft",
        "api_model_choice_draft",
        "api_model_name_draft",
        "api_provider_draft_last",
    ]
    if any(key not in st.session_state for key in required_draft_keys):
        _reset_api_settings_draft_from_saved()

    provider_options = ["deepseek", "qwen", "glm", "openai", "gemini", "claude", "kimi", "minimax"]
    current_provider = str(st.session_state.get("api_provider_draft", "deepseek"))
    provider_index = provider_options.index(current_provider) if current_provider in provider_options else 0
    provider = st.selectbox("模型提供商", provider_options, index=provider_index, key="api_provider_draft")

    last_provider = str(st.session_state.get("api_provider_draft_last", provider))
    if provider != last_provider:
        defaults_on_switch = PROVIDER_DEFAULTS[provider]
        st.session_state["api_base_url_draft"] = defaults_on_switch["base_url"]
        st.session_state["api_model_choice_draft"] = defaults_on_switch["model"]
        st.session_state["api_model_name_draft"] = defaults_on_switch["model"]
        st.session_state["api_provider_draft_last"] = provider

    defaults = PROVIDER_DEFAULTS[provider]
    st.text_input("API Key", type="password", key="api_key_draft")
    st.text_input("Base URL", key="api_base_url_draft")

    model_options = MODEL_OPTIONS_BY_PROVIDER.get(provider, [defaults["model"], "自定义"])
    if "自定义" not in model_options:
        model_options = [*model_options, "自定义"]

    model_choice = str(st.session_state.get("api_model_choice_draft", defaults["model"]))
    if model_choice not in model_options:
        model_choice = defaults["model"] if defaults["model"] in model_options else "自定义"
        st.session_state["api_model_choice_draft"] = model_choice

    choice_index = model_options.index(model_choice)
    selected_choice = st.selectbox(
        "Model",
        model_options,
        index=choice_index,
        key="api_model_choice_draft",
        format_func=lambda m: MODEL_DESCRIPTION_LABELS.get(str(m), str(m)),
    )
    if selected_choice == "自定义":
        st.text_input("自定义 Model", key="api_model_name_draft")
    else:
        st.session_state["api_model_name_draft"] = selected_choice

    st.caption("支持 OpenAI / Gemini / Kimi / MiniMax 等兼容接口，以及 Claude 官方 API。请点击“保存设置”后生效。")

    save_col, close_col = st.columns(2)
    with save_col:
        if st.button("保存设置", key="save_api_settings", use_container_width=True):
            st.session_state["api_provider"] = str(st.session_state.get("api_provider_draft", "deepseek"))
            st.session_state["api_key"] = str(st.session_state.get("api_key_draft", ""))
            st.session_state["api_base_url"] = str(st.session_state.get("api_base_url_draft", ""))
            st.session_state["api_model_choice"] = str(
                st.session_state.get("api_model_choice_draft", PROVIDER_DEFAULTS[st.session_state["api_provider"]]["model"])
            )
            st.session_state["api_model_name"] = str(st.session_state.get("api_model_name_draft", ""))
            st.session_state["api_provider_last"] = st.session_state["api_provider"]
            st.success("API 设置已保存。")
            st.rerun()

    with close_col:
        if st.button("关闭窗口", key="close_api_settings", use_container_width=True):
            st.rerun()


def _mount_browser_watchdog() -> None:
    watchdog_url = os.environ.get("TEACHINGAI_BROWSER_WATCHDOG_URL", "").strip()
    if not watchdog_url:
        return
    components.html(
        f"""
        <script>
        (function() {{
            const heartbeatUrl = {watchdog_url!r};
            const sendHeartbeat = () => {{
                if (navigator.sendBeacon) {{
                    navigator.sendBeacon(heartbeatUrl + "?ts=" + Date.now());
                }} else {{
                    fetch(heartbeatUrl + "?ts=" + Date.now(), {{
                        method: "GET",
                        keepalive: true
                    }});
                }}
            }};
            sendHeartbeat();
            window.setInterval(sendHeartbeat, 15000);
            window.addEventListener("focus", sendHeartbeat);
            document.addEventListener("visibilitychange", () => {{
                if (!document.hidden) sendHeartbeat();
            }});
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _build_cached_revised_pptx_payload(report: SimulationReport) -> tuple[bytes, str, str] | None:
    source_name = st.session_state.get("latest_source_pptx_name")
    source_bytes = st.session_state.get("latest_source_pptx_bytes")
    if not isinstance(source_name, str) or not source_name.strip():
        return None
    if not isinstance(source_bytes, (bytes, bytearray)):
        return None
    try:
        return build_revised_pptx_payload(source_name, bytes(source_bytes), report)
    except PptxRevisionError as exc:
        st.warning(f"PPT修订版生成失败：{exc}")
        return None


def run_app() -> None:
    st.set_page_config(page_title="AI虚拟学生教学预演", page_icon="📘", layout="wide")
    _mount_browser_watchdog()
    _ensure_api_settings()

    st.title("AI虚拟学生教学预演系统")
    st.caption("版本 v1.1：支持快速模式与深度思考模式（多智能体分模块预演）。")
    st.caption("运行前需要先联网配置模型 API Key。")

    provider = str(st.session_state.get("api_provider", "deepseek"))
    api_key = str(st.session_state.get("api_key", "")).strip()
    base_url = str(st.session_state.get("api_base_url", "")).strip()
    model_choice = str(st.session_state.get("api_model_choice", ""))
    model_name = (
        str(st.session_state.get("api_model_name", "")).strip()
        if model_choice == "自定义"
        else model_choice
    )

    with st.sidebar:
        st.subheader("模型API设置")
        if st.button("打开API设置窗口", key="open_api_settings", use_container_width=True):
            _reset_api_settings_draft_from_saved()
            _render_api_settings_dialog()
        key_status = "已配置" if api_key else "未配置"
        st.caption(f"当前提供商：{provider} | 当前模型：{model_name or '未设置'} | API Key：{key_status}")
        if not api_key:
            st.warning("请先点击上方“打开API设置窗口”完成 API Key 配置。")
        st.markdown("---")

        st.subheader("输入设置")
        subject = st.selectbox("学科", SUBJECT_OPTIONS, index=0, key="subject_select")
        grade = st.selectbox(
            "年级",
            GRADE_OPTIONS,
            index=7,
            format_func=lambda g: str(GRADE_DISPLAY_LABELS.get(g, g)),
            key="grade_select",
        )
        st.markdown("---")
        render_profile_editor(subject, grade)
        st.markdown("---")
        enable_ocr = True
        st.info("当前版本仅支持在线模型 API 分析。")

    lesson_topic = st.text_input("课题", key="lesson_topic_input", value="一元一次方程")
    uploaded_files = st.file_uploader(
        "上传教案/逐字稿/PPT/PDF（可多选）",
        type=["txt", "md", "docx", "pptx", "pdf"],
        accept_multiple_files=True,
        key="lesson_files_uploader",
    )
    manual_text = st.text_area("或直接粘贴教案/逐字稿文本", height=180, key="manual_text_input")

    export_col1, export_col2 = st.columns(2)
    with export_col1:
        report_export_format = st.selectbox("学生反应报告格式", EXPORT_OPTIONS, index=2)
    with export_col2:
        revised_export_format = st.selectbox("修订后教案格式", EXPORT_OPTIONS, index=2)

    st.markdown("---")
    st.subheader("教案改进方向")
    improvement_focus_options = [
        ("all", "兼顾全体学生"),
        ("low", "基础薄弱型学生"),
        ("mid-low", "中等偏下型学生"),
        ("mid", "中等稳定型学生"),
        ("mid-high", "中等偏上型学生"),
        ("high", "拔高拓展型学生"),
    ]
    improvement_focus = st.selectbox(
        "教案优化侧重点",
        options=[opt[0] for opt in improvement_focus_options],
        format_func=lambda x: dict(improvement_focus_options).get(x, x),
        index=0,
        key="improvement_focus_select",
        help="选择教案改进的目标学生群体，系统会根据该层级学生的特点优化教案内容",
    )

    st.markdown("---")
    st.subheader("分析模式")
    analysis_mode = st.radio(
        "分析模式",
        options=["quick", "deep"],
        format_func=lambda m: "⚡ 快速模式 — 一次分析，速度较快"
        if m == "quick"
        else "🧠 深度思考模式 — 多轮讨论与裁决预演，更真实",
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="analysis_mode_radio",
    )
    if analysis_mode == "deep":
        st.info(
            "深度模式流程：教师智能体生成讲稿并分模块 → 第一轮学生反应（带跨模块记忆）"
            " → 第二轮讨论(反方挑战+教学观察员进行对抗式复核与课堂可行性把关） → 汇总报告。"
            "耗时与 API 调用次数显著高于快速模式。"
        )
    else:
        st.caption("快速模式适合备课初期快速摸底；如需分环节、分学生的细颗粒度反馈，可选用深度思考模式。")

    api_ready = bool(api_key and base_url and model_name)
    if not api_ready:
        st.warning("请先在侧边栏第一行点击“打开API设置窗口”，完成模型提供商与 API Key 配置。")

    latest_report = st.session_state.get("latest_simulation_report")
    run_clicked = st.button(
        "开始预演与优化",
        type="primary",
        use_container_width=True,
        disabled=not api_ready,
    )

    if not run_clicked:
        if api_ready:
            if isinstance(latest_report, SimulationReport):
                st.caption("显示最近一次推理结果。可修改参数后再次点击“开始预演与优化”更新。")
                mode_name = "深度思考模式" if latest_report.analysis_mode == "deep" else "快速模式"
                st.caption(
                    f"当前分析来源: 模型 API（{provider} / {model_name} / {mode_name}）"
                )
                cached_pptx_payload = _build_cached_revised_pptx_payload(latest_report)
                render_simulation_results(
                    latest_report,
                    report_export_format,
                    revised_export_format,
                    revised_pptx_payload=cached_pptx_payload,
                )
            else:
                st.info("请先上传教学材料或粘贴文本，然后点击「开始预演与优化」。")
        else:
            st.info("当前未完成 API 配置，按钮已禁用。")
        return

    text_chunks: list[str] = []
    pptx_sources: list[tuple[str, bytes]] = []
    if uploaded_files:
        for file in uploaded_files:
            file_bytes = file.getvalue()
            if file.name.lower().endswith(".pptx"):
                pptx_sources.append((file.name, file_bytes))
            try:
                parsed = parse_file(file.name, file_bytes, enable_ocr=enable_ocr)
                if parsed:
                    text_chunks.append(parsed)
            except ParseError as exc:
                st.warning(f"{file.name} 解析失败: {exc}")
    if manual_text.strip():
        text_chunks.append(manual_text)

    merged_text = merge_text_sources(text_chunks)
    if not merged_text.strip():
        st.error("未检测到可分析文本，请上传文件或粘贴内容。")
        return
    if not api_key.strip():
        st.error("请先在侧边栏第一行打开 API 设置窗口并填写 API Key。")
        return

    report: SimulationReport
    try:
        if analysis_mode == "deep":
            progress_bar = st.progress(0, text="深度思考模式启动…")
            status_placeholder = st.empty()

            def on_progress(message: str, current: int, total: int) -> None:
                ratio = current / total if total > 0 else 0.0
                progress_bar.progress(min(ratio, 1.0), text=message)
                status_placeholder.caption(f"步骤 {current}/{total}：{message}")

            report = analyze_deep_with_model_api(
                text=merged_text,
                subject=subject,
                lesson_topic=lesson_topic,
                grade=grade,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                progress_callback=on_progress,
                improvement_focus=improvement_focus,
            )
            progress_bar.progress(1.0, text="深度预演完成")
            status_placeholder.empty()
        else:
            with st.spinner("快速模式：正在模拟学生反应并生成优化建议..."):
                report = analyze_with_model_api(
                text=merged_text,
                subject=subject,
                lesson_topic=lesson_topic,
                grade=grade,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                improvement_focus=improvement_focus,
            )
    except LLMApiError as exc:
        st.error(f"模型调用失败: {exc}")
        return

    if len(pptx_sources) == 1:
        st.session_state["latest_source_pptx_name"] = pptx_sources[0][0]
        st.session_state["latest_source_pptx_bytes"] = pptx_sources[0][1]
    else:
        st.session_state.pop("latest_source_pptx_name", None)
        st.session_state.pop("latest_source_pptx_bytes", None)

    st.session_state["latest_simulation_report"] = report

    mode_name = "深度思考模式" if analysis_mode == "deep" else "快速模式"
    st.caption(f"当前分析来源: 模型 API（{provider} / {model_name} / {mode_name}）")
    current_pptx_payload = _build_cached_revised_pptx_payload(report)
    render_simulation_results(
        report,
        report_export_format,
        revised_export_format,
        revised_pptx_payload=current_pptx_payload,
    )
