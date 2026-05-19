from __future__ import annotations

from ._builder import build_full_catalog

_HIST_PRIMARY_LOWER = {
    "low": {
        "strengths": ["喜欢听历史故事、神话传说", "能记住主要人物名字", "愿意看图说话", "课堂故事环节专注"],
        "weaknesses": ["时间先后混乱", "分不清故事与史实", "词汇量少影响表达", "不爱写字"],
        "likely_errors": ["把传说当历史", "朝代顺序错", "人物关系张冠李戴", "只看图画不读文字"],
        "support_needs": ["历史故事时间轴卡片", "人物关系图", "口头复述再简单记录", "图文对照阅读"],
    },
    "mid-low": {"strengths": ["能复述课文故事", "对地图有兴趣", "小组讨论"], "weaknesses": ["因果弱"], "likely_errors": ["混淆事件"], "support_needs": ["时间轴"]},
    "mid": {"strengths": ["课内达标", "能回答基础问题"], "weaknesses": ["概括弱"], "likely_errors": ["原因片面"], "support_needs": ["思维导图"]},
    "mid-high": {"strengths": ["阅读广", "表达好"], "weaknesses": ["深度"], "likely_errors": ["过度想象"], "support_needs": ["博物馆"]},
    "high": {"strengths": ["兴趣浓", "能讲述"], "weaknesses": ["规范"], "likely_errors": ["史料混淆"], "support_needs": ["拓展阅读"]},
}

_HIST_PRIMARY_UPPER = {
    "low": {
        "strengths": ["对中国古代史故事感兴趣", "能记住部分年代、人物", "愿意完成填空式作业", "课堂视频投入"],
        "weaknesses": ["史料意识弱", "论述题不会写", "中外史混", "时间空间定位差"],
        "likely_errors": ["把电视剧当史实", "朝代更替顺序错", "材料题只抄原文", "评价人物绝对化"],
        "support_needs": ["时间轴+疆域简图", "材料题“观点+依据”", "历史人物多角度评价表", "区分史实与文艺作品"],
    },
    "mid-low": {"strengths": ["基础记忆", "跟班"], "weaknesses": ["材料题"], "likely_errors": ["原因不全"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考主干"], "weaknesses": ["论述"], "likely_errors": ["观点空泛"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["压轴"], "likely_errors": ["时空"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["素养好"], "weaknesses": ["应试"], "likely_errors": ["过度"], "support_needs": ["史论"]},
}

_HIST_JUNIOR = {
    "low": {
        "strengths": ["对故事性内容感兴趣", "愿意背时间、人物", "课堂听讲", "作业完成"],
        "weaknesses": ["史料解读弱", "论述题不会分点", "中外通史线索乱", "开卷考试也不会找"],
        "likely_errors": ["材料题答非所问", "原因影响答不全", "史实错误", "观点绝对化无依据"],
        "support_needs": ["时空坐标训练", "材料题答题模板", "论述“观点+史实+小结”", "错题按类型归类"],
    },
    "mid-low": {"strengths": ["基础题"], "weaknesses": ["材料论述"], "likely_errors": ["时空"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考中等"], "weaknesses": ["综合"], "likely_errors": ["论述"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["压轴"], "likely_errors": ["比较"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["史论潜力"], "weaknesses": ["心态"], "likely_errors": ["偏激"], "support_needs": ["拓展"]},
}

_HIST_SENIOR = {
    "low": {
        "strengths": ["愿意背时间、事件", "对历史故事有兴趣", "跟课", "作业提交"],
        "weaknesses": ["通史线索乱", "论述题薄弱", "选修专题深度不够", "高考题量大焦虑"],
        "likely_errors": ["选择题史实错", "大题史论不分", "小论文不会论证", "时空定位错"],
        "support_needs": ["通史框架图", "论述模板", "选修知识清单", "选择排错训练"],
    },
    "mid-low": {"strengths": ["基础得分"], "weaknesses": ["论述"], "likely_errors": ["材料"], "support_needs": ["套卷"]},
    "mid": {"strengths": ["及格—良好"], "weaknesses": ["压轴"], "likely_errors": ["比较"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["75+潜力"], "weaknesses": ["波动"], "likely_errors": ["论述"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["史论素养"], "weaknesses": ["心态"], "likely_errors": ["偏激"], "support_needs": ["强基"]},
}

PROFILES_BY_BAND = build_full_catalog(
    _HIST_PRIMARY_LOWER,
    _HIST_PRIMARY_UPPER,
    _HIST_JUNIOR,
    _HIST_SENIOR,
    "历史",
)
