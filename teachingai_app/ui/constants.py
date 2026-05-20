from __future__ import annotations

EXPORT_OPTIONS = ["Markdown", "HTML", "Word"]
PROFILE_LEVEL_OPTIONS = ["low", "mid-low", "mid", "mid-high", "high"]
PROFILE_LEVEL_LABELS = {
    "low": "基础薄弱",
    "mid-low": "中等偏下",
    "mid": "中等稳定",
    "mid-high": "中等偏上",
    "high": "拔高拓展",
}
PROFILE_LEVEL_FULL_LABELS = {
    "low": "基础薄弱型",
    "mid-low": "中等偏下型",
    "mid": "中等稳定型",
    "mid-high": "中等偏上型",
    "high": "拔高拓展型",
}

MODEL_OPTIONS_BY_PROVIDER = {
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash", "自定义"],
    "qwen": ["qwen-plus", "qwen-turbo", "qwen-max", "自定义"],
    "glm": ["glm-4-flash", "glm-4.7-flash", "glm-4-plus", "glm-4-air", "自定义"],
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "自定义"],
    "gemini": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "自定义"],
    "claude": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "自定义"],
    "kimi": [
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "kimi-k2-turbo-preview",
        "kimi-k2-0905-preview",
        "自定义",
    ],
    "minimax": [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
        "自定义",
    ],
}

MODEL_DESCRIPTION_LABELS = {
    "deepseek-v4-pro": "deepseek-v4-pro｜能力更强，适合复杂分析",
    "deepseek-v4-flash": "deepseek-v4-flash｜速度更快，成本更低",
    "qwen-plus": "qwen-plus｜综合均衡，常规任务推荐",
    "qwen-turbo": "qwen-turbo｜响应快，适合快速预演",
    "qwen-max": "qwen-max｜能力更强，复杂推理更稳",
    "glm-4-flash": "glm-4-flash｜速度优先，轻量任务友好",
    "glm-4.7-flash": "glm-4.7-flash｜免费额度大，能力更强",
    "glm-4-plus": "glm-4-plus｜能力更强，结果更稳定",
    "glm-4-air": "glm-4-air｜均衡模式，速度与效果兼顾",
    "gpt-4o-mini": "gpt-4o-mini｜经济快速，通用任务",
    "gpt-4.1-mini": "gpt-4.1-mini｜更强小模型，性价比高",
    "gpt-4.1": "gpt-4.1｜高能力模型，复杂任务推荐",
    "gemini-2.0-flash": "gemini-2.0-flash｜快速响应，低延迟",
    "gemini-2.5-flash": "gemini-2.5-flash｜速度与效果均衡",
    "gemini-2.5-pro": "gemini-2.5-pro｜能力更强，适合高难度任务",
    "claude-3-5-sonnet-latest": "claude-3-5-sonnet-latest｜高质量输出，推理稳健",
    "claude-3-5-haiku-latest": "claude-3-5-haiku-latest｜更快更省，适合轻量任务",
    "moonshot-v1-8k": "moonshot-v1-8k｜短上下文，速度快",
    "moonshot-v1-32k": "moonshot-v1-32k｜中长文本，综合均衡",
    "moonshot-v1-128k": "moonshot-v1-128k｜超长上下文，材料更长可选",
    "kimi-k2-turbo-preview": "kimi-k2-turbo-preview｜预览版，高速响应",
    "kimi-k2-0905-preview": "kimi-k2-0905-preview｜预览版，能力增强",
    "MiniMax-M2.7": "MiniMax-M2.7｜能力优先，复杂任务推荐",
    "MiniMax-M2.7-highspeed": "MiniMax-M2.7-highspeed｜高速版本，响应更快",
    "MiniMax-M2.5": "MiniMax-M2.5｜均衡模式",
    "MiniMax-M2.5-highspeed": "MiniMax-M2.5-highspeed｜均衡高速版",
    "MiniMax-M2.1": "MiniMax-M2.1｜轻量版本，成本更低",
    "自定义": "自定义｜手动输入模型名称",
}

GRADE_OPTIONS = [
    "一年级",
    "二年级",
    "三年级",
    "四年级",
    "五年级",
    "六年级",
    "七年级",  # 初一
    "八年级",  # 初二
    "九年级",  # 初三
    "高一",
    "高二",
    "高三",
]

GRADE_DISPLAY_LABELS = {
    "七年级": "初一（七年级）",
    "八年级": "初二（八年级）",
    "九年级": "初三（九年级）",
}

SUBJECT_OPTIONS = [
    "数学",
    "语文",
    "英语",
    "物理",
    "化学",
    "生物",
    "历史",
    "地理",
    "政治",
]
