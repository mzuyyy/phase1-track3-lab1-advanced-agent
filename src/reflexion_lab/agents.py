from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Protocol

from .schemas import (
    AttemptTrace,
    JudgeResult,
    QAExample,
    ReflectionEntry,
    RunRecord,
)


class AgentRuntime(Protocol):
    def actor_answer(
        self,
        example: QAExample,
        attempt_id: int,
        agent_type: str,
        reflection_memory: list[str],
    ) -> tuple[str, int, int]: ...

    def evaluator(
        self,
        example: QAExample,
        answer: str,
    ) -> tuple[JudgeResult, int, int]: ...

    def reflector(
        self,
        example: QAExample,
        attempt_id: int,
        judge: JudgeResult,
    ) -> tuple[ReflectionEntry, int, int]: ...

@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    runtime: AgentRuntime
    max_attempts: int = 1

    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        total_tokens = 0
        total_latency = 0
        final_answer = ""
        final_score = 0
        for attempt_id in range(1, self.max_attempts + 1):
            answer, act_tokens, act_latency = self.runtime.actor_answer(
                example,
                attempt_id,
                self.agent_type,
                reflection_memory,
            )
            judge, ev_tokens, ev_latency = self.runtime.evaluator(example, answer)
            tokens_this_attempt = act_tokens + ev_tokens
            latency_this_attempt = act_latency + ev_latency
            trace = AttemptTrace(attempt_id=attempt_id, answer=answer, score=judge.score, reason=judge.reason, token_estimate=tokens_this_attempt, latency_ms=latency_this_attempt)
            total_tokens += tokens_this_attempt
            total_latency += latency_this_attempt
            final_answer = answer
            final_score = judge.score
            if judge.score == 1:
                traces.append(trace)
                break

            # Reflexion: reflect on wrong answer so next attempt can improve
            if self.agent_type == "reflexion" and attempt_id < self.max_attempts:
                reflection, ref_tokens, ref_latency = self.runtime.reflector(
                    example,
                    attempt_id,
                    judge,
                )
                total_tokens += ref_tokens
                total_latency += ref_latency
                reflections.append(reflection)
                reflection_memory.append(reflection.next_strategy)
                trace.reflection = reflection
            traces.append(trace)
        failure_mode = "none" if final_score == 1 else "wrong_final_answer"
        return RunRecord(qid=example.qid, question=example.question, gold_answer=example.gold_answer, agent_type=self.agent_type, predicted_answer=final_answer, is_correct=bool(final_score), attempts=len(traces), token_estimate=total_tokens, latency_ms=total_latency, failure_mode=failure_mode, reflections=reflections, traces=traces)

class ReActAgent(BaseAgent):
    def __init__(self, runtime: AgentRuntime) -> None:
        super().__init__(agent_type="react", runtime=runtime, max_attempts=1)

class ReflexionAgent(BaseAgent):
    def __init__(self, runtime: AgentRuntime, max_attempts: int = 3) -> None:
        super().__init__(
            agent_type="reflexion",
            runtime=runtime,
            max_attempts=max_attempts,
        )
