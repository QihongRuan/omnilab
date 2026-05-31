# OmniLab — Submission copy for AGI House × Google DeepMind Enterprise Build Day

Paste these fields into the AGI House project form (logged in as qihong@agenticsciences.ai).

---

## Project name
**OmniLab**

## One-line tagline (≤ 140 chars)
Antigravity's Science Skills, anywhere. A Gemini 3.5 agent that runs GDM Science Skills outside Antigravity — turning days of biomedical target research into minutes.

## Track
Track 3 — AI for Science

## Short description (≈ 300 words)
OmniLab makes Google DeepMind's Science Skills portable. The skills shipped on May 19 with one designed home — Google Antigravity — and a curated set of 30+ life-science tools (UniProt, AlphaFold DB, Open Targets, ClinVar, EuropePMC, AlphaGenome, ChEMBL, and more). We asked a simple question: what if any agent, in any harness, could call those skills the same way?

OmniLab is a thin orchestrator that exposes each Science Skill as a Gemini function-calling tool. A Gemini 3.5 Flash agent receives a research question, plans a multi-step investigation, picks which skills to invoke, runs the official skill scripts via `uv`, observes the JSON results, and iterates until it can produce a grounded report.

The live demo runs an end-to-end Type 2 Diabetes drug-target discovery workflow. From the prompt *"Find the top 3 druggable T2D targets with strong genetic and structural evidence"*, the agent autonomously:

1. Resolves "type 2 diabetes" → MONDO_0005148 via Open Targets
2. Pulls the top disease-associated targets ranked by overall score
3. Resolves each gene → UniProt accession with function annotations
4. Downloads the AlphaFold predicted structure + pLDDT confidence
5. Queries ClinVar for pathogenic variants per gene
6. Asks Open Targets for druggability/tractability assessment
7. Searches recent EuropePMC literature to anchor the evidence
8. Produces a ranked markdown report with structures, scores, variants, and citations

What normally takes a target-discovery scientist a day of tab-switching across five web portals runs end-to-end in ~3 minutes, with every claim grounded in a real API call.

The pattern generalises: drop in any Skills-format toolkit, swap the system prompt, and you have a portable agent for chemistry, climate, materials, or any other domain.

## What's new
- Wraps the 9 most useful Science Skills as Gemini function-calling tools
- Stateful agent loop with tool result threading, full execution trace, retry on transient failures
- Live AlphaFold structure download per target (`.cif` + PAE)
- Two-format output: machine-readable JSON trace + human-readable markdown report
- Reusable beyond T2D — works for any disease/target question

## Built with
Gemini 3.5 Flash (Vertex AI) · Google DeepMind Science Skills · UniProt · AlphaFold DB · Open Targets · ClinVar · EuropePMC · uv · Python

## Team
Qihong Ruan (Cornell — Agentic Sciences)

## Repo / demo links
- Code: <https://github.com/USER/omnilab>  *(fill in after `git init && git push`)*
- Demo report: `output/reports/t2d_demo.md` in repo
- Demo video: *(record 90 s screen capture before 8pm)*

## Future work
- Add AlphaGenome regulatory-variant scoring once event API keys arrive
- Extend to oncology and rare-disease workflows
- Wrap as an MCP server so the skills become callable from Claude Code, Cursor, and any MCP-aware agent
