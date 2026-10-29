"""Opt-in quality smoke evaluation for the real problem-reframing node.

Run with a configured provider:
    python scripts/eval_llm_quality.py --output outputs/llm_eval.json

This makes real model calls and is intentionally separate from the unit-test
suite. The lexical checks are smoke metrics, not a substitute for expert review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.refine_agent import problem_reframing_node


CASES = [
    {
        "id": "english-medical-segmentation",
        "state": {
            "topic": "medical image segmentation",
            "selected_idea": "Use anatomical priors to improve medical image segmentation under limited labels.",
            "broken_assumption": "Anatomical priors are treated as fixed post-processing rather than learnable constraints.",
            "messages": [{"role": "user", "content": "Medical image segmentation is the main goal."}],
        },
        "anchors": ["segmentation", "anatomical", "medical image"],
    },
    {
        "id": "chinese-retrieval-augmented-generation",
        "state": {
            "topic": "检索增强生成",
            "selected_idea": "针对长文档问答，将检索证据的不确定性传递到答案生成中。",
            "broken_assumption": "现有方法把检索到的片段一律视为同等可靠。",
            "messages": [{"role": "user", "content": "重点仍然是检索增强生成的答案可靠性。"}],
        },
        "anchors": ["检索增强生成", "检索", "答案"],
    },
]


def score_output(output: str, anchors: list[str]) -> dict:
    text = (output or "").strip()
    normalized = text.casefold()
    matched = [anchor for anchor in anchors if anchor.casefold() in normalized]
    return {
        "non_empty": bool(text),
        "min_length": len(text) >= 120,
        "anchor_coverage": len(matched) / max(1, len(anchors)),
        "matched_anchors": matched,
        "characters": len(text),
        "passed_smoke_checks": bool(text) and len(text) >= 120 and bool(matched),
    }


def run_evaluation(output_path: Path) -> dict:
    provider = os.environ.get("RESEARCH_AGENT_LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "auto"
    model = next((os.environ.get(name) for name in (
        "GEMINI_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL", "ANTHROPIC_MODEL", "OLLAMA_MODEL"
    ) if os.environ.get(name)), None)
    results = []

    for case in CASES:
        started = time.perf_counter()
        state = problem_reframing_node(case["state"])
        elapsed = time.perf_counter() - started
        output = str(state.get("reframed_problem") or "")
        results.append({
            "case_id": case["id"],
            "elapsed_seconds": round(elapsed, 3),
            "scores": score_output(output, case["anchors"]),
            "output": output,
        })

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "case_count": len(results),
        "passed_cases": sum(item["scores"]["passed_smoke_checks"] for item in results),
        "results": results,
        "limitations": [
            "Lexical anchor coverage and length do not establish scientific correctness.",
            "Review outputs manually for grounding, usefulness, scope preservation, and language quality.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/llm_eval.json"))
    args = parser.parse_args()

    report = run_evaluation(args.output)
    print(f"Model smoke evaluation: {report['passed_cases']}/{report['case_count']} passed")
    print(f"Report: {args.output}")
    for item in report["results"]:
        print(
            f"- {item['case_id']}: passed={item['scores']['passed_smoke_checks']} "
            f"anchors={item['scores']['anchor_coverage']:.0%} "
            f"chars={item['scores']['characters']} "
            f"time={item['elapsed_seconds']}s"
        )
    return 0 if report["passed_cases"] == report["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
