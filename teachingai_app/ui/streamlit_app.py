from __future__ import annotations

import html
import os
import time

import streamlit as st
import streamlit.components.v1 as components

from teachingai_app.core.analysis_pipeline import analyze_deep_with_model_api, analyze_with_model_api
from teachingai_app.core.ingestion import ParseError, merge_text_sources, parse_file
from teachingai_app.core.llm_api import LLMApiError, LLMRateLimitError, PROVIDER_DEFAULTS, get_glm_api_key_from_env
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


def _mount_app_chrome_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.3rem;
        }
        .classroom-hero {
            border: 1px solid #E7DECE;
            border-radius: 16px;
            padding: 14px 16px;
            background:
                radial-gradient(1200px 260px at -5% 0%, rgba(53, 121, 91, 0.16), transparent 58%),
                radial-gradient(1000px 240px at 105% -20%, rgba(183, 114, 53, 0.16), transparent 60%),
                linear-gradient(180deg, #FCFBF6 0%, #F5F1E8 100%);
            margin-bottom: 12px;
        }
        .classroom-hero-title {
            font-size: 23px;
            font-weight: 800;
            color: #234033;
            line-height: 1.2;
            margin-bottom: 6px;
        }
        .classroom-hero-sub {
            font-size: 13px;
            color: #5F594E;
            margin-bottom: 8px;
        }
        .phase-chip {
            display: inline-block;
            border-radius: 999px;
            border: 1px solid #D9D2C2;
            background: #FFFCF4;
            color: #403A2F;
            font-size: 12px;
            padding: 2px 9px;
            margin-right: 6px;
            margin-bottom: 4px;
        }
        .section-note {
            border-left: 3px solid #A8BCA9;
            background: #F8F7F2;
            color: #544E44;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 13px;
            margin: 6px 0 12px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_classroom_hero(analysis_mode: str, latest_report: SimulationReport | None = None) -> None:
    mode_label = "深度讨论课" if analysis_mode == "deep" else "快速巡课"
    mode_tip = (
        "正在组织分模块讲解、分模块学生互动与分模块讨论裁决。"
        if analysis_mode == "deep"
        else "以最短路径完成课堂摸底，适合快速备课。"
    )
    module_count = 0
    if isinstance(latest_report, SimulationReport) and latest_report.analysis_mode == "deep":
        module_count = len(latest_report.lesson_modules)

    if analysis_mode == "deep":
        module_stage = f"阶段 2 分模块讲解（{module_count} 模块）" if module_count > 0 else "阶段 2 分模块讲解"
        phase_chips = [
            "阶段 1 输入材料",
            module_stage,
            "阶段 3 分模块学生反应",
            "阶段 4 分模块讨论裁决",
            "阶段 5 教案优化",
        ]
        subtitle = "深度模式会把课堂拆成多个教学模块，逐模块模拟“讲解-反应-裁决”全过程。"
    else:
        phase_chips = [
            "阶段 1 输入材料",
            "阶段 2 学生模拟",
            "阶段 3 教案优化",
        ]
        subtitle = "快速模式为单轮推演，不包含讨论裁决阶段。"

    chips_html = "".join(f"<span class='phase-chip'>{html.escape(chip)}</span>" for chip in phase_chips)
    st.markdown(
        f"""
        <div class="classroom-hero">
            <div class="classroom-hero-title">AI 虚拟课堂控制台</div>
            <div class="classroom-hero-sub">{html.escape(subtitle)}</div>
            {chips_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='section-note'>当前课堂模式: {html.escape(mode_label)} | {html.escape(mode_tip)}</div>",
        unsafe_allow_html=True,
    )


def _mount_live_panel_styles() -> None:
    st.markdown(
        """
        <style>
        .live-panel {
            border: 1px solid #E5DED0;
            border-radius: 14px;
            padding: 12px;
            background:
                radial-gradient(900px 180px at -10% 0%, rgba(51, 119, 88, 0.14), transparent 58%),
                radial-gradient(900px 220px at 110% 0%, rgba(181, 107, 39, 0.14), transparent 60%),
                linear-gradient(180deg, #FCFBF7 0%, #F7F3E9 100%);
            margin-bottom: 12px;
        }
        .live-head {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #214133;
            font-weight: 700;
            font-size: 16px;
            margin-bottom: 6px;
        }
        .live-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #2E8B57;
            box-shadow: 0 0 0 rgba(46, 139, 87, 0.5);
            animation: livePulse 1.2s infinite;
        }
        .live-dot.done {
            background: #1E7A3D;
            animation: none;
        }
        .live-meta {
            font-size: 13px;
            color: #5B564A;
        }
        .live-step {
            margin-top: 6px;
            border-radius: 10px;
            background: #FFFFFFD9;
            border: 1px solid #E8E3D8;
            padding: 8px 10px;
            font-size: 13px;
            color: #2F2A23;
        }
        .live-feed {
            border: 1px solid #E8E1D4;
            border-radius: 12px;
            background: #FFFEFB;
            padding: 8px 10px;
            max-height: 260px;
            overflow-y: auto;
        }
        .live-feed-title {
            font-size: 13px;
            color: #6B6457;
            margin-bottom: 6px;
        }
        .live-event {
            border-left: 3px solid #9FB8A9;
            padding-left: 8px;
            margin-bottom: 8px;
            animation: liveSlideIn 0.24s ease-out;
        }
        .live-event-time {
            font-size: 11px;
            color: #6E685C;
        }
        .live-event-msg {
            font-size: 13px;
            color: #2F2A23;
            font-weight: 600;
        }
        @keyframes livePulse {
            0% { box-shadow: 0 0 0 0 rgba(46, 139, 87, 0.45); }
            70% { box-shadow: 0 0 0 9px rgba(46, 139, 87, 0.00); }
            100% { box-shadow: 0 0 0 0 rgba(46, 139, 87, 0.00); }
        }
        @keyframes liveSlideIn {
            from { transform: translateY(4px); opacity: 0.2; }
            to { transform: translateY(0); opacity: 1; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_live_progress_panel(
    *,
    panel_placeholder: st.delta_generator.DeltaGenerator,
    events_placeholder: st.delta_generator.DeltaGenerator,
    current: int,
    total: int,
    message: str,
    events: list[dict[str, str]],
    running: bool,
) -> None:
    total_safe = max(1, total)
    ratio = min(max(current / total_safe, 0.0), 1.0)
    percent = int(ratio * 100)
    escaped_msg = html.escape(message)
    dot_class = "live-dot" if running else "live-dot done"
    status_text = "进行中" if running else "已完成"
    panel_placeholder.markdown(
        f"""
        <div class="live-panel">
            <div class="live-head"><span class="{dot_class}"></span>深度预演直播面板</div>
            <div class="live-meta">状态: {status_text} | 步骤 {current}/{total_safe} | 进度 {percent}%</div>
            <div class="live-step">当前事件: {escaped_msg}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not events:
        events_placeholder.info("等待第一条课堂事件...")
        return

    feed_items: list[str] = []
    for item in reversed(events):
        feed_items.append(
            "<div class='live-event'>"
            f"<div class='live-event-time'>{html.escape(item.get('time', ''))}</div>"
            f"<div class='live-event-msg'>{html.escape(item.get('message', ''))}</div>"
            "</div>"
        )
    events_placeholder.markdown(
        "<div class='live-feed-title'>课堂事件流（最新在上）</div>"
        + "<div class='live-feed'>"
        + "".join(feed_items)
        + "</div>",
        unsafe_allow_html=True,
    )


def _is_using_default_glm_mode() -> bool:
    env_key = get_glm_api_key_from_env()
    return bool(env_key)


FREE_GL_MODELS = {
    "glm-4-flash": "GLM-4-FLASH（快速）",
    "glm-4": "GLM-4（基础版）",
}

API_MODE_OPTIONS = [
    ("free_glm", "🎁 免费API模型"),
    ("custom", "🔑 用户个人API模型"),
]

PROVIDER_OPTIONS_FOR_CUSTOM = [
    ("deepseek", "DeepSeek"),
    ("qwen", "Qwen（阿里通义）"),
    ("glm", "GLM（智谱）"),
    ("openai", "OpenAI"),
    ("gemini", "Google Gemini"),
    ("claude", "Claude"),
    ("kimi", "Kimi（月之暗面）"),
    ("minimax", "MiniMax"),
]


def _ensure_api_settings() -> None:
    env_glm_key = get_glm_api_key_from_env()

    if "api_mode" not in st.session_state:
        st.session_state["api_mode"] = "free_glm"

    current_mode = str(st.session_state.get("api_mode", "custom"))

    if current_mode == "free_glm":
        st.session_state["api_base_url"] = PROVIDER_DEFAULTS["glm"]["base_url"]
        st.session_state["api_provider"] = "glm"
        if env_glm_key:
            st.session_state["api_key"] = env_glm_key
            st.session_state["api_model_choice"] = "glm-4-flash"
            st.session_state["api_model_name"] = "glm-4-flash"
        else:
            st.session_state["api_key"] = ""
            st.session_state["api_model_choice"] = "glm-4-flash"
            st.session_state["api_model_name"] = "glm-4-flash"
    else:
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


MAX_RATE_LIMIT_WAIT_SECONDS = 300
RATE_LIMIT_WAIT_INTERVAL = 5


def _call_with_rate_limit_retry(
    api_call_func,
    status_container: st.empty,
    *args,
    **kwargs,
):
    start_time = time.time()
    while True:
        try:
            return api_call_func(*args, **kwargs)
        except LLMRateLimitError:
            elapsed = time.time() - start_time
            remaining = MAX_RATE_LIMIT_WAIT_SECONDS - elapsed
            if remaining <= 0:
                status_container.error(
                    "⚠️ 等待超时（已等待5分钟），免费模型仍然不可用。\n\n"
                    "建议切换到「用户个人API模型」模式，使用您自己的 API Key 以获得更稳定的体验。"
                )
                raise LLMRateLimitError("Rate limit wait timeout")
            status_container.info(
                f"⏳ 当前免费模型访问人数过多，正在排队中...\n\n"
                f"预计还需等待: {int(remaining)} 秒\n\n"
                "您可以关闭此页面，稍后再试。"
            )
            time.sleep(RATE_LIMIT_WAIT_INTERVAL)


def run_app() -> None:
    st.set_page_config(page_title="AI虚拟学生教学预演", page_icon="📘", layout="wide")
    _mount_browser_watchdog()
    _mount_app_chrome_styles()
    _ensure_api_settings()

    st.title("AI虚拟学生教学预演系统")
    st.caption("版本 v1.2：支持快速模式与深度思考模式（多智能体分模块预演）。")

    env_glm_key = get_glm_api_key_from_env()
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
        st.subheader("🤖 模型API设置")

        api_mode = st.selectbox(
            "API模式",
            options=[opt[0] for opt in API_MODE_OPTIONS],
            format_func=lambda x: dict(API_MODE_OPTIONS).get(x, x),
            key="api_mode",
        )

        if api_mode == "free_glm":
            st.success("🎁 使用免费API模型（GLM系列）")
            free_model_options = [opt[0] for opt in FREE_GL_MODELS.items()]
            free_model_choice = st.selectbox(
                "选择免费模型",
                options=free_model_options,
                format_func=lambda x: FREE_GL_MODELS.get(x, x),
                key="free_api_model_choice",
            )
            if env_glm_key:
                st.session_state["api_model_choice"] = free_model_choice
                st.session_state["api_model_name"] = free_model_choice
            st.caption(f"当前模型：{FREE_GL_MODELS.get(free_model_choice, free_model_choice)}")
            if not env_glm_key:
                st.warning("⚠️ 未检测到 LLM_GLM_KEY 环境变量，可能因为软件为本地模式运行，免费模型暂时不可用。请切换到「用户个人API模型」模式。")
        else:
            st.info("🔑 使用用户个人API模型")
            provider_options = [opt[0] for opt in PROVIDER_OPTIONS_FOR_CUSTOM]

            current_provider = str(st.session_state.get("api_provider", "deepseek"))
            try:
                provider_index = provider_options.index(current_provider)
            except ValueError:
                provider_index = 0

            selected_provider = st.selectbox(
                "模型提供商 (先选我)",
                options=provider_options,
                format_func=lambda x: dict(PROVIDER_OPTIONS_FOR_CUSTOM).get(x, x),
                index=provider_index,
                key="api_provider",
            )

            defaults = PROVIDER_DEFAULTS[selected_provider]
            st.text_input("API Key", type="password", key="api_key", help="输入你的API Key")
            st.text_input("Base URL（手动选择模型提供商后自动填充）", key="api_base_url", help="API接口地址")

            model_options = MODEL_OPTIONS_BY_PROVIDER.get(selected_provider, [defaults["model"], "自定义"])
            if "自定义" not in model_options:
                model_options = [*model_options, "自定义"]

            current_model_choice = str(st.session_state.get("api_model_choice", defaults["model"]))
            if current_model_choice not in model_options:
                current_model_choice = defaults["model"] if defaults["model"] in model_options else "自定义"

            try:
                model_index = model_options.index(current_model_choice)
            except ValueError:
                model_index = 0

            selected_model = st.selectbox(
                "模型",
                options=model_options,
                index=model_index,
                key="api_model_choice",
                format_func=lambda m: MODEL_DESCRIPTION_LABELS.get(str(m), str(m)),
            )
            if selected_model == "自定义":
                st.text_input("自定义模型名称", key="api_model_name", help="填写模型的确切名称")
            else:
                st.session_state["api_model_name"] = selected_model

            st.caption("支持 OpenAI / Gemini / Kimi / MiniMax 等兼容接口，以及 Claude 官方 API。")

        st.markdown("---")
        enable_ocr = True
        st.info("当前版本仅支持在线模型 API 分析。")

    col1, col2 = st.columns(2)
    with col1:
        subject = st.selectbox("学科", SUBJECT_OPTIONS, index=0, key="subject_select")
    with col2:
        grade = st.selectbox(
            "年级",
            GRADE_OPTIONS,
            index=7,
            format_func=lambda g: str(GRADE_DISPLAY_LABELS.get(g, g)),
            key="grade_select",
        )

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
    st.subheader("待模拟学生设置")
    render_profile_editor(st.session_state.get("subject_select", ""), st.session_state.get("grade_select", ""))
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
        format_func=lambda m: (
            "⚡ 快速模式 — 一次分析，速度较快" if m == "quick"
            else "🧠 深度思考模式 — 多轮讨论与裁决预演，更真实"
        ),
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

    latest_report = st.session_state.get("latest_simulation_report")
    _render_classroom_hero(analysis_mode, latest_report if isinstance(latest_report, SimulationReport) else None)

    api_ready = bool(api_key and base_url and model_name)
    simulation_running = st.session_state.get("simulation_running", False)
    if not api_ready:
        st.warning('请先在侧边栏第一行点击"模型API设置"，完成模型提供商与 API Key 配置。')

    run_clicked = st.button(
        "开始预演与优化",
        type="primary",
        use_container_width=True,
        disabled=not api_ready or simulation_running,
    )

    # 如果正在模拟，直接继续执行
    if simulation_running and st.session_state.get("simulation_triggered", False):
        pass
    elif not run_clicked:
        st.session_state["simulation_running"] = False
        if api_ready:
            if isinstance(latest_report, SimulationReport):
                st.caption('显示最近一次推理结果。可修改参数后再次点击"开始预演与优化"更新。')
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

    if not st.session_state.get("simulation_triggered", False):
        # 第一次点击，先检查内容
        has_content = False
        if uploaded_files:
            has_content = True
        if manual_text.strip():
            has_content = True
        
        if not has_content:
            st.error("请先上传教案文件或粘贴教案文字，然后再开始模拟。")
            return
        
        st.session_state["simulation_running"] = True
        st.session_state["simulation_triggered"] = True
        st.rerun()
    
    st.session_state["simulation_triggered"] = False

    st.info("模拟已开始...")
    
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
        st.session_state["simulation_running"] = False
        st.error("未检测到可分析文本，请上传文件或粘贴内容。")
        return
    if not api_key.strip():
        st.session_state["simulation_running"] = False
        st.error("请先在侧边栏第一行打开 API 设置窗口并填写 API Key。")
        return

    report: SimulationReport
    rate_limit_status = st.empty()
    try:
        if analysis_mode == "deep":
            _mount_live_panel_styles()
            progress_bar = st.progress(0, text="深度思考模式启动…")
            panel_placeholder = st.empty()
            events_placeholder = st.empty()
            start_time = time.time()
            deep_events: list[dict[str, str]] = []

            _render_live_progress_panel(
                panel_placeholder=panel_placeholder,
                events_placeholder=events_placeholder,
                current=0,
                total=1,
                message="正在连接智能体并准备课堂场景...",
                events=deep_events,
                running=True,
            )

            def on_progress(message: str, current: int, total: int) -> None:
                ratio = current / total if total > 0 else 0.0
                progress_bar.progress(min(ratio, 1.0), text=message)
                now = time.strftime("%H:%M:%S")
                event = {"time": now, "message": f"步骤 {current}/{total} · {message}"}
                if not deep_events or deep_events[-1]["message"] != event["message"]:
                    deep_events.append(event)
                deep_events[:] = deep_events[-14:]
                _render_live_progress_panel(
                    panel_placeholder=panel_placeholder,
                    events_placeholder=events_placeholder,
                    current=current,
                    total=total,
                    message=message,
                    events=deep_events,
                    running=True,
                )

            report = _call_with_rate_limit_retry(
                analyze_deep_with_model_api,
                rate_limit_status,
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
            elapsed = max(1, int(time.time() - start_time))
            deep_events.append({"time": time.strftime("%H:%M:%S"), "message": f"深度预演完成，用时约 {elapsed} 秒"})
            deep_events[:] = deep_events[-14:]
            final_total = len(report.lesson_modules) * 2 + 2 if report.lesson_modules else 1
            _render_live_progress_panel(
                panel_placeholder=panel_placeholder,
                events_placeholder=events_placeholder,
                current=final_total,
                total=final_total,
                message="课堂回放与结果已就绪。",
                events=deep_events,
                running=False,
            )
        else:
            progress_bar = st.progress(0, text="快速模式：正在准备分析...")
            for step, desc in enumerate(
                [
                    "正在解析教学内容...",
                    "正在调用AI模型...",
                    "正在生成学生模拟反馈...",
                    "正在整理优化建议...",
                ],
                start=1,
            ):
                progress_bar.progress(step * 25, text=desc)
                time.sleep(0.3)
            rate_limit_status = st.empty()
            rate_limit_status.info("快速模式：正在模拟学生反应并生成优化建议...")
            report = _call_with_rate_limit_retry(
                analyze_with_model_api,
                rate_limit_status,
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
            progress_bar.progress(100, text="分析完成！")
            time.sleep(1)
            progress_bar.empty()
            rate_limit_status.empty()
    except LLMRateLimitError:
        st.session_state["simulation_running"] = False
        st.warning(
            "⚠️ 免费模型当前请求人数过多，已等待5分钟仍不可用。\n\n"
            "建议切换到「用户个人API模型」模式，使用您自己的 API Key 以获得更稳定的体验。"
        )
        return
    except LLMApiError as exc:
        st.session_state["simulation_running"] = False
        st.error(
            f"模型调用失败: {exc}\n\n"
            "如果问题持续存在，请点击左侧「API模式」切换到用户个人API模型，使用您自己的API Key。"
        )
        return

    if len(pptx_sources) == 1:
        st.session_state["latest_source_pptx_name"] = pptx_sources[0][0]
        st.session_state["latest_source_pptx_bytes"] = pptx_sources[0][1]
    else:
        st.session_state.pop("latest_source_pptx_name", None)
        st.session_state.pop("latest_source_pptx_bytes", None)

    st.session_state["latest_simulation_report"] = report
    st.session_state["simulation_running"] = False

    mode_name = "深度思考模式" if analysis_mode == "deep" else "快速模式"
    st.caption(f"当前分析来源: 模型 API（{provider} / {model_name} / {mode_name}）")
    current_pptx_payload = _build_cached_revised_pptx_payload(report)
    render_simulation_results(
        report,
        report_export_format,
        revised_export_format,
        revised_pptx_payload=current_pptx_payload,
    )
