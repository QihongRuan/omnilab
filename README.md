# OmniLab

**Antigravity's Science Skills, anywhere.**

A Gemini 3.5 Flash agent that runs Google DeepMind's [Science Skills](https://github.com/google-deepmind/science-skills) outside of Antigravity — turning days of biomedical target research into minutes.

Built for **Track 3: AI for Science** at the AGI House × Google DeepMind Enterprise Build Day (2026-05-30).

## What it does

Given a research question like *"Find the top 3 druggable T2D targets with strong genetic and structural evidence"*, OmniLab:

1. Plans a multi-step investigation with Gemini 3.5 Flash
2. Invokes Science Skills as Gemini function-calling tools — Open Targets → UniProt → AlphaFold DB → ClinVar → EuropePMC
3. Threads each skill's JSON output back into the agent loop
4. Produces a grounded markdown report with every claim anchored to a tool call

Time: ~30 seconds of model thinking + ~22 seconds of API calls = a complete drug-target dossier in under a minute.

## Live demo

```bash
python run.py --name t2d_demo
```

This runs the canonical Type 2 Diabetes demo. See [`output/reports/t2d_demo.md`](output/reports/t2d_demo.md) for a sample report (top 3 T2D targets: KCNJ11, ABCC8, GCK — each with UniProt accession, OT score, druggability, mean AlphaFold pLDDT, and a representative pathogenic ClinVar variant).

## Custom questions

```bash
python run.py "What are the top 5 druggable targets for NASH?"
python run.py --name obesity "Which obesity-associated targets have the highest AlphaFold confidence?"
```

## Architecture

```
run.py
 └── omnilab.agent.run_agent()              ← Gemini 3.5 Flash loop, function calling
      └── omnilab.tools.TOOL_FUNCTIONS      ← 9 wrappers over Science Skills scripts
           └── uv run science-skills/skills/<skill>/scripts/<x>.py
                                             ↑
                                    The official, unmodified GDM Science Skills
```

Skills wired in:

| Tool | Skill | Purpose |
|------|-------|---------|
| `literature_search` | `literature_search_europepmc` | Find recent papers |
| `opentargets_search_disease` | `opentargets_database` | Disease → EFO/MONDO id |
| `opentargets_associated_targets` | `opentargets_database` | Top targets ranked |
| `opentargets_target_druggability` | `opentargets_database` | Tractability + safety |
| `uniprot_search` | `uniprot_database` | Gene → UniProt accession + function |
| `alphafold_fetch_structure` | `alphafold_database_fetch_and_analyze` | Structure CIF + pLDDT |
| `alphafold_analyze_plddt` | `alphafold_database_fetch_and_analyze` | Per-residue confidence |
| `clinvar_search` | `clinvar_database` | Variants per gene |
| `clinvar_summary` | `clinvar_database` | Variant phenotypes + significance |

Adding a tenth skill = ~10 lines in `omnilab/tools.py`.

## Setup

Prereqs: Python ≥ 3.11, [`uv`](https://docs.astral.sh/uv/), and a Vertex AI project with Gemini access via ADC.

```bash
pip install google-genai
git clone https://github.com/google-deepmind/science-skills.git
python run.py
```

Edit `omnilab/agent.py` to point at your own Vertex project / region.

## What's portable

Science Skills shipped on May 19 as a curated bundle for Antigravity. OmniLab demonstrates that the same skill files — unmodified — work as tool-callable backends for any agent framework. The pattern transfers to MCP, LangGraph, AutoGen, or a hand-rolled loop like this one.

## Built with

- Gemini 3.5 Flash (Vertex AI, `location="global"`)
- Google DeepMind Science Skills v1.0.0
- UniProt · AlphaFold DB · Open Targets · ClinVar · EuropePMC
- `uv` for hermetic per-skill dependency isolation

## License

Apache 2.0 (matches the underlying Science Skills). Science Skills carry their own per-source licenses — see [`science-skills/SKILL_LICENSES.md`](science-skills/SKILL_LICENSES.md) before commercial use.
