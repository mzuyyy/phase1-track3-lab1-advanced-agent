from __future__ import annotations
from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field

class ContextChunk(BaseModel):
    title: str
    text: str

class QAExample(BaseModel):
    qid: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    gold_answer: str
    context: list[ContextChunk]

class JudgeResult(BaseModel):
    """Kết quả đánh giá từ Evaluator — chấm điểm câu trả lời."""
    score: int = Field(ge=0, le=1, description="1 nếu đúng, 0 nếu sai")
    reason: str = Field(description="Giải thích ngắn gọn lý do chấm điểm")
    missing_evidence: list[str] = Field(default_factory=list, description="Thông tin còn thiếu để trả lời đúng")
    spurious_claims: list[str] = Field(default_factory=list, description="Khẳng định sai hoặc không dựa trên context")

class ReflectionEntry(BaseModel):
    """Một mục reflection — phân tích lỗi và đề xuất chiến thuật mới."""
    attempt_id: int = Field(description="Lần thử thứ mấy")
    failure_reason: str = Field(description="Lý do lần thử này thất bại")
    lesson: str = Field(description="Bài học rút ra từ lỗi")
    next_strategy: str = Field(description="Chiến thuật cụ thể để áp dụng ở lần thử tiếp theo")

class AttemptTrace(BaseModel):
    attempt_id: int
    answer: str
    score: int
    reason: str
    reflection: Optional[ReflectionEntry] = None
    token_estimate: int = 0
    latency_ms: int = 0

class RunRecord(BaseModel):
    qid: str
    question: str
    gold_answer: str
    agent_type: Literal["react", "reflexion"]
    predicted_answer: str
    is_correct: bool
    attempts: int
    token_estimate: int
    latency_ms: int
    failure_mode: Literal["none", "entity_drift", "incomplete_multi_hop", "wrong_final_answer", "looping", "reflection_overfit"]
    reflections: list[ReflectionEntry] = Field(default_factory=list)
    traces: list[AttemptTrace] = Field(default_factory=list)

class ReportPayload(BaseModel):
    meta: dict
    summary: dict
    failure_modes: dict
    examples: list[dict]
    extensions: list[str]
    discussion: str

class ReflexionState(TypedDict):
    question: str
    context: list[str]
    trajectory: list[str]
    reflection_memory: list[str]
    attempt_count: int
    success: bool
    final_answer: str
