"""
Palinode Consolidation Cron Entry Point

Three-tier memory freshness:
  Tier 1: Session append (hook/MCP, every session, free — captures intent + result)
  Tier 2: Nightly dedup (--nightly, UPDATE/SUPERSEDE only, 1-day lookback)
  Tier 3: Weekly deep clean (full ops, 3-7 day lookback)

Crontab examples (times in UTC, target 4am PT = 11:00 UTC during PDT):
    # Nightly — lightweight dedup of today's sessions
    0 11 * * * cd /path/to/palinode && PALINODE_DIR=~/.palinode venv/bin/python -m palinode.consolidation.cron --nightly --days 1

    # Weekly — full compaction with MERGE/ARCHIVE
    0 11 * * 0 cd /path/to/palinode && PALINODE_DIR=~/.palinode venv/bin/python -m palinode.consolidation.cron --days 3
"""
from __future__ import annotations

import logging
import sys

from palinode.core.config import config
from palinode.consolidation.runner import run_consolidation, run_nightly

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("palinode.consolidation.cron")


def main() -> None:
    if not config.consolidation.enabled:
        logger.info("Consolidation is disabled in config. Exiting.")
        sys.exit(0)

    nightly = "--nightly" in sys.argv

    # Parse --days N for custom lookback (default: config value)
    lookback = None
    if "--days" in sys.argv:
        try:
            idx = sys.argv.index("--days")
            lookback = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            pass

    mode = "nightly" if nightly else "weekly"
    logger.info(f"Starting {mode} consolidation (lookback: {lookback or 'config default'} days)...")

    if nightly:
        result = run_nightly(lookback_days=lookback)
    else:
        result = run_consolidation(lookback_days=lookback)

    logger.info(f"Consolidation complete: {result}")


if __name__ == "__main__":
    main()
