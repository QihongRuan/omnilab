"""OmniLab v2 — built on the official Antigravity SDK (Managed Agents API).

This rewrites the v1 hand-rolled Gemini function-calling loop to use the
google.antigravity SDK. Two consequences:

1. We claim the new stack honestly: Antigravity SDK + Managed Agents API + Gemini 3.5 Flash.
2. We let the SDK's local harness load Science Skills natively via skills_paths.
   The agent gets the SKILL.md instruction files plus the `uv run` invocation
   protocol the way Antigravity expects.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.antigravity import Agent, LocalAgentConfig

SKILLS_DIR = (Path(__file__).resolve().parents[2] / "science-skills" / "skills").resolve()
OUTPUT_DIR = (Path(__file__).resolve().parents[1] / "output" / "reports").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VERTEX_PROJECT = "qr33-vertex-247397"
VERTEX_LOCATION = "global"
MODEL_ID = "gemini-3.5-flash"

SYSTEM_INSTRUCTIONS = """You are OmniLab — an enterprise-grade biomedical target-discovery agent built on the Managed Agents API.

You have access to Google DeepMind Science Skills covering UniProt, AlphaFold DB, Open Targets, ClinVar, EuropePMC, and ~30 other life-science databases. Use these official Skills to investigate research questions.

Workflow rules:
1. Before any tool call, state a brief plan (one sentence).
2. NEVER fabricate gene symbols, accessions, scores, variants, or citations. Every claim in the final report must come from a Skill result.
3. Use IDs returned by previous calls — don't guess Ensembl IDs, UniProt accessions, ClinVar variant IDs, etc.
4. EFFICIENCY (strict): One clinvar_search + one clinvar_summary per gene. Take the FIRST pathogenic / likely-pathogenic record as the representative variant — do NOT keep filtering for a "better" variant. Budget: at most 15 tool calls before final report.
5. Final report MUST be in markdown and for each ranked target include: gene symbol, UniProt accession, Open Targets association score, druggability/tractability, mean AlphaFold pLDDT, and one representative pathogenic ClinVar variant (HGVS notation if available).
6. End with a `## Sources` section listing the Skills invoked.
"""

DEFAULT_QUESTION = (
    "Find the top 3 druggable targets for Type 2 Diabetes with the strongest combined "
    "genetic, structural, and clinical-variant evidence. For each, give the gene symbol, "
    "UniProt accession, Open Targets association score, druggability/tractability, mean "
    "AlphaFold pLDDT, and a representative pathogenic ClinVar variant. Conclude with a "
    "short ranking rationale."
)


@dataclass
class Trace:
    question: str
    started_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    final_text: str = ""
    usage: dict[str, Any] | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "started_at": self.started_at.isoformat(),
            "model": MODEL_ID,
            "skills_dir": str(SKILLS_DIR),
            "chunks": self.chunks,
            "final_text": self.final_text,
            "usage": self.usage,
        }


async def run(question: str = DEFAULT_QUESTION, name: str = "t2d_v2") -> Trace:
    config = LocalAgentConfig(
        vertex=True,
        project=VERTEX_PROJECT,
        location=VERTEX_LOCATION,
        model=MODEL_ID,
        system_instructions=SYSTEM_INSTRUCTIONS,
        skills_paths=[str(SKILLS_DIR)],
        workspaces=[str(OUTPUT_DIR.parent)],
    )

    trace = Trace(question=question)
    print(f"\n{'=' * 70}\nOmniLab v2 (Antigravity SDK + Managed Agents API)\n{'=' * 70}")
    print(question)
    print("=" * 70)

    async with Agent(config) as agent:
        resp = await agent.chat(question)
        async for chunk in resp.chunks:
            kind = type(chunk).__name__
            entry: dict[str, Any] = {"kind": kind}
            if kind == "ToolCall":
                entry["name"] = getattr(chunk, "name", None)
                entry["args"] = getattr(chunk, "args", None)
                print(f"\n[call] {entry['name']}({json.dumps(entry['args'])[:200]})")
            elif kind == "ToolResult":
                entry["name"] = getattr(chunk, "name", None)
                output = getattr(chunk, "output", None) or getattr(chunk, "result", None) or ""
                entry["output_preview"] = str(output)[:1500]
                preview = str(output)[:240].replace("\n", " ")
                print(f"[result] {preview}{'...' if len(str(output)) > 240 else ''}")
            elif kind == "Text":
                text = getattr(chunk, "text", "") or ""
                entry["text"] = text
                if text.strip():
                    preview = text.strip()[:300].replace("\n", " ")
                    print(f"\n[text] {preview}{'...' if len(text) > 300 else ''}")
            else:
                entry["repr"] = str(chunk)[:300]
            trace.chunks.append(entry)

        trace.final_text = await resp.text()
        um = resp.usage_metadata
        if um:
            trace.usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", None),
                "cached_tokens": getattr(um, "cached_content_token_count", None),
                "output_tokens": getattr(um, "candidates_token_count", None),
                "thinking_tokens": getattr(um, "thoughts_token_count", None),
                "total_tokens": getattr(um, "total_token_count", None),
            }

    # save trace + report
    trace_path = OUTPUT_DIR / f"{name}.trace.json"
    trace_path.write_text(json.dumps(trace.to_jsonable(), indent=2, default=str))
    report_path = OUTPUT_DIR / f"{name}.md"
    report_md = render_report(trace)
    report_path.write_text(report_md)

    print(f"\n{'=' * 70}")
    print(f"trace : {trace_path}")
    print(f"report: {report_path}")
    if trace.usage:
        print(f"usage : {trace.usage}")
    print("=" * 70)
    return trace


def render_report(trace: Trace) -> str:
    n_tool_calls = sum(1 for c in trace.chunks if c["kind"] == "ToolCall")
    lines = [
        "# OmniLab v2 Report",
        "",
        f"**Question:** {trace.question}",
        "",
        f"**Stack:** Antigravity SDK · Managed Agents API · Gemini 3.5 Flash (Vertex `{VERTEX_LOCATION}`)",
        f"**Started:** {trace.started_at.isoformat()}Z",
        f"**Skill calls:** {n_tool_calls}",
        f"**Tokens:** {trace.usage}" if trace.usage else "",
        "",
        "---",
        "",
        "## Final Answer",
        "",
        trace.final_text or "_(no final answer produced)_",
        "",
        "---",
        "",
        "## Skill calls",
        "",
    ]
    for i, c in enumerate(trace.chunks, 1):
        if c["kind"] == "ToolCall":
            lines.append(f"{i}. `{c.get('name')}({json.dumps(c.get('args') or {})[:200]})`")
    lines.append("")
    lines.append("_Generated by OmniLab v2 — Google Antigravity SDK_")
    return "\n".join(lines)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUESTION
    asyncio.run(run(q))
