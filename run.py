"""OmniLab CLI: ask a scientific question, get a grounded report.

Examples:

    # Default T2D demo
    python run.py

    # Custom question
    python run.py "What are the top 5 druggable targets for non-alcoholic steatohepatitis?"

    # Save to a specific output name
    python run.py --name nash "What are the top 5 druggable targets for NASH?"
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import asyncio
from omnilab.agent_v3 import run as run_v3


DEFAULT_QUESTION = (
    "Find the top 3 druggable targets for Type 2 Diabetes with the strongest combined "
    "genetic, structural, and clinical-variant evidence. For each, give the gene symbol, "
    "UniProt accession, Open Targets association score, druggability/tractability, mean "
    "AlphaFold pLDDT, and a representative pathogenic ClinVar variant. Conclude with a "
    "short ranking rationale."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="OmniLab — Antigravity SDK + DeepMind Science Skills agent")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="Research question")
    parser.add_argument("--name", default=None, help="Output filename stem (default: timestamp)")
    args = parser.parse_args()

    stem = args.name or dt.datetime.utcnow().strftime("run_%Y%m%d_%H%M%S")
    asyncio.run(run_v3(args.question, name=stem))
    return 0


if __name__ == "__main__":
    sys.exit(main())
