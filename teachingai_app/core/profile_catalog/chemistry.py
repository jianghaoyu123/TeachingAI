from __future__ import annotations

from ._builder import build_full_catalog

_CHEM_PRIMARY_LOWER = {
    "low": {
        "strengths": ["对颜色变化、气泡等实验现象好奇", "愿意安全参与演示实验", "能描述‘变了吗’", "喜欢动手"],
        "weaknesses": ["无系统化学概念", "分不清物理变化与化学变化", "词汇量少", "记录能力弱"],
        "likely_errors": ["认为所有变化都是化学变化", "混淆溶解与反应", "实验安全规则记不住", "结论与现象不符"],
        "support_needs": ["生活化学现象观察", "安全规则图示", "现象描述句式", "对比实验（对照）"],
    },
    "mid-low": {
        "strengths": ["科学课实验参与", "能跟读元素名称", "小组合作", "对生活中的化学好奇"],
        "weaknesses": ["符号、式子陌生", "微观想象弱"],
        "likely_errors": ["化学式书写错误", "实验步骤遗漏"],
        "support_needs": ["分子模型教具", "实验报告模板"],
    },
    "mid": {"strengths": ["科学探究任务完成", "能归纳简单规律", "测量较认真", "科普阅读"], "weaknesses": ["抽象符号多时不适应"], "likely_errors": ["混淆混合物纯净物"], "support_needs": ["宏观—微观类比"]},
    "mid-high": {"strengths": ["观察细", "提问多", "实验规范"], "weaknesses": ["书写解释简略"], "likely_errors": ["结论过度推广"], "support_needs": ["小课题"]},
    "high": {"strengths": ["探究热情高", "逻辑初成", "表达清"], "weaknesses": ["耐心不足"], "likely_errors": ["变量控制不严"], "support_needs": ["科技活动"]},
}

_CHEM_PRIMARY_UPPER = {
    "low": {
        "strengths": ["对实验现象有兴趣", "愿意背诵部分知识点", "课堂跟做实验", "作业完成"],
        "weaknesses": ["化学用语（式子、方程式）困难", "微观粒子想象弱", "计算（相对质量、浓度）弱", "概念多而混"],
        "likely_errors": ["化学方程式不配平", "化合价判断错", "实验操作顺序错", "鉴别题选试剂乱选"],
        "support_needs": ["化学用语每日练", "分子原子模型", "实验步骤流程图", "概念对比表"],
    },
    "mid-low": {
        "strengths": ["课内基础能对", "实验操作中等", "愿意问", "订正"],
        "weaknesses": ["推断题、计算题弱", "金属、酸碱盐综合差"],
        "likely_errors": ["CO2性质与制法混淆", "酸碱中和计算错", "过滤操作不规范"],
        "support_needs": ["专题突破", "中考真题"],
    },
    "mid": {"strengths": ["主干知识中等", "实验较稳", "跟班复习"], "weaknesses": ["综合推断难"], "likely_errors": ["图像分析题"], "support_needs": ["中档保分"]},
    "mid-high": {"strengths": ["理解快", "实验设计好", "成绩中上"], "weaknesses": ["粗心"], "likely_errors": ["计算失误"], "support_needs": ["压轴"]},
    "high": {"strengths": ["竞赛潜力", "探究强"], "weaknesses": ["应试"], "likely_errors": ["跳步"], "support_needs": ["培优"]},
}

_CHEM_JUNIOR = {
    "low": {
        "strengths": ["实验课参与", "基础记忆经反复可改善", "对化学有兴趣点", "课堂纪律"],
        "weaknesses": ["化学方程式、计算全面弱", "微观—宏观联系断裂", "推断题无从入手", "中考焦虑"],
        "likely_errors": ["方程式条件、配平、箭头错误", "质量守恒不会用", "实验探究题不会分析数据", "酸碱盐转化关系混乱"],
        "support_needs": ["方程式分类打卡", "实验探究模板", "推断题突破口训练", "计算题规范步骤"],
    },
    "mid-low": {"strengths": ["基础题可对", "实验操作", "跟班"], "weaknesses": ["综合弱"], "likely_errors": ["金属活动性顺序错", "溶解度曲线"], "support_needs": ["专题"]},
    "mid": {"strengths": ["中考中等稳定", "知识体系"], "weaknesses": ["压轴"], "likely_errors": ["综合计算"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["中上", "实验好"], "weaknesses": ["时间"], "likely_errors": ["推断"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["竞赛潜力"], "weaknesses": ["心态"], "likely_errors": ["粗心"], "support_needs": ["培优"]},
}

_CHEM_SENIOR = {
    "low": {
        "strengths": ["愿意背方程式、知识点", "实验课观察", "跟课", "作业提交"],
        "weaknesses": ["有机、反应原理、平衡全面难", "计算（物质的量）弱", "高考综合题空白多", "选科后信心不足"],
        "likely_errors": ["有机推断官能团错", "氧化还原配平错", "实验题数据处理错", "电化学综合不会"],
        "support_needs": ["必修核心+有机基础", "物质的量计算专项", "实验得分点", "选填保分策略"],
    },
    "mid-low": {"strengths": ["基础题得分", "跟班"], "weaknesses": ["有机、原理"], "likely_errors": ["平衡移动", "大题"], "support_needs": ["专题套卷"]},
    "mid": {"strengths": ["及格—良好"], "weaknesses": ["压轴"], "likely_errors": ["有机合成"], "support_needs": ["真题"]},
    "mid-high": {"strengths": ["80+潜力"], "weaknesses": ["波动"], "likely_errors": ["计算"], "support_needs": ["冲刺"]},
    "high": {"strengths": ["竞赛强基"], "weaknesses": ["平衡"], "likely_errors": ["创新"], "support_needs": ["大学先修"]},
}

PROFILES_BY_BAND = build_full_catalog(
    _CHEM_PRIMARY_LOWER,
    _CHEM_PRIMARY_UPPER,
    _CHEM_JUNIOR,
    _CHEM_SENIOR,
    "化学",
)
