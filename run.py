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

from omnilab.agent import run_agent, save_trace
from omnilab.report import save_markdown


DEFAULT_QUESTION = (
    "Find the top 3 druggable targets for Type 2 Diabetes with the strongest combined "
    "genetic, structural, and clinical-variant evidence. For each, give the gene symbol, "
    "UniProt accession, Open Targets association score, druggability/tractability, mean "
    "AlphaFold pLDDT, and a representative pathogenic ClinVar variant. Conclude with a "
    "short ranking rationale."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="OmniLab — Gemini × GDM Science Skills agent")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="Research question")
    parser.add_argument("--name", default=None, help="Output filename stem (default: timestamp)")
    parser.add_argument("--max-iters", type=int, default=20)
    args = parser.parse_args()

    stem = args.name or dt.datetime.utcnow().strftime("run_%Y%m%d_%H%M%S")
    out_dir = Path("output") / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 70}\nOmniLab — research question\n{'=' * 70}")
    print(args.question)
    print(f"{'=' * 70}\n")

    trace = run_agent(args.question, max_iters=args.max_iters)

    trace_path = save_trace(trace, out_dir / f"{stem}.trace.json")
    md_path = save_markdown(trace, out_dir / f"{stem}.md")

    print(f"\n{'=' * 70}")
    print(f"Saved trace : {trace_path}")
    print(f"Saved report: {md_path}")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
