from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from .schemas import ReportPayload, RunRecord


def summarize(
    records: list[RunRecord],
    running_time_seconds: dict[str, float],
    usd_per_million_tokens: float,
) -> dict:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.agent_type].append(record)
    summary: dict[str, dict] = {}
    for agent_type, rows in grouped.items():
        total_tokens = sum(row.token_estimate for row in rows)
        summary[agent_type] = {
            "count": len(rows),
            "em": round(mean(1.0 if r.is_correct else 0.0 for r in rows), 4),
            "avg_attempts": round(mean(r.attempts for r in rows), 4),
            "avg_token_estimate": round(mean(r.token_estimate for r in rows), 2),
            "avg_latency_ms": round(mean(r.latency_ms for r in rows), 2),
            "total_tokens": total_tokens,
            "running_time_seconds": round(
                running_time_seconds.get(agent_type, 0.0),
                3,
            ),
            "estimated_cost_usd": round(
                total_tokens * usd_per_million_tokens / 1_000_000,
                6,
            ),
        }
    if "react" in summary and "reflexion" in summary:
        summary["delta_reflexion_minus_react"] = {"em_abs": round(summary["reflexion"]["em"] - summary["react"]["em"], 4), "attempts_abs": round(summary["reflexion"]["avg_attempts"] - summary["react"]["avg_attempts"], 4), "tokens_abs": round(summary["reflexion"]["avg_token_estimate"] - summary["react"]["avg_token_estimate"], 2), "latency_abs": round(summary["reflexion"]["avg_latency_ms"] - summary["react"]["avg_latency_ms"], 2)}
    return summary

def failure_breakdown(records: list[RunRecord]) -> dict:
    grouped = {
        mode: {"react": 0, "reflexion": 0}
        for mode in (
            "entity_drift",
            "incomplete_multi_hop",
            "wrong_final_answer",
            "looping",
            "reflection_overfit",
        )
    }
    for record in records:
        if record.failure_mode != "none":
            grouped[record.failure_mode][record.agent_type] += 1
    return grouped

def build_report(
    records: list[RunRecord],
    dataset_name: str,
    mode: str = "mock",
    running_time_seconds: dict[str, float] | None = None,
    usd_per_million_tokens: float = 0.0,
) -> ReportPayload:
    examples = [{"qid": r.qid, "agent_type": r.agent_type, "gold_answer": r.gold_answer, "predicted_answer": r.predicted_answer, "is_correct": r.is_correct, "attempts": r.attempts, "failure_mode": r.failure_mode, "reflection_count": len(r.reflections)} for r in records]
    return ReportPayload(
        meta={
            "dataset": dataset_name,
            "mode": mode,
            "num_records": len(records),
            "agents": sorted({r.agent_type for r in records}),
            "usd_per_million_tokens": usd_per_million_tokens,
        },
        summary=summarize(
            records,
            running_time_seconds or {},
            usd_per_million_tokens,
        ),
        failure_modes=failure_breakdown(records),
        examples=examples,
        extensions=["structured_evaluator", "reflection_memory", "benchmark_report_json", "mock_mode_for_autograding"],
        discussion="Reflexion có thể sửa câu trả lời khi lần đầu dừng ở hop trung gian hoặc chọn sai thực thể. Đổi lại, agent cần thêm lượt Actor, Evaluator và Reflector nên token, running time và chi phí thường cao hơn ReAct. Hiệu quả thực tế phụ thuộc chất lượng evaluator: evaluator chấm sai sẽ tạo reflection sai và không bảo đảm lần thử sau tốt hơn. Vì vậy nên đọc đồng thời EM, số attempt, token, latency và failure modes thay vì chỉ nhìn accuracy.",
    )


def render_markdown(report: ReportPayload) -> str:
    s = report.summary
    react = s.get("react", {})
    reflexion = s.get("reflexion", {})
    delta = s.get("delta_reflexion_minus_react", {})
    ext_lines = "\n".join(f"- {item}" for item in report.extensions)
    return f"""# Báo cáo Benchmark ReAct và Reflexion

## Metadata
- Dataset: {report.meta['dataset']}
- Mode: {report.meta['mode']}
- Records: {report.meta['num_records']}
- Agents: {', '.join(report.meta['agents'])}

## So sánh ReAct và Reflexion Agent
| Tiêu chí | ReAct | Reflexion |
|---|---|---|
| Cơ chế | Reasoning + acting trong một lượt | Thử, đánh giá, tự phản chiếu rồi thử lại |
| Bộ nhớ lỗi | Không | Có reflection memory |
| Số lượt tối đa | 1 | Cấu hình được, mặc định 3 |
| Ưu điểm | Nhanh, ít token, chi phí thấp | Có khả năng sửa lỗi qua nhiều attempt |
| Hạn chế | Không tự sửa khi trả lời sai | Chậm và tốn token hơn; phụ thuộc evaluator |

## Kết quả
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | {react.get('em', 0)} | {reflexion.get('em', 0)} | {delta.get('em_abs', 0)} |
| Avg attempts | {react.get('avg_attempts', 0)} | {reflexion.get('avg_attempts', 0)} | {delta.get('attempts_abs', 0)} |
| Avg tokens | {react.get('avg_token_estimate', 0)} | {reflexion.get('avg_token_estimate', 0)} | {delta.get('tokens_abs', 0)} |
| Avg model latency (ms) | {react.get('avg_latency_ms', 0)} | {reflexion.get('avg_latency_ms', 0)} | {delta.get('latency_abs', 0)} |

## Ước tính cost và running time
Giả định giá: `${report.meta['usd_per_million_tokens']}` / 1M total tokens.

| Agent | Số mẫu | Total tokens | Running time (s) | Estimated cost (USD) |
|---|---:|---:|---:|---:|
| ReAct | {react.get('count', 0)} | {react.get('total_tokens', 0)} | {react.get('running_time_seconds', 0)} | {react.get('estimated_cost_usd', 0)} |
| Reflexion | {reflexion.get('count', 0)} | {reflexion.get('total_tokens', 0)} | {reflexion.get('running_time_seconds', 0)} | {reflexion.get('estimated_cost_usd', 0)} |

## Failure modes
```json
{json.dumps(report.failure_modes, indent=2)}
```

## Extensions implemented
{ext_lines}

## Discussion
{report.discussion}
"""

def save_report(report: ReportPayload, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
