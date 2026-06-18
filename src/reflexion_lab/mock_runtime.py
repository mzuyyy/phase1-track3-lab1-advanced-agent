from __future__ import annotations
from .schemas import QAExample, JudgeResult, ReflectionEntry
from .utils import normalize_answer

FIRST_ATTEMPT_WRONG = {"hp2": "London", "hp4": "Atlantic Ocean", "hp6": "Red Sea", "hp8": "Andes"}
FAILURE_MODE_BY_QID = {"hp2": "incomplete_multi_hop", "hp4": "wrong_final_answer", "hp6": "entity_drift", "hp8": "entity_drift"}

def actor_answer(
    example: QAExample,
    attempt_id: int,
    agent_type: str,
    reflection_memory: list[str],
) -> tuple[str, int, int]:
    if example.qid not in FIRST_ATTEMPT_WRONG:
        return example.gold_answer, 0, 0
    if agent_type == "react":
        return FIRST_ATTEMPT_WRONG[example.qid], 0, 0
    if attempt_id == 1 and not reflection_memory:
        return FIRST_ATTEMPT_WRONG[example.qid], 0, 0
    return example.gold_answer, 0, 0

def evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, int, int]:
    if normalize_answer(example.gold_answer) == normalize_answer(answer):
        result = JudgeResult(
            score=1,
            reason="Final answer matches the gold answer after normalization.",
        )
        return result, 0, 0
    if normalize_answer(answer) == "london":
        result = JudgeResult(
            score=0,
            reason="The answer stopped before completing the second hop.",
            missing_evidence=["Need to identify the river that flows through London."],
        )
        return result, 0, 0
    result = JudgeResult(
        score=0,
        reason="The final answer selected the wrong second-hop entity.",
        missing_evidence=["Need to ground the answer in the second paragraph."],
        spurious_claims=[answer],
    )
    return result, 0, 0

def reflector(
    example: QAExample,
    attempt_id: int,
    judge: JudgeResult,
) -> tuple[ReflectionEntry, int, int]:
    strategy = "Do the second hop explicitly: birthplace city -> river through that city." if example.qid == "hp2" else "Verify the final entity against the second paragraph before answering."
    result = ReflectionEntry(
        attempt_id=attempt_id,
        failure_reason=judge.reason,
        lesson="A partial first-hop answer is not enough; complete all hops.",
        next_strategy=strategy,
    )
    return result, 0, 0
