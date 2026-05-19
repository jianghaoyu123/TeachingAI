from __future__ import annotations

from ._builder import build_full_catalog

_POL_PRIMARY_LOWER = {
    "low": {
        "strengths": ["对班级规则、礼貌、合作话题有感受", "愿意参与情景表演", "能说出对错", "课堂活动积极"],
        "weaknesses": ["抽象道德概念弱", "说不清理由", "注意力短", "怕批评"],
        "likely_errors": ["绝对化判断（好人坏人）", "把个人喜好当标准", "复述口号无理解", "情境判断片面"],
        "support_needs": ["生活情境讨论", "角色扮演", "图文故事", "正向反馈"],
    },
    "mid-low": {"strengths": ["能跟读课文", "小组合作"], "weaknesses": ["说理弱"], "likely_errors": ["混淆概念"], "support_needs": ["案例讨论"]},
    "mid": {"strengths": ["课内达标"], "weaknesses": ["深度"], "likely_errors": ["片面"], "support_needs": ["思维导图"]},
    "mid-high": {"strengths": ["表达好"], "weaknesses": ["规范"], "likely_errors": ["绝对"], "support_needs": ["辩论启蒙"]},
    "high": {"strengths": ["参与积极"], "weaknesses": ["耐心"], "likely_errors": ["偏激"], "support_needs": ["项目"]},
}

_POL_PRIMARY_UPPER = {
    "low": {
        "strengths": ["对法律、权利、网络、环保话题有感受", "愿意参与课堂讨论", "能背诵部分观点", "生活经验丰富"],
        "weaknesses": ["理论联系实际弱", "辨析题不会分析", "开放性题目空泛", "书面表达弱"],
        "likely_errors": ["只背结论不说理由", "案例与知识点对不上", "评价绝对化", "材料题抄原文"],
        "support_needs": ["案例—知识点配对", "辨析题“正确/错误+理由”", "观点分点", "时事小评论"],
    },
    "mid-low": {"strengths": ["基础记忆"], "weaknesses": ["分析"], "likely_errors": ["混淆"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考中等"], "weaknesses": ["论述"], "likely_errors": ["空泛"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["压轴"], "likely_errors": ["偏激"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["表达强"], "weaknesses": ["应试"], "likely_errors": ["过度"], "support_needs": ["辩论"]},
}

_POL_JUNIOR = {
    "low": {
        "strengths": ["对时事、法律、道德话题感兴趣", "愿意背知识点", "课堂讨论参与", "作业完成"],
        "weaknesses": ["理论深度弱", "材料分析题不会", "论述题分点差", "开卷找知识点慢"],
        "likely_errors": ["选择题概念混淆", "辨析题理由不充分", "材料题答非所问", "探究题空泛无措施"],
        "support_needs": ["核心概念对比表", "材料题“知识+材料”", "论述分点模板", "时事与课本联系"],
    },
    "mid-low": {"strengths": ["基础题"], "weaknesses": ["材料"], "likely_errors": ["辨析"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考中等"], "weaknesses": ["综合"], "likely_errors": ["论述"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["开放"], "likely_errors": ["偏激"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["辩论潜力"], "weaknesses": ["心态"], "likely_errors": ["绝对"], "support_needs": ["拓展"]},
}

_POL_SENIOR = {
    "low": {
        "strengths": ["愿意背知识点", "对时事有兴趣", "跟课", "作业提交"],
        "weaknesses": ["哲学、经济学、政治理论抽象", "材料论述弱", "选修模块深", "高考时间紧"],
        "likely_errors": ["选择题概念错", "大题知识罗列无分析", "哲学原理用错", "时政术语不准"],
        "support_needs": ["核心概念图", "材料题模板", "时政热点清单", "选择保分"],
    },
    "mid-low": {"strengths": ["基础得分"], "weaknesses": ["论述"], "likely_errors": ["材料"], "support_needs": ["套卷"]},
    "mid": {"strengths": ["及格—良好"], "weaknesses": ["压轴"], "likely_errors": ["哲学"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["75+潜力"], "weaknesses": ["开放"], "likely_errors": ["偏激"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["政治素养"], "weaknesses": ["心态"], "likely_errors": ["绝对"], "support_needs": ["强基"]},
}

PROFILES_BY_BAND = build_full_catalog(
    _POL_PRIMARY_LOWER,
    _POL_PRIMARY_UPPER,
    _POL_JUNIOR,
    _POL_SENIOR,
    "政治",
)
