"""`palinode import --from-vault` — import an existing Obsidian vault into palinode.

Walks the source vault, maps each .md file to a palinode category, rewrites
wikilinks to point at the new slugged paths, adds palinode frontmatter, and
optionally writes the result to memory_dir.

Default is a DRY RUN — pass --apply to write files.

Examples::

    # Preview what would be imported:
    palinode import --from-vault ~/my-old-vault

    # Actually import, putting everything into projects/:
    palinode import --from-vault ~/my-old-vault --into-category projects/ --apply

    # Re-run and overwrite previously imported files:
    palinode import --from-vault ~/my-old-vault --apply --overwrite
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import click

from palinode.core.config import config


@click.group("import")
def import_cmd() -> None:
    """Import content from external sources into the palinode memory store."""


@import_cmd.command("from-vault")
@click.option(
    "--from-vault",
    "source_vault",
    required=True,
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help="Source Obsidian vault directory to import from.",
)
@click.option(
    "--into-category",
    "into_category",
    default=None,
    metavar="CATEGORY/",
    help=(
        "Override: map ALL imported files into this category "
        "(e.g. --into-category archive/). "
        "When omitted, category is inferred from PARA directory structure, "
        "daily-note filename pattern, or frontmatter type: field."
    ),
)
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Write files to memory_dir. Omit for a dry-run (default).",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Replace existing files at the destination path. Default: skip with warning.",
)
def from_vault(
    source_vault: str,
    into_category: Optional[str],
    apply: bool,
    overwrite: bool,
) -> None:
    """Import .md files from an Obsidian vault into the palinode memory store.

    Walks SOURCE_VAULT for .md files, skipping .obsidian/, .trash/, and
    hidden directories. For each file:

    \b
    - Infers category (PARA dir, daily-note pattern, frontmatter type, or archive)
    - Maps source path to memory_dir/<category>/<slugified-path>.md
    - Rewrites [[wikilinks]] to point at the new slugged destination names
    - Adds palinode frontmatter (id, category, created_at, last_updated,
      source: "vault-import") without overwriting existing frontmatter

    Default is a DRY RUN. Pass --apply to actually write files.
    Orphaned wikilinks (targets not in the import set) are left as-is and
    reported; run `palinode orphan-repair` after import to fix them.
    """
    # Resolve memory_dir from env or config
    memory_dir_str = os.environ.get("PALINODE_DIR", config.memory_dir)
    memory_dir = Path(os.path.expanduser(memory_dir_str))

    if not memory_dir.exists():
        click.echo(
            f"Error: memory_dir does not exist: {memory_dir}",
            err=True,
        )
        sys.exit(1)

    source_path = Path(source_vault)
    into_cat = into_category.rstrip("/") if into_category else None

    from palinode.import_.vault import plan_import, execute_import

    click.echo(f"Scanning vault: {source_path}")
    click.echo(f"Target memory_dir: {memory_dir}")
    if into_cat:
        click.echo(f"Category override: {into_cat}/")
    if not apply:
        click.echo("[dry-run] Pass --apply to write files.")
    click.echo("")

    plans, orphan_warnings = plan_import(
        source_vault=source_path,
        memory_dir=memory_dir,
        into_category=into_cat,
    )

    if not plans:
        click.echo("0 .md files found in vault. Nothing to import.")
        return

    # Print plan
    for plan in plans:
        dest_rel = plan.dest_path.relative_to(memory_dir) if plan.dest_path.is_relative_to(memory_dir) else plan.dest_path
        src_rel = plan.source_path.relative_to(source_path) if plan.source_path.is_relative_to(source_path) else plan.source_path
        status = ""
        if plan.dest_exists:
            status = " [EXISTS]" + ("" if overwrite else " — would skip")
        click.echo(
            f"  {src_rel}  →  {dest_rel}  "
            f"[{plan.category}: {plan.category_reason}]{status}"
        )

    click.echo("")

    if orphan_warnings:
        click.echo(f"Orphaned wikilinks ({len(orphan_warnings)}) — left as-is:")
        for warn in orphan_warnings:
            click.echo(f"  warning: {warn}")
        click.echo(
            "  Tip: run `palinode orphan-repair` after import to fix unresolved links."
        )
        click.echo("")

    if not apply:
        click.echo(
            f"[dry-run] {len(plans)} file(s) would be imported. "
            "Pass --apply to write."
        )
        return

    result = execute_import(plans, overwrite=overwrite)

    if result.written:
        click.echo(f"Written ({len(result.written)}):")
        for p in result.written:
            rel = p.relative_to(memory_dir) if p.is_relative_to(memory_dir) else p
            click.echo(f"  + {rel}")

    if result.skipped:
        click.echo(f"Skipped ({len(result.skipped)}):")
        for p, reason in result.skipped:
            rel = p.relative_to(memory_dir) if p.is_relative_to(memory_dir) else p
            click.echo(f"  · {rel}: {reason}")

    if result.errors:
        click.echo(f"Errors ({len(result.errors)}):", err=True)
        for p, reason in result.errors:
            rel = p.relative_to(memory_dir) if p.is_relative_to(memory_dir) else p
            click.echo(f"  ! {rel}: {reason}", err=True)

    click.echo("")
    click.echo(
        f"Import complete: {len(result.written)} written, "
        f"{len(result.skipped)} skipped, "
        f"{len(result.errors)} error(s)."
    )

    if result.errors:
        sys.exit(1)
