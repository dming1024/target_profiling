import logging
from datetime import datetime
from pathlib import Path

import typer

from target_profile import __version__
from target_profile.analysis.basic import analyze_basic
from target_profile.analysis.cancer import analyze_cancer
from target_profile.analysis.comparative import analyze_comparative
from target_profile.analysis.dependency import analyze_dependency
from target_profile.analysis.disease import analyze_disease
from target_profile.analysis.expression import analyze_expression
from target_profile.analysis.mutation import analyze_mutation
from target_profile.analysis.pathway import analyze_pathway
from target_profile.analysis.ptm import analyze_ptm
from target_profile.analysis.safety import analyze_safety
from target_profile.analysis.summary import build_summary
from target_profile.analysis.tractability import analyze_tractability
from target_profile.api.alphafold import alphafold_confidence, alphafold_prediction
from target_profile.api.clinvar import fetch_clinvar
from target_profile.api.opentargets import (
    target_basic,
    target_cancer,
    target_details,
    target_disease,
    target_pathways,
    target_safety,
    target_tractability,
)
from target_profile.api.stringdb import interaction_partners
from target_profile.api.uniprot import uniprot_record
from target_profile.config import load_settings
from target_profile.data_prep.lake import DERIVERS, derive_all
from target_profile.errors import DataMissing, GeneNotFound
from target_profile.figures.chart_specs import (
    build_basic,
    build_cancer,
    build_comparative,
    build_dependency,
    build_disease,
    build_expression,
    build_mutation,
    build_pathway,
    build_ptm,
    build_safety,
    build_tractability,
)
from target_profile.gene_resolve import resolve_gene
from target_profile.llm import build_narratives
from target_profile.models import ModuleResult
from target_profile.report.pdf import html_to_pdf
from target_profile.report.render import render_print_report, render_report

app = typer.Typer(no_args_is_help=True, help="Single-gene target profiling")

MODULES = [
    analyze_basic,
    analyze_disease,
    analyze_expression,
    analyze_mutation,
    analyze_dependency,
    analyze_pathway,
    analyze_ptm,
    analyze_tractability,
    analyze_safety,
]

BUILDERS = {
    "basic": build_basic,
    "expression": build_expression,
    "mutation": build_mutation,
    "dependency": build_dependency,
    "pathway": build_pathway,
    "ptm": build_ptm,
    "disease": build_disease,
    "tractability": build_tractability,
    "safety": build_safety,
    "cancer": build_cancer,
    "comparative": build_comparative,
}


def _configure_logging(log_path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


@app.command()
def version() -> None:
    """Show version."""
    typer.echo(f"target-profile {__version__}")


@app.command()
def data(
    source: str = typer.Argument("all", help="all or a source name"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Derive compact parquet files from the local Biomni data lake."""
    settings = load_settings()
    if source != "all" and source not in DERIVERS:
        typer.echo(f"unknown source: {source}; choose from {', '.join(DERIVERS)}", err=True)
        raise typer.Exit(code=2)
    try:
        entries = derive_all(settings) if source == "all" else [DERIVERS[source](settings)]
    except FileNotFoundError as exc:
        typer.echo(f"missing lake file: {exc}", err=True)
        raise typer.Exit(code=3)
    for entry in entries:
        typer.echo(f"{entry.name}: {entry.rows} rows -> {entry.path}")


@app.command()
def fetch(
    gene: str = typer.Argument(..., help="Gene symbol, alias, Ensembl or UniProt ID"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Warm the per-gene API cache."""
    settings = load_settings()
    try:
        ctx = resolve_gene(gene, settings, offline=False)
    except GeneNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    from target_profile.api.cache import CachedFetcher
    from target_profile.api.cbioportal import fetch_pancan_mutations

    fetcher = CachedFetcher(settings.data_root / "cache", offline=False)
    steps = [
        ("Open Targets target", lambda: target_details(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets basic", lambda: target_basic(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets pathways", lambda: target_pathways(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets disease", lambda: target_disease(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets tractability", lambda: target_tractability(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets safety", lambda: target_safety(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets cancer", lambda: target_cancer(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("STRING partners", lambda: interaction_partners(ctx.symbol, fetcher, refresh=refresh)),
    ]
    if ctx.uniprot_id:
        steps.append(("UniProt record", lambda: uniprot_record(ctx.uniprot_id, fetcher, refresh=refresh)))
        steps.append(("AlphaFold prediction", lambda: alphafold_prediction(ctx.uniprot_id, fetcher, refresh=refresh)))

        def _fetch_alphafold_confidence() -> object:
            prediction = alphafold_prediction(ctx.uniprot_id, fetcher, refresh=refresh)
            return alphafold_confidence(
                ctx.uniprot_id, prediction, fetcher, refresh=refresh
            )

        steps.append(("AlphaFold confidence", _fetch_alphafold_confidence))
    if ctx.entrez_id:
        steps.append(
            (
                "cBioPortal TCGA mutations",
                lambda: fetch_pancan_mutations(ctx.symbol, ctx.entrez_id, fetcher, refresh=refresh),
            )
        )
    steps.append(("ClinVar records", lambda: fetch_clinvar(ctx.symbol, fetcher, refresh=refresh)))
    for label, action in steps:
        try:
            action()
            typer.echo(f"cached: {label}")
        except Exception as exc:
            typer.echo(f"warning: {label} failed: {exc}", err=True)
    typer.echo(f"cached gene: {ctx.symbol}")


@app.command()
def doctor() -> None:
    """Check environment and data availability."""
    settings = load_settings()
    ok = True
    typer.echo(f"lake_root: {settings.lake_root}")
    typer.echo(f"data_root: {settings.data_root}")
    for name in DERIVERS:
        path = settings.data_root / "parquet" / f"{name}.parquet"
        exists = path.exists()
        ok = ok and exists
        typer.echo(f"{'OK ' if exists else 'MISS'} {path}")
    try:
        import playwright  # noqa: F401

        typer.echo("OK  playwright")
    except Exception:
        typer.echo("MISS playwright (PDF disabled; HTML still works)")
    raise typer.Exit(code=0 if ok else 1)


def _run_analyzer(analyzer, ctx, settings, offline, **kwargs) -> ModuleResult:
    name = getattr(analyzer, "__name__", "module").replace("analyze_", "")
    try:
        return analyzer(ctx, settings, offline=offline, **kwargs)
    except DataMissing:
        raise
    except Exception as exc:
        logging.exception("module %s failed", name)
        return ModuleResult(name=name).degrade(f"{name}: internal error ({exc})")


@app.command()
def run(
    gene: str = typer.Argument(..., help="Gene symbol, alias, Ensembl or UniProt ID"),
    out: Path | None = typer.Option(None, "--out", help="Output directory"),
    format: str = typer.Option("html", "--format", help="html|pdf|both"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM polishing"),
    force: bool = typer.Option(False, "--force", help="Overwrite output directory"),
    offline: bool = typer.Option(False, "--offline", help="Forbid network access"),
) -> None:
    """Generate a single-gene profiling report."""
    if format not in {"html", "pdf", "both"}:
        typer.echo(f"invalid --format: {format}; choose html|pdf|both", err=True)
        raise typer.Exit(code=2)
    settings = load_settings()
    try:
        ctx = resolve_gene(gene, settings, offline=offline)
    except GeneNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    except DataMissing as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3)

    out_dir = out or settings.out_root / f"{ctx.symbol}_{datetime.now():%Y%m%d}"
    if out_dir.exists() and not force:
        typer.echo(f"output exists: {out_dir}; use --force", err=True)
        raise typer.Exit(code=2)
    out_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(out_dir / "run.log")

    modules = [_run_analyzer(analyzer, ctx, settings, offline) for analyzer in MODULES]
    by_name = {module.name: module for module in modules}

    for analyzer in (analyze_cancer, analyze_comparative):
        result = _run_analyzer(analyzer, ctx, settings, offline, prior=by_name)
        modules.append(result)
        by_name[result.name] = result

    modules.append(build_summary(modules, settings))

    for module in modules:
        module.facts.setdefault("symbol", ctx.symbol)
        builder = BUILDERS.get(module.name)
        if builder and module.status == "ok":
            try:
                module.charts = builder(module)
            except Exception as exc:
                logging.warning("charts %s failed: %s", module.name, exc)

    llm_info = build_narratives(ctx.symbol, modules, settings, enabled=not no_llm)

    html_path, facts_path = render_report(ctx, modules, out_dir, llm_info=llm_info)
    logging.info("wrote %s", html_path)
    logging.info("wrote %s", facts_path)

    if format in {"both", "pdf"}:
        pdf_path = out_dir / "report.pdf"
        print_path = render_print_report(ctx, modules, out_dir, llm_info=llm_info)
        try:
            ok = html_to_pdf(print_path, pdf_path)
        finally:
            print_path.unlink(missing_ok=True)
        if not ok:
            typer.echo("PDF export failed; HTML retained", err=True)
            raise typer.Exit(code=4)

    typer.echo(f"report: {html_path}")
    if format in {"both", "pdf"}:
        typer.echo(f"pdf: {out_dir / 'report.pdf'}")
