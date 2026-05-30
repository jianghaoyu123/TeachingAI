"""课程标准评估器模块 - 负责课程标准的加载和合规性评估"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import sys

# 导入LLM相关模块
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from teachingai_app.core.llm_api import invoke_llm
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


class CurriculumStandardEvaluator:
    """课程标准评估器，用于加载课程标准并评估教案合规性"""

    def __init__(self, subject: str, grade: str, region: str = "人教版"):
        self.subject = subject
        self.grade = grade
        self.region = region
        self._standards: dict[str, Any] | None = None
        self._load_standards()

    def _load_standards(self) -> None:
        """加载课程标准文件"""
        base_dir = Path(__file__).parent.parent / "data" / "curriculum_standards"
        subject_dir = base_dir / self.subject
        file_path = subject_dir / f"{self.grade}_{self.region}.json"

        if not file_path.exists():
            print(f"课程标准文件不存在: {file_path}")
            self._standards = None
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self._standards = json.load(f)
        except Exception as e:
            print(f"加载课程标准文件失败: {e}")
            self._standards = None

    def has_standards(self) -> bool:
        """检查课程标准是否已加载"""
        return self._standards is not None

    def get_standards_summary(self) -> str:
        """获取课程标准摘要，用于LLM提示"""
        if not self._standards:
            return ""

        meta = self._standards.get("meta", {})
        modules = self._standards.get("modules", [])

        summary_parts = [
            f"学科: {meta.get('subject', self.subject)}",
            f"年级: {meta.get('grade', self.grade)}",
            f"教材版本: {meta.get('region', self.region)}",
            f"课程模块数量: {len(modules)}",
        ]

        if modules:
            module_names = [m.get("module_name", "") for m in modules[:5]]
            summary_parts.append(f"主要模块: {', '.join(module_names)}")

        return "\n".join(summary_parts)

    def get_all_key_concepts(self) -> list[str]:
        """获取所有关键概念"""
        if not self._standards:
            return []

        concepts = []
        for module in self._standards.get("modules", []):
            concepts.extend(module.get("key_concepts", []))
        return concepts

    def get_module_names(self) -> list[str]:
        """获取所有模块名称"""
        if not self._standards:
            return []

        return [m.get("module_name", "") for m in self._standards.get("modules", [])]

    def evaluate_compliance(self, text: str, teacher_script: str = "", lesson_topic: str = "") -> dict[str, Any] | None:
        """评估教案内容与课程标准的合规性，返回None表示不支持课标评估"""
        if not self._standards:
            return None

        modules = self._standards.get("modules", [])
        
        # 根据课程主题筛选相关模块
        relevant_modules = self._find_relevant_modules(modules, text, teacher_script, lesson_topic)
        
        # 如果没有相关模块，返回None表示不支持课标评估
        if not relevant_modules:
            return None
        
        all_concepts: set[str] = set()
        all_skills: set[str] = set()

        for module in relevant_modules:
            for concept in module.get("key_concepts", []):
                all_concepts.add(concept.lower())
            for skill in module.get("required_skills", []):
                all_skills.add(skill.lower())

        text_lower = (text + " " + teacher_script + " " + lesson_topic).lower()

        mentioned_concepts = [c for c in all_concepts if c in text_lower]
        mentioned_skills = [s for s in all_skills if s in text_lower]

        coverage_score = len(mentioned_concepts) / max(len(all_concepts), 1) * 100 if all_concepts else 0

        missing = [c for c in all_concepts if c not in text_lower]
        excessive = [c for c in mentioned_concepts if c not in all_concepts]

        difficulty_level = self._standards.get("meta", {}).get("difficulty_level", "基础")

        return {
            "topic_coverage_score": round(coverage_score, 1),
            "mentioned_concepts": mentioned_concepts,
            "missing_topics": missing[:10],
            "excessive_topics": excessive[:5],
            "difficulty_match": difficulty_level,
            "difficulty_score": 80.0,
            "objective_achievement": [],
            "overall_compliance_score": round(coverage_score, 1),
            "recommendations": self._generate_recommendations(coverage_score, missing),
        }
    
    def _find_relevant_modules(self, modules: list[dict], text: str, teacher_script: str, lesson_topic: str) -> list[dict]:
        """根据课程主题和内容筛选相关模块，返回空列表表示不支持课标评估"""
        if not modules:
            return []
        
        combined_text = (text + " " + teacher_script + " " + lesson_topic).lower()
        relevant_modules = []
        
        # 1. 首先根据课程主题进行精确匹配
        topic_lower = lesson_topic.lower()
        for module in modules:
            module_name = module.get("module_name", "").lower()
            if self._match_topic(module_name, topic_lower):
                relevant_modules.append(module)
        
        # 2. 如果没有精确匹配，根据内容关键词匹配
        if not relevant_modules:
            for module in modules:
                module_name = module.get("module_name", "").lower()
                key_concepts = [c.lower() for c in module.get("key_concepts", [])]
                
                # 检查模块名是否出现在文本中
                if module_name in combined_text:
                    relevant_modules.append(module)
                    continue
                
                # 检查是否有多个关键概念出现在文本中
                concept_matches = 0
                for concept in key_concepts:
                    if concept in combined_text:
                        concept_matches += 1
                        if concept_matches >= 2:  # 至少匹配2个概念才认为相关
                            relevant_modules.append(module)
                            break
        
        # 3. 如果还是没有匹配到，让大模型决定最相关的模块（或决定不匹配）
        if not relevant_modules and HAS_LLM:
            relevant_modules = self._select_modules_with_llm(modules, text, teacher_script, lesson_topic)
        
        # 4. 如果最终没有匹配到任何模块，返回空列表表示不支持课标评估
        return relevant_modules
    
    def _select_modules_with_llm(self, modules: list[dict], text: str, teacher_script: str, lesson_topic: str) -> list[dict]:
        """使用大模型智能选择最相关的模块（需由外部提供LLM配置）"""
        # 如果没有LLM配置，直接返回空列表
        if not hasattr(self, '_llm_config') or not self._llm_config:
            return []
        
        try:
            # 构建模块信息列表
            module_list_text = []
            for i, module in enumerate(modules):
                module_name = module.get("module_name", "")
                key_concepts = module.get("key_concepts", [])
                module_list_text.append(f"{i+1}. {module_name}\n   主要概念: {', '.join(key_concepts)}")
            
            module_list_str = "\n".join(module_list_text)
            
            # 构建提示词
            system_prompt = "你是一位专业的课程标准匹配专家。请根据课程主题和内容，选择最相关的课程模块；如果确实没有相关的模块，可以返回0表示不匹配。"
            
            user_prompt = f"""课程主题: {lesson_topic}

课程内容摘要:
{text[:500]}...

可选课程模块:
{module_list_str}

请选择与课程主题和内容最相关的1-2个模块，仅返回模块序号（用逗号分隔），例如：1,2 或 3
如果确实没有相关的模块，请返回 0
"""
            
            # 使用外部提供的LLM配置调用
            try:
                config = self._llm_config
                result = invoke_llm(
                    provider=config.get('provider', 'openai'),
                    api_key=config.get('api_key', ''),
                    base_url=config.get('base_url', ''),
                    model=config.get('model', 'gpt-4o-mini'),
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    timeout_sec=30,
                )
            except Exception:
                # LLM调用失败，返回空列表让后续逻辑兜底
                return []
            
            # 解析LLM返回的结果
            selected_indices = []
            import re
            numbers = re.findall(r'\d+', result)
            
            # 检查是否返回 0（表示不匹配）
            if '0' in numbers:
                return []
            
            for num_str in numbers:
                try:
                    idx = int(num_str) - 1  # 转换为0-based索引
                    if 0 <= idx < len(modules):
                        selected_indices.append(idx)
                except ValueError:
                    continue
            
            # 去重并限制数量
            selected_indices = list(set(selected_indices))[:2]
            
            # 返回选中的模块
            return [modules[i] for i in selected_indices]
            
        except Exception:
            # 任何错误都返回空列表，让后续逻辑兜底
            return []
    
    def set_llm_config(self, provider: str, api_key: str, base_url: str, model: str) -> None:
        """设置LLM配置，用于智能选择模块"""
        self._llm_config = {
            'provider': provider,
            'api_key': api_key,
            'base_url': base_url,
            'model': model
        }
    
    def _match_topic(self, module_name: str, lesson_topic: str) -> bool:
        """检查课程主题与模块名是否匹配"""
        # 常用主题词映射
        topic_mappings = {
            "一元一次": ["一元一次"],
            "方程": ["方程"],
            "有理数": ["有理数"],
            "整式": ["整式"],
            "图形": ["图形"],
            "相交": ["相交", "平行线"],
            "数据": ["数据", "统计"],
            "概率": ["概率"],
        }
        
        for key, keywords in topic_mappings.items():
            if key in lesson_topic:
                for kw in keywords:
                    if kw in module_name:
                        return True
        
        # 直接包含匹配
        return module_name in lesson_topic or lesson_topic in module_name

    def _generate_recommendations(self, coverage_score: float, missing_topics: list[str]) -> list[str]:
        """生成改进建议"""
        recommendations = []

        if coverage_score < 60:
            recommendations.append("知识点覆盖不足，建议补充相关基础概念")
        elif coverage_score < 80:
            recommendations.append("知识点覆盖较好，但可进一步完善")
        else:
            recommendations.append("知识点覆盖较为完整")

        if missing_topics:
            top_missing = missing_topics[:3]
            recommendations.append(f"建议加强以下知识点的讲解: {', '.join(top_missing)}")

        return recommendations
