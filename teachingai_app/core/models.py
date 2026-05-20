from dataclasses import dataclass, field
from typing import List


@dataclass
class StudentProfile:
    name: str
    level: str
    strengths: List[str]
    weaknesses: List[str]
    likely_errors: List[str]
    support_needs: List[str]


@dataclass
class StudentReaction:
    profile_name: str
    engagement: str
    confusion_points: List[str]
    likely_questions: List[str]
    error_predictions: List[str]
    listening_state: str = "基本跟随"
    distraction_reason: str = ""
    missed_key_points: List[str] = field(default_factory=list)


@dataclass
class DifficultyAssessment:
    overall_level: str
    cognitive_load_score: int
    step_complexity_score: int
    concept_span_score: int
    rationale: List[str]


@dataclass
class ConfidenceAssessment:
    overall_level: str
    overall_score: int
    rationale: List[str] = field(default_factory=list)
    profile_confidence: List[str] = field(default_factory=list)


@dataclass
class OptimizationSuggestion:
    priority: str
    issue: str
    suggestion: str
    expected_impact: str


@dataclass
class LessonModule:
    module_id: str
    title: str
    order: int
    teacher_script: str
    key_points: List[str] = field(default_factory=list)


@dataclass
class ModuleStudentInteraction:
    module_id: str
    module_title: str
    profile_name: str
    engagement: str
    verbal_response: str
    confusion_points: List[str] = field(default_factory=list)
    likely_questions: List[str] = field(default_factory=list)
    error_predictions: List[str] = field(default_factory=list)
    listening_state: str = "基本跟随"
    distraction_reason: str = ""
    missed_key_points: List[str] = field(default_factory=list)
    confidence_score: int = 60
    consistency_note: str = ""


@dataclass
class ModuleDeliberationRecord:
    module_id: str
    module_title: str
    consensus: List[str] = field(default_factory=list)
    disagreements: List[str] = field(default_factory=list)
    teaching_adjustments: List[str] = field(default_factory=list)
    memory_updates: List[str] = field(default_factory=list)


@dataclass
class ExamQuestion:
    question_id: str
    content: str
    question_type: str  # 选择题/填空题/解答题/判断题/其他
    points: float
    knowledge_tags: List[str] = field(default_factory=list)


@dataclass
class StudentQuestionAttempt:
    profile_name: str
    question_id: str
    predicted_correct: bool
    estimated_score: float
    predicted_answer: str
    error_type: str  # 无明显错误/概念错误/计算错误/审题失误/思路偏差/其他
    reasoning_note: str


@dataclass
class QuestionDiagnostic:
    question_id: str
    difficulty_label: str  # 易/中/难
    predicted_class_accuracy: float  # 0-1
    common_error_type: str
    teaching_note: str


@dataclass
class ExamReport:
    subject: str
    grade: str
    exam_topic: str
    original_exam_text: str = ""
    questions: List[ExamQuestion] = field(default_factory=list)
    student_attempts: List[StudentQuestionAttempt] = field(default_factory=list)
    question_diagnostics: List[QuestionDiagnostic] = field(default_factory=list)
    suggestions: List[OptimizationSuggestion] = field(default_factory=list)
    class_summary: str = ""


@dataclass
class SimulationReport:
    subject: str
    lesson_topic: str
    grade: str
    original_lesson_material: str = ""
    analysis_mode: str = "quick"
    extracted_key_points: List[str] = field(default_factory=list)
    reactions: List[StudentReaction] = field(default_factory=list)
    difficulty: DifficultyAssessment | None = None
    confidence: ConfidenceAssessment | None = None
    suggestions: List[OptimizationSuggestion] = field(default_factory=list)
    lesson_plan_change_summary: List[str] = field(default_factory=list)
    revised_lesson_plan: str = ""
    teacher_script: str = ""
    lesson_modules: List[LessonModule] = field(default_factory=list)
    module_interactions: List[ModuleStudentInteraction] = field(default_factory=list)
    module_deliberations: List[ModuleDeliberationRecord] = field(default_factory=list)
