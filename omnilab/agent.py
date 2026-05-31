"""Gemini 3.5 Flash agent loop that orchestrates GDM Science Skills.

This is the core of OmniLab: it lets Gemini reason about a scientific question,
choose which Science Skills to invoke via function calling, observe the
results, and iterate until it can produce a grounded final report.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types

from omnilab.tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

VERTEX_PROJECT = "qr33-vertex-247397"
VERTEX_LOCATION = "global"
MODEL_ID = "gemini-3.5-flash"  # the headline model for the event
FALLBACK_MODEL_ID = "gemini-2.5-pro"

SYSTEM_INSTRUCTION = """You are OmniLab, a scientific research agent powered by Gemini 3.5 \
and Google DeepMind Science Skills. You have direct, programmatic access to UniProt, \
AlphaFold DB, Open Targets, ClinVar, and EuropePMC.

Your job: given a research question, autonomously plan and execute a multi-step \
investigation using the available tools, then deliver a rigorous, grounded answer.

Rules:
1. NEVER fabricate gene names, accession numbers, association scores, or paper \
   titles. Every claim in your final report must be backed by a tool result.
2. Plan before acting. State a brief plan (1-3 sentences) before your first tool call.
3. Be efficient — don't fetch data you won't use. For T2D-style ranking tasks, \
   3-5 top candidates is plenty.
4. When a tool returns IDs (UniProt accession, Ensembl ID, ClinVar variant IDs), \
   use them in follow-up calls — don't guess.
5. After gathering enough evidence, output a final markdown report. The report \
   MUST include for each ranked target: gene symbol, UniProt accession, association \
   score, druggability assessment, structural confidence (mean pLDDT), and clinical \
   variant evidence — citing the tools used.
6. End the final report with a "Sources" section listing tools invoked and any \
   PubMed IDs / DOIs you cited.
7. STRICT EFFICIENCY RULES (violating these wastes the user's time):
   - For each target, make EXACTLY ONE clinvar_search and ONE clinvar_summary call. \
     The FIRST pathogenic / likely-pathogenic variant in the summary IS your \
     representative — do not keep searching for a "better" missense / SNV / etc.
   - Do not refetch data you already have. If a target's pLDDT is already in the \
     alphafold_fetch_structure result, do NOT also call alphafold_analyze_plddt.
   - Hard budget: 15 tool calls total. After call 12, your next response MUST be \
     the final markdown report.
"""


@dataclass
class Step:
    kind: str  # "plan" | "tool_call" | "tool_result" | "final"
    name: str | None = None
    args: dict[str, Any] | None = None
    text: str | None = None
    seconds: float = 0.0


@dataclass
class AgentTrace:
    question: str
    started_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    steps: list[Step] = field(default_factory=list)
    final_answer: str = ""
    model_used: str = MODEL_ID

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "started_at": self.started_at.isoformat(),
            "model_used": self.model_used,
            "steps": [
                {"kind": s.kind, "name": s.name, "args": s.args, "text": s.text, "seconds": round(s.seconds, 2)}
                for s in self.steps
            ],
            "final_answer": self.final_answer,
        }


def _make_client() -> genai.Client:
    return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)


def _build_tools() -> list[types.Tool]:
    return [types.Tool(function_declarations=TOOL_DECLARATIONS)]


def _function_call_to_dict(fc) -> dict[str, Any]:
    args = dict(fc.args) if fc.args else {}
    return {"name": fc.name, "args": args}


def run_agent(
    question: str,
    max_iters: int = 20,
    log: Callable[[str], None] = print,
) -> AgentTrace:
    client = _make_client()
    tools = _build_tools()
    trace = AgentTrace(question=question)

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=question)]),
    ]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tools,
        temperature=0.2,
    )

    model_id = MODEL_ID
    for iteration in range(max_iters):
        t0 = time.time()
        try:
            resp = client.models.generate_content(model=model_id, contents=contents, config=config)
        except Exception as e:
            if iteration == 0 and model_id == MODEL_ID:
                log(f"[warn] {model_id} unavailable ({e}); falling back to {FALLBACK_MODEL_ID}")
                model_id = FALLBACK_MODEL_ID
                trace.model_used = model_id
                continue
            raise
        elapsed = time.time() - t0

        cand = resp.candidates[0]
        parts = cand.content.parts or []
        function_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        text_parts = [p.text for p in parts if getattr(p, "text", None)]

        if function_calls:
            contents.append(cand.content)
            tool_response_parts: list[types.Part] = []
            for tp in text_parts:
                if tp.strip():
                    log(f"\n[plan] {tp.strip()[:500]}")
                    trace.steps.append(Step(kind="plan", text=tp.strip(), seconds=elapsed))
                    elapsed = 0.0
            for fc in function_calls:
                call = _function_call_to_dict(fc)
                fn_name = call["name"]
                fn_args = call["args"]
                log(f"\n[call] {fn_name}({json.dumps(fn_args)[:200]})")
                trace.steps.append(Step(kind="tool_call", name=fn_name, args=fn_args, seconds=elapsed))
                elapsed = 0.0

                fn = TOOL_FUNCTIONS.get(fn_name)
                t1 = time.time()
                if fn is None:
                    result = f"ERROR: unknown tool {fn_name}"
                else:
                    try:
                        result = fn(**fn_args)
                    except Exception as exc:
                        result = f"ERROR running {fn_name}: {exc}"
                tool_seconds = time.time() - t1
                preview = result[:240].replace("\n", " ")
                log(f"[result {tool_seconds:.1f}s] {preview}{'...' if len(result) > 240 else ''}")
                trace.steps.append(
                    Step(kind="tool_result", name=fn_name, text=result, seconds=tool_seconds)
                )
                tool_response_parts.append(
                    types.Part.from_function_response(name=fn_name, response={"result": result})
                )
            contents.append(types.Content(role="user", parts=tool_response_parts))
            continue

        # Pure text response = final answer
        final_text = "\n".join(t for t in text_parts if t).strip()
        trace.final_answer = final_text
        trace.steps.append(Step(kind="final", text=final_text, seconds=elapsed))
        log(f"\n[final] ({len(final_text)} chars)")
        return trace

    log(f"\n[warn] hit max_iters={max_iters} without final answer")
    return trace


def save_trace(trace: AgentTrace, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace.to_jsonable(), indent=2))
    return path
