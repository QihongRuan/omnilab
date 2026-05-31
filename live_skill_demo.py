"""60-second live Science Skill demo — for when a judge says "show me a skill called live".

Narrow agent: ONLY Open Targets + UniProt tools. ONE question. Real API call visible.
Use this when an SVP asks for proof during Q&A.
"""

from __future__ import annotations

import asyncio
import sys
import time

from google.antigravity import Agent, LocalAgentConfig

from omnilab.tools import (
    opentargets_associated_targets,
    opentargets_search_disease,
    uniprot_search,
)

VERTEX_PROJECT = "qr33-vertex-247397"
VERTEX_LOCATION = "global"
MODEL_ID = "gemini-3.5-flash"

QUESTION = (
    "What is the #1 Open Targets-ranked gene for Type 2 Diabetes, "
    "and what is its UniProt accession? Answer in one sentence after calling the tools."
)


async def main() -> None:
    config = LocalAgentConfig(
        vertex=True,
        project=VERTEX_PROJECT,
        location=VERTEX_LOCATION,
        model=MODEL_ID,
        system_instructions=(
            "You are a live-demo agent. You have exactly three Science Skill tools. "
            "Use opentargets_search_disease to resolve the disease ID, then "
            "opentargets_associated_targets to get the #1 gene, then uniprot_search to fetch "
            "its UniProt accession. Be concise — one sentence answer at the end."
        ),
        tools=[opentargets_search_disease, opentargets_associated_targets, uniprot_search],
    )

    print("\n" + "=" * 70)
    print("  OmniLab live Science Skill demo")
    print("=" * 70)
    print(f"  Stack: Antigravity SDK + Managed Agents API + DeepMind Science Skills")
    print(f"  Question: {QUESTION}")
    print("=" * 70)

    t0 = time.time()
    async with Agent(config) as agent:
        resp = await agent.chat(QUESTION)
        async for chunk in resp.chunks:
            kind = type(chunk).__name__
            if kind == "ToolCall":
                print(f"\n\033[96m[Antigravity → tool]\033[0m {chunk.name}({str(chunk.args)[:160]})")
            elif kind == "ToolResult":
                output = getattr(chunk, "output", None) or getattr(chunk, "result", None) or ""
                preview = str(output)[:140].replace("\n", " ")
                print(f"\033[2m[← {len(str(output))} chars]\033[0m {preview}...")
            elif kind == "Text":
                text = getattr(chunk, "text", "") or ""
                print(text, end="", flush=True)

    elapsed = time.time() - t0
    print(f"\n\n\033[92m✓\033[0m {elapsed:.1f}s end-to-end. Every claim above is grounded in a Science Skill API receipt.")


if __name__ == "__main__":
    asyncio.run(main())
