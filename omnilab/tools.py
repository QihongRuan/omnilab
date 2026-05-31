"""Thin Python wrappers over GDM Science Skills CLI scripts.

Each function shells out to `uv run` on the corresponding skill script. Scripts
that write JSON to `--output FILE` are read back and trimmed before returning
to the Gemini agent loop.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "science-skills" / "skills"
OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
(OUTPUT_ROOT / "structures").mkdir(parents=True, exist_ok=True)
(OUTPUT_ROOT / "tool_runs").mkdir(parents=True, exist_ok=True)

USER_AGENT = "OmniLab/1.0 (qr33@cornell.edu)"

# ANSI colors for receipt printing — judges should physically see the API call.
_GREEN = "\033[92m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _receipt(skill: str, action: str) -> None:
    """Print a visible receipt before each Science Skill API invocation."""
    print(f"{_GREEN}[SCIENCE SKILL]{_RESET} {skill} → {_DIM}{action}{_RESET}", flush=True)


def _env() -> dict[str, str]:
    e = os.environ.copy()
    e["SCIENCE_SKILLS_USER_AGENT"] = USER_AGENT
    return e


def _run(skill: str, script: str, args: list[str], timeout: int = 180) -> str:
    script_path = SKILLS_ROOT / skill / "scripts" / script
    cmd = ["uv", "run", str(script_path), *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_env(),
        cwd=str(SKILLS_ROOT),
    )
    if proc.returncode != 0:
        return f"ERROR (exit {proc.returncode}): {(proc.stderr or proc.stdout)[:2000]}"
    return proc.stdout


def _run_to_json(
    skill: str,
    script: str,
    args_before_output: list[str],
    out_name: str,
    args_after_output: list[str] | None = None,
    timeout: int = 180,
) -> dict[str, Any] | str:
    """Run a skill that writes JSON to --output FILE, then load & return the dict."""
    out_path = OUTPUT_ROOT / "tool_runs" / out_name
    args_after_output = args_after_output or []
    args = [*args_before_output, "--output", str(out_path), *args_after_output]
    result = _run(skill, script, args, timeout=timeout)
    if result.startswith("ERROR"):
        return result
    if not out_path.exists():
        return f"ERROR: skill ran but produced no output file. stdout={result[:500]}"
    try:
        return json.loads(out_path.read_text())
    except json.JSONDecodeError as e:
        return f"ERROR parsing JSON: {e}"


def _trim(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _trim_json(data: Any, limit: int = 6000) -> str:
    return _trim(json.dumps(data, indent=2, default=str), limit=limit)


# ---------- LITERATURE ----------

def literature_search(query: str, max_results: int = 5) -> str:
    """Search EuropePMC for biomedical papers."""
    _receipt("EuropePMC", f'search "{query[:60]}" (max {max_results})')
    data = _run_to_json(
        "literature_search_europepmc",
        "europepmc_api.py",
        ["search", query],
        out_name=f"pmc_{abs(hash(query)) % 10_000_000}.json",
        args_after_output=["--max_results", str(max_results), "--sort", "P_PDATE_D desc"],
    )
    if isinstance(data, str):
        return data
    rs = data.get("results", [])
    simplified = [
        {
            "title": r.get("title"),
            "authors": r.get("authorString"),
            "journal": r.get("journalTitle") or (r.get("journalInfo") or {}).get("journal", {}).get("title"),
            "year": r.get("pubYear"),
            "pmid": r.get("pmid"),
            "doi": r.get("doi"),
            "abstract": (r.get("abstractText") or "")[:600],
        }
        for r in rs
    ]
    return _trim_json({"hit_count": data.get("hitCount"), "papers": simplified})


# ---------- OPENTARGETS ----------

def opentargets_search_disease(query: str) -> str:
    """Resolve a disease name to its EFO/MONDO ID."""
    _receipt("Open Targets", f'search-disease "{query}"')
    data = _run_to_json(
        "opentargets_database",
        "query_opentargets.py",
        [],
        out_name=f"ot_disease_{abs(hash(query)) % 10_000_000}.json",
        args_after_output=["search-disease", query],
    )
    if isinstance(data, str):
        return data
    return _trim_json(data)


def opentargets_associated_targets(efo_id: str, limit: int = 10) -> str:
    """Top targets associated with a disease."""
    _receipt("Open Targets", f"get-associated-targets {efo_id} (top {limit})")
    data = _run_to_json(
        "opentargets_database",
        "query_opentargets.py",
        ["--limit", str(limit)],
        out_name=f"ot_assoc_{efo_id}.json",
        args_after_output=["get-associated-targets", efo_id],
    )
    if isinstance(data, str):
        return data
    return _trim_json(data)


def opentargets_target_druggability(ensembl_id: str) -> str:
    """Druggability / tractability assessment for a target."""
    _receipt("Open Targets", f"get-target-druggability {ensembl_id}")
    data = _run_to_json(
        "opentargets_database",
        "query_opentargets.py",
        [],
        out_name=f"ot_drug_{ensembl_id}.json",
        args_after_output=["get-target-druggability", ensembl_id],
    )
    if isinstance(data, str):
        return data
    return _trim_json(data)


# ---------- UNIPROT ----------

def uniprot_search(query: str, limit: int = 3) -> str:
    """Search UniProtKB. Use field-prefixed queries like 'gene:KCNJ11 AND organism_id:9606 AND reviewed:true'."""
    _receipt("UniProt", f'search "{query[:60]}" (limit {limit})')
    out = _run(
        "uniprot_database",
        "uniprot_tools.py",
        [
            "search",
            query,
            "--limit",
            str(limit),
            "--fields",
            "accession,id,gene_names,protein_name,length,cc_function,cc_subcellular_location",
            "--format",
            "json",
        ],
    )
    if out.startswith("ERROR"):
        return out
    try:
        data = json.loads(out)
        simplified = [
            {
                "accession": r.get("primaryAccession"),
                "id": r.get("uniProtkbId"),
                "name": ((r.get("proteinDescription") or {}).get("recommendedName") or {}).get("fullName", {}).get("value"),
                "gene": [g.get("geneName", {}).get("value") for g in (r.get("genes") or [])],
                "length": (r.get("sequence") or {}).get("length"),
                "function": " ".join(
                    c.get("texts", [{}])[0].get("value", "")
                    for c in (r.get("comments") or [])
                    if c.get("commentType") == "FUNCTION"
                )[:400],
            }
            for r in (data.get("results") or [])
        ]
        return _trim_json(simplified)
    except json.JSONDecodeError:
        return _trim(out)


# ---------- ALPHAFOLD ----------

def alphafold_fetch_structure(uniprot_accession: str) -> str:
    """Fetch AlphaFold structure + metadata; returns pLDDT summary."""
    _receipt("AlphaFold DB", f"fetch structure {uniprot_accession}")
    out_dir = OUTPUT_ROOT / "structures" / uniprot_accession
    out_dir.mkdir(parents=True, exist_ok=True)
    out = _run(
        "alphafold_database_fetch_and_analyze",
        "fetch_structure.py",
        [uniprot_accession, "-o", str(out_dir)],
    )
    if out.startswith("ERROR"):
        return out
    meta_files = list(out_dir.glob("*metadata.json"))
    cif_files = list(out_dir.glob("*.cif"))
    summary = {
        "uniprot": uniprot_accession,
        "cif_file": str(cif_files[0]) if cif_files else None,
        "files_saved": [p.name for p in out_dir.iterdir()],
    }
    if meta_files:
        try:
            meta = json.loads(meta_files[0].read_text())
            m = meta[0] if isinstance(meta, list) and meta else meta
            summary["model_version"] = m.get("latestVersion") or m.get("modelCreatedDate")
            summary["mean_pLDDT_global"] = m.get("globalMetricValue")
            summary["entity_description"] = m.get("uniprotDescription")
            summary["organism"] = m.get("organismScientificName")
        except Exception as e:
            summary["meta_parse_error"] = str(e)
    return _trim_json(summary)


def alphafold_analyze_plddt(uniprot_accession: str) -> str:
    """Compute per-residue pLDDT confidence summary for an already-fetched structure."""
    _receipt("AlphaFold DB", f"analyze pLDDT {uniprot_accession}")
    out_dir = OUTPUT_ROOT / "structures" / uniprot_accession
    metas = list(out_dir.glob("*metadata.json"))
    if not metas:
        return f"ERROR: no metadata.json found for {uniprot_accession} in {out_dir}. Call alphafold_fetch_structure first."
    out = _run(
        "alphafold_database_fetch_and_analyze",
        "analyze_plddt.py",
        [str(metas[0])],
    )
    return _trim(out, limit=3000)


# ---------- CLINVAR ----------

def clinvar_search(gene_symbol: str, clinical_significance: str = "pathogenic", retmax: int = 8) -> str:
    """Search ClinVar for variants in a gene (default: pathogenic only)."""
    query = f"{gene_symbol}[gene]"
    if clinical_significance:
        query += f" AND {clinical_significance}[clinsig]"
    _receipt("ClinVar", f"search {query} (max {retmax})")
    data = _run_to_json(
        "clinvar_database",
        "clinvar_api.py",
        ["search"],
        out_name=f"cv_{gene_symbol}.json",
        args_after_output=["--query", query, "--retmax", str(retmax)],
    )
    if isinstance(data, str):
        return data
    return _trim_json(data)


def clinvar_summary(variant_ids: list[str]) -> str:
    """Get clinical significance + phenotypes for ClinVar variant IDs."""
    if not variant_ids:
        return "ERROR: variant_ids list is empty"
    _receipt("ClinVar", f"summary for {len(variant_ids)} variant IDs")
    data = _run_to_json(
        "clinvar_database",
        "clinvar_api.py",
        ["summary"],
        out_name=f"cv_sum_{'_'.join(variant_ids[:3])}.json",
        args_after_output=["--variant_ids", *variant_ids],
    )
    if isinstance(data, str):
        return data
    return _trim_json(data)


# ---------- TOOL REGISTRY ----------

TOOL_FUNCTIONS = {
    "literature_search": literature_search,
    "opentargets_search_disease": opentargets_search_disease,
    "opentargets_associated_targets": opentargets_associated_targets,
    "opentargets_target_druggability": opentargets_target_druggability,
    "uniprot_search": uniprot_search,
    "alphafold_fetch_structure": alphafold_fetch_structure,
    "alphafold_analyze_plddt": alphafold_analyze_plddt,
    "clinvar_search": clinvar_search,
    "clinvar_summary": clinvar_summary,
}

TOOL_DECLARATIONS = [
    {
        "name": "literature_search",
        "description": "Search EuropePMC (30M+ biomedical papers, sorted newest first) for recent literature on a topic, target, or disease.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text query, e.g. 'GLP-1 receptor agonist Type 2 diabetes 2025'"},
                "max_results": {"type": "integer", "description": "Default 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "opentargets_search_disease",
        "description": "Resolve a disease name to its EFO/MONDO id. ALWAYS call this first when given a disease name.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Disease name, e.g. 'type 2 diabetes'"}},
            "required": ["query"],
        },
    },
    {
        "name": "opentargets_associated_targets",
        "description": "Get the top genes/proteins associated with a disease, ranked by Open Targets overall score (genetics + literature + drugs + RNA expression).",
        "parameters": {
            "type": "object",
            "properties": {
                "efo_id": {"type": "string", "description": "EFO or MONDO id from opentargets_search_disease"},
                "limit": {"type": "integer", "description": "Number of top targets (default 10)"},
            },
            "required": ["efo_id"],
        },
    },
    {
        "name": "opentargets_target_druggability",
        "description": "Assess tractability of a target: small molecule, antibody, PROTAC, other modalities, plus safety liabilities.",
        "parameters": {
            "type": "object",
            "properties": {"ensembl_id": {"type": "string", "description": "Ensembl gene id, e.g. ENSG00000187486"}},
            "required": ["ensembl_id"],
        },
    },
    {
        "name": "uniprot_search",
        "description": "Search UniProt for a protein. Use field-prefixed queries for precision.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "e.g. 'gene:KCNJ11 AND organism_id:9606 AND reviewed:true'"},
                "limit": {"type": "integer", "description": "Default 3"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "alphafold_fetch_structure",
        "description": "Download AlphaFold structure (CIF + PAE) for a UniProt accession and return mean pLDDT + metadata.",
        "parameters": {
            "type": "object",
            "properties": {"uniprot_accession": {"type": "string"}},
            "required": ["uniprot_accession"],
        },
    },
    {
        "name": "alphafold_analyze_plddt",
        "description": "Analyze per-residue pLDDT confidence for an already-fetched AlphaFold structure.",
        "parameters": {
            "type": "object",
            "properties": {"uniprot_accession": {"type": "string"}},
            "required": ["uniprot_accession"],
        },
    },
    {
        "name": "clinvar_search",
        "description": "Search ClinVar for clinical variants in a gene (default: pathogenic only). Returns variant IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "gene_symbol": {"type": "string", "description": "HGNC symbol, e.g. KCNJ11"},
                "clinical_significance": {"type": "string", "description": "e.g. 'pathogenic', 'likely_pathogenic', or '' for any"},
                "retmax": {"type": "integer", "description": "Max variant IDs (default 8)"},
            },
            "required": ["gene_symbol"],
        },
    },
    {
        "name": "clinvar_summary",
        "description": "Get clinical significance + phenotypes for specific ClinVar variant IDs (from clinvar_search).",
        "parameters": {
            "type": "object",
            "properties": {"variant_ids": {"type": "array", "items": {"type": "string"}, "description": "List of variant IDs"}},
            "required": ["variant_ids"],
        },
    },
]
