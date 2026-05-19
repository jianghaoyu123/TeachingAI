from __future__ import annotations

from ._builder import build_full_catalog

_BIO_PRIMARY_LOWER = {
    "low": {
        "strengths": ["对动植物、人体外形好奇", "愿意观察、绘画", "能说出常见生物名称", "课堂自然课参与"],
        "weaknesses": ["生命科学词汇少", "结构—功能关系不懂", "注意力短", "怕血腥或敏感话题"],
        "likely_errors": ["混淆植物动物细胞", "把习惯当生理（‘吃饭才消化’说不清机制）", "实验记录乱", "结论跳跃"],
        "support_needs": ["图片、模型、视频", "观察记录表", "生活联系（健康习惯）", "敏感内容适度处理"],
    },
    "mid-low": {"strengths": ["能完成观察任务", "小组合作", "科普兴趣"], "weaknesses": ["抽象概念弱"], "likely_errors": ["分类标准混乱"], "support_needs": ["分类游戏"]},
    "mid": {"strengths": ["科学课稳定", "能归纳"], "weaknesses": ["系统概念少"], "likely_errors": ["生态关系混淆"], "support_needs": ["思维导图"]},
    "mid-high": {"strengths": ["观察细", "提问"], "weaknesses": ["书写"], "likely_errors": ["过度概括"], "support_needs": ["探究"]},
    "high": {"strengths": ["探究热情"], "weaknesses": ["耐心"], "likely_errors": ["设计不严"], "support_needs": ["项目"]},
}

_BIO_PRIMARY_UPPER = {
    "low": {
        "strengths": ["对显微镜、解剖模型好奇", "愿意背术语", "实验课参与", "生活健康话题感兴趣"],
        "weaknesses": ["细胞结构、遗传概念抽象", "图表（曲线、遗传图解）弱", "综合题弱", "术语记忆困难"],
        "likely_errors": ["光合呼吸混淆", "遗传图解符号错", "生态系统成分分不清", "实验对照组找错"],
        "support_needs": ["模型+口诀", "遗传图解分步练", "图表阅读专项", "实验设计模板"],
    },
    "mid-low": {"strengths": ["基础题", "实验操作", "跟班"], "weaknesses": ["遗传计算"], "likely_errors": ["基因型表现型"], "support_needs": ["专题"]},
    "mid": {"strengths": ["课标中等"], "weaknesses": ["综合"], "likely_errors": ["生态分析"], "support_needs": ["中考真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["压轴"], "likely_errors": ["实验"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["竞赛潜力"], "weaknesses": ["应试"], "likely_errors": ["粗心"], "support_needs": ["培优"]},
}

_BIO_JUNIOR = {
    "low": {
        "strengths": ["实验课愿意动手", "对人体、环境话题感兴趣", "基础记忆经反复可改善", "课堂参与"],
        "weaknesses": ["遗传、生态、生理综合弱", "图表分析差", "专业术语混", "中考复习量大时焦虑"],
        "likely_errors": ["遗传概率计算错", "食物链营养级错", "实验变量控制错", "识图题细胞结构标错"],
        "support_needs": ["遗传图解模板", "生态案例图", "实验探究句式", "术语分类记忆"],
    },
    "mid-low": {"strengths": ["基础可对", "实验", "跟班"], "weaknesses": ["综合"], "likely_errors": ["进化", "免疫"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考中等"], "weaknesses": ["压轴"], "likely_errors": ["综合"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上"], "weaknesses": ["时间"], "likely_errors": ["实验"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["竞赛"], "weaknesses": ["心态"], "likely_errors": ["跳步"], "support_needs": ["培优"]},
}

_BIO_SENIOR = {
    "low": {
        "strengths": ["愿意背知识点", "实验观察", "跟课", "对医学、环保话题好奇"],
        "weaknesses": ["遗传、调节、生态全面难", "长题干阅读弱", "高考实验设计空白", "选科信心不足"],
        "likely_errors": ["遗传系谱分析错", "光合呼吸曲线", "内环境稳态概念混", "实验题不会变量"],
        "support_needs": ["必修核心清单", "实验得分点", "遗传专题", "选填保分"],
    },
    "mid-low": {"strengths": ["基础得分"], "weaknesses": ["遗传生态"], "likely_errors": ["大题"], "support_needs": ["套卷"]},
    "mid": {"strengths": ["及格—良好"], "weaknesses": ["压轴"], "likely_errors": ["实验"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["80+潜力"], "weaknesses": ["波动"], "likely_errors": ["计算"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["竞赛强基"], "weaknesses": ["平衡"], "likely_errors": ["创新"], "support_needs": ["科研启蒙"]},
}

PROFILES_BY_BAND = build_full_catalog(
    _BIO_PRIMARY_LOWER,
    _BIO_PRIMARY_UPPER,
    _BIO_JUNIOR,
    _BIO_SENIOR,
    "生物",
)
