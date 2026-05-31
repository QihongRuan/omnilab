# OmniLab

**Agentic Target Validation: zero-hallucination bioinformatics powered by the Google Antigravity SDK + Managed Agents API + DeepMind Science Skills.**

Built for **Track 3: AI for Science** at the AGI House × Google DeepMind Enterprise Build Day (2026-05-30).

![T2D demo](output/reports/t2d_v3.gif)

## What it does

In biopharma, LLM hallucination isn't an annoyance — it's a critical failure point for target discovery. OmniLab is an autonomous **Principal Investigator agent** that grounds every claim in a verifiable Science Skill API call.

Given a research question like *"Find the top 3 druggable T2D targets with strong genetic and structural evidence"*, OmniLab:

1. Plans a multi-step investigation with Gemini 3.5 Flash via the Antigravity SDK
2. Orchestrates 9 distinct GDM Science Skills (Open Targets, UniProt, AlphaFold DB, ClinVar, EuropePMC) as deterministic Python tools
3. Threads each skill's JSON output back through the agent loop
4. Produces a grounded markdown report — every claim anchored to a real API call, printed as a visible `[SCIENCE SKILL]` receipt

End-to-end: **~80 seconds, 16 Science Skill calls**, fully grounded T2D target dossier.

## Live demo

```bash
python -m omnilab.agent_v3
```

Watch the green `[SCIENCE SKILL]` receipts scroll past while the agent autonomously:
- Resolves "type 2 diabetes" → MONDO_0005148 via Open Targets
- Pulls the top disease-associated targets ranked by overall score
- For each finalist (KCNJ11 / ABCC8 / PPARG):
  - UniProt search for canonical accession + function
  - Open Targets tractability assessment
  - AlphaFold structure download + mean pLDDT
  - ClinVar pathogenic variant lookup
- Synthesises a ranked report with HGVS-notated variants and mechanistic rationale

See [`output/reports/t2d_v3.md`](output/reports/t2d_v3.md) for a sample report.

## Micro-demo (for Q&A)

When a judge says *"show me a Science Skill being called live"*:

```bash
python live_skill_demo.py
```

Runs in ~15 seconds. Narrow 3-tool agent answers *"What is the #1 Open Targets-ranked gene for Type 2 Diabetes, and what is its UniProt accession?"* with visible API receipts.

## Custom questions

```bash
python -m omnilab.agent_v3 "What are the top 5 druggable targets for NASH?"
python -m omnilab.agent_v3 "Which obesity-associated targets have the highest AlphaFold confidence?"
```

## Architecture

```
omnilab/agent_v3.py
 └── google.antigravity.Agent + LocalAgentConfig(vertex=True, model="gemini-3.5-flash",
                                                  tools=[…9 Science Skill wrappers…])
      └── omnilab.tools.TOOL_FUNCTIONS  ← prints [SCIENCE SKILL] receipt before each call
           └── uv run science-skills/skills/<skill>/scripts/<x>.py
                                                ↑
                                The official, unmodified GDM Science Skills
```

### Science Skills wired in

| Tool | Skill | Purpose |
|------|-------|---------|
| `opentargets_search_disease` | `opentargets_database` | Disease → EFO/MONDO id |
| `opentargets_associated_targets` | `opentargets_database` | Top targets ranked |
| `opentargets_target_druggability` | `opentargets_database` | Tractability + safety |
| `uniprot_search` | `uniprot_database` | Gene → UniProt accession + function |
| `alphafold_fetch_structure` | `alphafold_database_fetch_and_analyze` | Structure CIF + mean pLDDT |
| `alphafold_analyze_plddt` | `alphafold_database_fetch_and_analyze` | Per-residue confidence |
| `clinvar_search` | `clinvar_database` | Variants per gene |
| `clinvar_summary` | `clinvar_database` | Variant phenotypes + significance |
| `literature_search` | `literature_search_europepmc` | Recent biomedical papers |

Adding a tenth skill = ~15 lines in `omnilab/tools.py`.

## Provenance — the SVP-friendly receipt

Every Science Skill call prints a coloured receipt before the network request:

```
[Antigravity → tool] alphafold_fetch_structure({"uniprot_accession": "Q14654"})
[SCIENCE SKILL] AlphaFold DB → fetch structure Q14654
[← result 412 chars] {"uniprot": "Q14654", "mean_pLDDT_global": 83.81, …}
```

The final report's `## Science Skill calls` section is a complete numbered audit trail — every biological claim in the report can be traced back to a specific call.

## Setup

Prereqs: Python ≥ 3.11, [`uv`](https://docs.astral.sh/uv/), and a Vertex AI project with Gemini access via ADC.

```bash
pip install google-antigravity google-genai
git clone https://github.com/google-deepmind/science-skills.git
python -m omnilab.agent_v3
```

Edit `omnilab/agent_v3.py` to point at your own Vertex project / region.

## What's new (vs. our v1 / v2 internal drafts)

- **v1** (`omnilab/agent.py`): hand-rolled Gemini function-calling loop. Worked, but didn't use the official Antigravity stack.
- **v2** (`omnilab/agent_v2.py`): ported to Antigravity SDK with `skills_paths`. The agent had file-system tools and shortcut by reading prior logs — honest but didn't exercise the Skills primitives.
- **v3** (`omnilab/agent_v3.py`): Antigravity SDK + Managed Agents API with our deterministic Science Skill wrappers as explicit `tools=[…]`, no workspace shortcut. The agent CANNOT cheat — it has to invoke the Science Skills to answer. This is what you should run.

## Built with

- Google Antigravity SDK 0.1.1 (`pip install google-antigravity`)
- Managed Agents API (Gemini 3.5 Flash on Vertex AI, `location="global"`)
- Google DeepMind Science Skills v1.0.0
- UniProt · AlphaFold DB · Open Targets · ClinVar · EuropePMC
- `uv` for hermetic per-skill dependency isolation

## License

Apache 2.0. Science Skills carry their own per-source licenses — see [`science-skills/SKILL_LICENSES.md`](science-skills/SKILL_LICENSES.md) before commercial use.
