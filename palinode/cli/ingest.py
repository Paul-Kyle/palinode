import click
import httpx
from palinode.core.config import config
from palinode.cli._format import console, print_result, get_default_format, OutputFormat


@click.command()
@click.option("--url", help="URL to fetch and save as a research reference")
@click.option("--name", help="Optional title for the reference")
@click.option("--inbox", is_flag=True, help="Process files in the inbox directory")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]))
def ingest(url, name, inbox, fmt):
    """Ingest a URL or process the inbox directory."""
    if not url and not inbox:
        raise click.UsageError("Provide --url <URL> or --inbox")

    api_port = config.services.api.port
    output_fmt = OutputFormat(fmt) if fmt else get_default_format()

    try:
        if inbox:
            resp = httpx.post(f"http://127.0.0.1:{api_port}/ingest", timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
            if output_fmt == OutputFormat.JSON:
                print_result(data, fmt=output_fmt)
            else:
                console.print("[green]✓[/green] Inbox processed.")
        else:
            payload = {"url": url}
            if name:
                payload["name"] = name
            resp = httpx.post(
                f"http://127.0.0.1:{api_port}/ingest-url",
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if output_fmt == OutputFormat.JSON:
                print_result(data, fmt=output_fmt)
            else:
                if data.get("status") == "success":
                    console.print(f"[green]✓[/green] Saved to {data.get('file_path', 'research/')}")
                else:
                    console.print("[yellow]No content extracted from URL.[/yellow]")
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        console.print(f"[red]Error:[/red] {detail or e.response.status_code}")
    except httpx.RequestError as e:
        console.print(f"[red]Error:[/red] Cannot reach API — is palinode running? ({e})")
