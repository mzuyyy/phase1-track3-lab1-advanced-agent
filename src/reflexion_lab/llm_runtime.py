"""LLM Runtime — gọi NVIDIA NIM API thay cho mock.

Mỗi hàm trả về tuple (result, token_count, latency_ms):
  - actor_answer  → (answer_str, tokens, latency_ms)
  - evaluator     → (JudgeResult, tokens, latency_ms)
  - reflector     → (ReflectionEntry, tokens, latency_ms)
"""
from __future__ import annotations

import json
import os
import re
import time
from functools import cache
from typing import Final

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from .prompts import (
    ACTOR_REFLECTION_SECTION,
    ACTOR_SYSTEM,
    EVALUATOR_SYSTEM,
    REFLECTOR_SYSTEM,
)
from .schemas import JudgeResult, QAExample, ReflectionEntry

load_dotenv()

# ── NVIDIA NIM config ──────────────────────────────────────────────
NVIDIA_BASE_URL: Final = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
MODEL_ID: Final = os.getenv(
    "NVIDIA_MODEL_ID", "meta/llama-3.1-8b-instruct"
)
RATE_LIMIT_RETRIES: Final = 4
RATE_LIMIT_BACKOFF_SECONDS: Final = 10


@cache
def _create_client() -> OpenAI:
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set")
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)


# ── helpers ─────────────────────────────────────────────────────────
def _call_llm(system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
    """Gọi LLM, trả về (response_text, total_tokens, latency_ms)."""
    t0 = time.perf_counter()
    for retry in range(RATE_LIMIT_RETRIES):
        try:
            resp = _create_client().chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            break
        except RateLimitError:
            if retry == RATE_LIMIT_RETRIES - 1:
                raise
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (2**retry))
    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = resp.choices[0].message.content.strip()
    tokens = resp.usage.total_tokens if resp.usage else 0
    return text, tokens, latency_ms


def _extract_json(text: str) -> str:
    """Trích JSON từ response LLM (có thể bọc trong ```json ... ```)."""
    # Thử tìm JSON block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Thử tìm JSON object trần
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


# ── public API ──────────────────────────────────────────────────────
def actor_answer(
    example: QAExample,
    attempt_id: int,
    agent_type: str,
    reflection_memory: list[str],
) -> tuple[str, int, int]:
    """Actor: trả lời câu hỏi dựa trên context. Trả về (answer, tokens, latency_ms)."""
    # Build system prompt
    reflection_section = ""
    if reflection_memory:
        reflection_section = ACTOR_REFLECTION_SECTION.format(
            reflections="\n".join(f"- {s}" for s in reflection_memory)
        )
    system = ACTOR_SYSTEM.format(reflection_section=reflection_section)

    # Build user prompt with context
    ctx_block = "\n\n".join(
        f"[{c.title}]\n{c.text}" for c in example.context
    )
    user = f"Question: {example.question}\n\nContext:\n{ctx_block}\n\nAnswer:"

    text, tokens, latency = _call_llm(system, user)
    # Lấy dòng cuối cùng làm answer (ngắn gọn)
    answer = text.split("\n")[-1].strip().rstrip(".")
    return answer, tokens, latency


def evaluator(
    example: QAExample, answer: str
) -> tuple[JudgeResult, int, int]:
    """Evaluator: chấm điểm answer vs gold. Trả về (JudgeResult, tokens, latency_ms)."""
    system = EVALUATOR_SYSTEM
    user = (
        f"Gold answer: {example.gold_answer}\n"
        f"Predicted answer: {answer}\n\n"
        f"Evaluate the predicted answer. Return JSON."
    )

    text, tokens, latency = _call_llm(system, user)

    try:
        data = json.loads(_extract_json(text))
        judge = JudgeResult(
            score=int(data.get("score", 0)),
            reason=data.get("reason", ""),
            missing_evidence=data.get("missing_evidence", []),
            spurious_claims=data.get("spurious_claims", []),
        )
    except (json.JSONDecodeError, Exception):
        judge = JudgeResult(
            score=0,
            reason=f"Failed to parse evaluator output: {text[:200]}",
        )

    return judge, tokens, latency


def reflector(
    example: QAExample,
    attempt_id: int,
    judge: JudgeResult,
) -> tuple[ReflectionEntry, int, int]:
    """Reflector: phân tích lỗi, đề xuất chiến thuật mới. Trả về (ReflectionEntry, tokens, latency_ms)."""
    system = REFLECTOR_SYSTEM
    user = (
        f"Question: {example.question}\n"
        f"Attempt #{attempt_id} answer was WRONG.\n"
        f"Evaluator reason: {judge.reason}\n"
        f"Missing evidence: {judge.missing_evidence}\n"
        f"Spurious claims: {judge.spurious_claims}\n\n"
        f"Reflect and return JSON."
    )

    text, tokens, latency = _call_llm(system, user)

    try:
        data = json.loads(_extract_json(text))
        entry = ReflectionEntry(
            attempt_id=data.get("attempt_id", attempt_id),
            failure_reason=data.get("failure_reason", judge.reason),
            lesson=data.get("lesson", ""),
            next_strategy=data.get("next_strategy", ""),
        )
    except (json.JSONDecodeError, Exception):
        entry = ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson="Could not parse reflection output.",
            next_strategy="Retry with same approach.",
        )

    return entry, tokens, latency
