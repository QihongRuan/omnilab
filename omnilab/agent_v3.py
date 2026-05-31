"""OmniLab v3 — Antigravity SDK + Managed Agents API, orchestrating our
deterministic Science Skills wrappers as first-class tools.

Differences from v2:
- We pass our v1 Science Skill wrappers EXPLICITLY as `tools=[...]`.
- We do NOT pass `skills_paths` or `workspaces`, so the Antigravity agent
  cannot shortcut by reading prior log files. It has to actually invoke
  the Science Skills via the Python callables we hand it.
- Each wrapper prints a visible `[SCIENCE SKILL]` receipt before the API call,
  so a live judge can see the network activity.
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

from omnilab.tools import (
    alphafold_analyze_plddt,
    alphafold_fetch_structure,
    clinvar_search,
    clinvar_summary,
    literature_search,
    opentargets_associated_targets,
    opentargets_search_disease,
    opentargets_target_druggability,
    uniprot_search,
)

OUTPUT_DIR = (Path(__file__).resolve().parents[1] / "output" / "reports").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VERTEX_PROJECT = "qr33-vertex-247397"
VERTEX_LOCATION = "global"
MODEL_ID = "gemini-3.5-flash"

SCIENCE_SKILL_TOOLS = [
    literature_search,
    opentargets_search_disease,
    opentargets_associated_targets,
    opentargets_target_druggability,
    uniprot_search,
    alphafold_fetch_structure,
    alphafold_analyze_plddt,
    clinvar_search,
    clinvar_summary,
]

SYSTEM_INSTRUCTIONS = """You are OmniLab — an enterprise biomedical target-validation agent built on the Google Antigravity SDK + Managed Agents API.

You orchestrate the official Google DeepMind Science Skills (Open Targets, UniProt, AlphaFold DB, ClinVar, EuropePMC) via deterministic Python wrappers. Every claim you make in your final report MUST come from a tool result — do not rely on training-data recall for gene names, accessions, scores, variants, or citations.

Workflow:
1. Plan: one sentence before each tool call describing why.
2. Resolve disease → MONDO/EFO id first via opentargets_search_disease.
3. Pull top associated targets via opentargets_associated_targets.
4. For each finalist target:
   - uniprot_search to get the canonical accession + function
   - opentargets_target_druggability for tractability
   - alphafold_fetch_structure for mean pLDDT (already in the result, no need to also analyze_plddt unless you want per-residue detail)
   - clinvar_search → clinvar_summary (ONE of each per gene). Take the FIRST pathogenic / likely-pathogenic record as the representative variant. Do NOT keep filtering for a "perfect" SNV.
5. Strict budget: at most 18 total tool calls. After call 16, your next response MUST be the final markdown report.
6. Final report MUST include for each ranked target: gene symbol, UniProt accession, Open Targets association score, druggability/tractability, mean AlphaFold pLDDT, and one representative pathogenic ClinVar variant in HGVS notation. End with a `## Sources` section listing the Science Skills invoked.
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
    elapsed_seconds: float = 0.0

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "started_at": self.started_at.isoformat(),
            "model": MODEL_ID,
            "stack": "Antigravity SDK + Managed Agents API + DeepMind Science Skills",
            "chunks": self.chunks,
            "final_text": self.final_text,
            "usage": self.usage,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
        }


async def run(question: str = DEFAULT_QUESTION, name: str = "t2d_v3") -> Trace:
    config = LocalAgentConfig(
        vertex=True,
        project=VERTEX_PROJECT,
        location=VERTEX_LOCATION,
        model=MODEL_ID,
        system_instructions=SYSTEM_INSTRUCTIONS,
        tools=SCIENCE_SKILL_TOOLS,
    )

    trace = Trace(question=question)
    t0 = asyncio.get_event_loop().time()
    print(f"\n{'=' * 70}\nOmniLab v3 — Antigravity SDK + Managed Agents API + Science Skills\n{'=' * 70}")
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
                print(f"\n\033[96m[Antigravity → tool]\033[0m {entry['name']}({json.dumps(entry['args'])[:200]})", flush=True)
            elif kind == "ToolResult":
                output = getattr(chunk, "output", None) or getattr(chunk, "result", None) or ""
                entry["name"] = getattr(chunk, "name", None)
                entry["output_preview"] = str(output)[:1500]
                preview = str(output)[:200].replace("\n", " ")
                print(f"\033[2m[← result {len(str(output))} chars]\033[0m {preview}{'…' if len(str(output)) > 200 else ''}")
            elif kind == "Text":
                text = getattr(chunk, "text", "") or ""
                entry["text"] = text
                if text.strip():
                    print(text, end="", flush=True)
            elif kind == "Thought":
                pass  # don't dump thoughts to console
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
    trace.elapsed_seconds = asyncio.get_event_loop().time() - t0

    n_tool_calls = sum(1 for c in trace.chunks if c["kind"] == "ToolCall")
    print(f"\n\n{'=' * 70}")
    print(f"\033[92m✓\033[0m DONE in {trace.elapsed_seconds:.1f}s — {n_tool_calls} Science Skill calls")
    if trace.usage:
        print(f"  tokens: {trace.usage['total_tokens']:,} total ({trace.usage['cached_tokens']:,} cached, {trace.usage.get('thinking_tokens') or 0:,} thinking)")

    trace_path = OUTPUT_DIR / f"{name}.trace.json"
    trace_path.write_text(json.dumps(trace.to_jsonable(), indent=2, default=str))
    report_path = OUTPUT_DIR / f"{name}.md"
    report_path.write_text(render_report(trace))
    print(f"  trace : {trace_path}")
    print(f"  report: {report_path}")
    print("=" * 70)
    return trace


def render_report(trace: Trace) -> str:
    n_tool_calls = sum(1 for c in trace.chunks if c["kind"] == "ToolCall")
    lines = [
        "# OmniLab Report",
        "",
        f"**Question:** {trace.question}",
        "",
        f"**Stack:** Google Antigravity SDK · Managed Agents API · Gemini 3.5 Flash (Vertex `{VERTEX_LOCATION}`)",
        f"**Started:** {trace.started_at.isoformat()}Z",
        f"**Elapsed:** {trace.elapsed_seconds:.1f} s end-to-end",
        f"**Science Skill calls:** {n_tool_calls}",
    ]
    if trace.usage:
        lines.append(
            f"**Tokens:** {trace.usage['total_tokens']:,} total "
            f"({trace.usage['cached_tokens']:,} cached, "
            f"{trace.usage.get('thinking_tokens') or 0:,} thinking)"
        )
    lines += [
        "",
        "---",
        "",
        "## Final Answer",
        "",
        trace.final_text or "_(no final answer produced)_",
        "",
        "---",
        "",
        "## Science Skill calls (audit trail)",
        "",
    ]
    call_num = 0
    for c in trace.chunks:
        if c["kind"] == "ToolCall":
            call_num += 1
            args = json.dumps(c.get("args") or {})[:200]
            lines.append(f"{call_num}. `{c.get('name')}({args})`")
    lines.append("")
    lines.append("_Generated by OmniLab — Antigravity SDK + Managed Agents API + DeepMind Science Skills_")
    return "\n".join(lines)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUESTION
    asyncio.run(run(q))
