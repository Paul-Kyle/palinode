import click
from palinode.cli._api import api_client
from palinode.cli._format import console, print_result, get_default_format

@click.command()
@click.argument("file_path")
@click.option("--search", help="Filter to matching lines")
def blame(file_path, search):
    """Show when lines were changed."""
    try:
        data = api_client.blame(file_path, search)
        console.print(data)
    except Exception as e:
        console.print(f"[red]Error blaming: {str(e)}[/red]")

@click.command()
@click.argument("file_path")
@click.option("--limit", type=int, default=20, help="Max commits to show")
def history(file_path, limit):
    """Show file change history with diff stats."""
    try:
        data = api_client.get_history(file_path, limit)
        print_result(data, fmt=get_default_format())
    except Exception as e:
        console.print(f"[red]Error showing history: {str(e)}[/red]")

@click.command()
@click.argument("file_path")
@click.argument("commit", required=False)
@click.option(
    "--dry-run/--no-dry-run",
    "dry_run",
    default=True,
    help="Preview the change without applying.  Default: --dry-run.",
)
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help=(
        "Deprecated alias for --no-dry-run (ADR-010 / #164).  Will be "
        "removed in a future release."
    ),
)
def rollback(file_path, commit, dry_run, execute):
    """Revert a file to a previous commit.

    By default this is a dry run — pass ``--no-dry-run`` to actually
    apply the rollback.  ``COMMIT`` is optional; when omitted, rolls
    back to the immediately previous version.
    """
    # ADR-010 / #164: --execute is a deprecated alias for --no-dry-run.
    # The Click pair --dry-run/--no-dry-run is the canonical convention
    # matching MCP and API.
    if execute:
        click.echo(
            "warning: --execute is deprecated; use --no-dry-run instead.",
            err=True,
        )
        dry_run = False
    try:
        data = api_client.rollback(file_path, commit, dry_run=dry_run)
        console.print(data)
    except Exception as e:
        console.print(f"[red]Error rolling back: {str(e)}[/red]")

@click.command()
def push():
    """Sync to GitHub."""
    try:
        data = api_client.push()
        console.print(data)
    except Exception as e:
        console.print(f"[red]Error pushing: {str(e)}[/red]")
