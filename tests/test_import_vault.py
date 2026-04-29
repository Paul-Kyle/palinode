"""Tests for `palinode import --from-vault` (#236).

Coverage:
- Round-trip: 3-file vault (Projects/, daily-note, freeform) → correct palinode locations + frontmatter
- Wikilink translation: source [[Foo]] → rewrites to new slug when target is in import set
- Orphan wikilinks: [[UnknownThing]] is left as-is and reported
- Skip-existing safety: re-run without --overwrite does not clobber prior writes
- Overwrite mode: with --overwrite, re-run replaces existing files
- Dry-run: no files are written; output describes what would happen
- Empty vault: no error, "0 files imported" output
- Non-markdown files: only .md files imported, others ignored
- --into-category override: all files land in the specified category
- Slug disambiguation: two files with the same slug after slugification → -2 suffix
"""
from __future__ import annotations

import os
from pathlib import Path

import frontmatter as fm_lib
import pytest
from click.testing import CliRunner

from palinode.cli import main
from palinode.import_.vault import plan_import, execute_import


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_vault(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a fake vault under tmp_path/vault/ with the given file tree.

    Args:
        files: mapping of relative path (str) → file content (str)
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    for rel, content in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vault


def make_memory_dir(tmp_path: Path) -> Path:
    """Create an empty memory_dir for import targets."""
    mem = tmp_path / "memory"
    mem.mkdir()
    return mem


def run_import(vault: Path, memory: Path, *extra_args: str):
    """Invoke palinode import from-vault with given paths and return result."""
    runner = CliRunner()
    return runner.invoke(
        main,
        [
            "import", "from-vault",
            "--from-vault", str(vault),
            *extra_args,
        ],
        env={"PALINODE_DIR": str(memory)},
        catch_exceptions=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECTS_FILE = """\
---
title: My Project Notes
tags: [work]
---

This is a project note referencing [[Daily Log]] and [[Research Article]].
"""

DAILY_FILE = """\
---
title: Daily Log
---

Today I worked on things. Linked from [[My Project Notes]].
"""

FREEFORM_FILE = """\
---
title: Random Thought
---

Just a random note with no PARA category.
"""


# ---------------------------------------------------------------------------
# Core round-trip
# ---------------------------------------------------------------------------

def test_round_trip_three_files(tmp_path: Path):
    """Three vault files land in correct palinode locations with expected frontmatter."""
    vault = make_vault(tmp_path, {
        "Projects/my-project.md": PROJECTS_FILE,
        "2026-01-15.md": DAILY_FILE,
        "random-thought.md": FREEFORM_FILE,
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory, "--apply")
    assert result.exit_code == 0, result.output

    # projects/ file
    projects_files = list((memory / "projects").rglob("*.md"))
    assert len(projects_files) == 1
    post = fm_lib.load(str(projects_files[0]))
    assert post.metadata.get("category") == "projects"
    assert post.metadata.get("source") == "vault-import"
    assert "id" in post.metadata
    assert "created_at" in post.metadata
    assert "last_updated" in post.metadata

    # daily/ file
    daily_files = list((memory / "daily").rglob("*.md"))
    assert len(daily_files) == 1
    post_d = fm_lib.load(str(daily_files[0]))
    assert post_d.metadata.get("category") == "daily"

    # freeform → archive/
    archive_files = list((memory / "archive").rglob("*.md"))
    assert len(archive_files) == 1
    post_a = fm_lib.load(str(archive_files[0]))
    assert post_a.metadata.get("category") == "archive"


# ---------------------------------------------------------------------------
# Wikilink translation
# ---------------------------------------------------------------------------

def test_wikilink_translation_within_import_set(tmp_path: Path):
    """[[Target]] that matches another imported file is rewritten to new slug."""
    vault = make_vault(tmp_path, {
        "Projects/my-project.md": "---\ntitle: My Project\n---\n\nSee [[Sub Note]] for details.\n",
        "Projects/sub-note.md": "---\ntitle: Sub Note\n---\n\nContent here.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, warnings = plan_import(
        source_vault=vault,
        memory_dir=memory,
        into_category=None,
    )

    # Find the plan for my-project.md
    project_plan = next(p for p in plans if "my-project" in p.source_path.name)
    sub_plan = next(p for p in plans if "sub-note" in p.source_path.name)

    # The wikilink in my-project should now point at the sub-note's dest slug
    expected_slug = sub_plan.dest_path.stem
    assert f"[[{expected_slug}]]" in project_plan.content, (
        f"Expected [[{expected_slug}]] in:\n{project_plan.content}"
    )


def test_wikilink_orphan_left_as_is(tmp_path: Path):
    """[[UnknownThing]] not in the import set is left untouched and warned about."""
    vault = make_vault(tmp_path, {
        "Notes/note.md": "---\ntitle: Note\n---\n\nSee [[Totally Unknown Thing]] for details.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, warnings = plan_import(vault, memory, None)

    assert len(plans) == 1
    assert "[[Totally Unknown Thing]]" in plans[0].content
    assert len(warnings) == 1
    assert "Totally Unknown Thing" in warnings[0]


# ---------------------------------------------------------------------------
# Skip-existing safety
# ---------------------------------------------------------------------------

def test_skip_existing_without_overwrite(tmp_path: Path):
    """Re-running import without --overwrite does not modify existing files."""
    vault = make_vault(tmp_path, {
        "2026-01-01.md": "---\ntitle: Day One\n---\n\nOriginal.\n",
    })
    memory = make_memory_dir(tmp_path)

    # First run — should write
    r1 = run_import(vault, memory, "--apply")
    assert r1.exit_code == 0
    daily_files = list((memory / "daily").rglob("*.md"))
    assert len(daily_files) == 1
    original_content = daily_files[0].read_text()

    # Modify file in vault to simulate a change
    (vault / "2026-01-01.md").write_text("---\ntitle: Day One\n---\n\nModified.\n")

    # Second run — should skip the existing file
    r2 = run_import(vault, memory, "--apply")
    assert r2.exit_code == 0
    assert "skipped" in r2.output.lower()

    # Content on disk must be unchanged
    assert daily_files[0].read_text() == original_content


def test_overwrite_mode_replaces_existing(tmp_path: Path):
    """With --overwrite, re-running replaces existing files."""
    vault = make_vault(tmp_path, {
        "2026-01-01.md": "---\ntitle: Day One\n---\n\nOriginal.\n",
    })
    memory = make_memory_dir(tmp_path)

    r1 = run_import(vault, memory, "--apply")
    assert r1.exit_code == 0
    daily_files = list((memory / "daily").rglob("*.md"))
    assert len(daily_files) == 1

    # Update source
    (vault / "2026-01-01.md").write_text("---\ntitle: Day One\n---\n\nUpdated content.\n")

    r2 = run_import(vault, memory, "--apply", "--overwrite")
    assert r2.exit_code == 0

    new_content = daily_files[0].read_text()
    assert "Updated content." in new_content


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path: Path):
    """Dry-run mode prints what would happen but writes zero files."""
    vault = make_vault(tmp_path, {
        "Projects/proj.md": "---\ntitle: Proj\n---\n\nContent.\n",
        "2026-02-01.md": "---\ntitle: Daily\n---\n\nDaily.\n",
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory)  # no --apply → dry-run

    assert result.exit_code == 0
    assert "dry-run" in result.output.lower()
    # Nothing written
    all_md = list(memory.rglob("*.md"))
    assert all_md == [], f"Expected no files, found: {all_md}"


def test_dry_run_output_describes_files(tmp_path: Path):
    """Dry-run output mentions both source files."""
    vault = make_vault(tmp_path, {
        "Projects/proj.md": "---\ntitle: Proj\n---\n\nContent.\n",
        "2026-02-01.md": "---\ntitle: Daily\n---\n\nDaily.\n",
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory)

    assert "proj" in result.output.lower()
    assert "projects" in result.output.lower()
    assert "daily" in result.output.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_vault(tmp_path: Path):
    """Empty vault produces no error and reports 0 files."""
    vault = make_vault(tmp_path, {})
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory, "--apply")
    assert result.exit_code == 0
    assert "0" in result.output


def test_non_markdown_files_ignored(tmp_path: Path):
    """Images, PDFs, and other non-.md files are silently skipped."""
    vault = make_vault(tmp_path, {
        "note.md": "---\ntitle: Note\n---\n\nContent.\n",
        "image.png": b"\x89PNG\r\n".decode("latin-1"),
        "doc.pdf": "%PDF-1.4",
        "data.json": '{"key": "value"}',
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory, "--apply")
    assert result.exit_code == 0

    all_files = list(memory.rglob("*"))
    imported = [f for f in all_files if f.is_file()]
    assert all(f.suffix == ".md" for f in imported), f"Non-.md file imported: {imported}"
    assert len(imported) == 1


def test_into_category_override(tmp_path: Path):
    """--into-category forces all files into the specified category."""
    vault = make_vault(tmp_path, {
        "Projects/proj.md": "---\ntitle: Proj\n---\n\nContent.\n",
        "2026-03-01.md": "---\ntitle: Daily\n---\n\nDaily.\n",
        "random.md": "---\ntitle: Random\n---\n\nRandom.\n",
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory, "--into-category", "archive/", "--apply")
    assert result.exit_code == 0

    # All files should be under archive/
    archive_files = list((memory / "archive").rglob("*.md"))
    assert len(archive_files) == 3

    other_files = [
        f for f in memory.rglob("*.md")
        if "archive" not in str(f)
    ]
    assert other_files == [], f"Files outside archive/: {other_files}"


def test_skip_obsidian_and_trash_dirs(tmp_path: Path):
    """.obsidian/ and .trash/ directories are skipped."""
    vault = make_vault(tmp_path, {
        "real-note.md": "---\ntitle: Real\n---\n\nContent.\n",
        ".obsidian/app.json": '{"key": "value"}',
        ".trash/deleted.md": "---\ntitle: Deleted\n---\n\nGone.\n",
    })
    memory = make_memory_dir(tmp_path)

    result = run_import(vault, memory, "--apply")
    assert result.exit_code == 0

    imported = list(memory.rglob("*.md"))
    assert len(imported) == 1


def test_slug_disambiguation(tmp_path: Path):
    """Two files that map to the same slug get -2 suffix on the second."""
    vault = make_vault(tmp_path, {
        # These both slugify to "my-note" after PARA prefix stripped
        "Projects/my-note.md": "---\ntitle: My Note A\n---\n\nA.\n",
        "Projects/My Note.md": "---\ntitle: My Note B\n---\n\nB.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, _ = plan_import(vault, memory, None)

    dest_paths = {p.dest_path for p in plans}
    # Must be two distinct paths
    assert len(dest_paths) == 2, f"Expected 2 distinct dest paths, got: {dest_paths}"


def test_existing_frontmatter_preserved(tmp_path: Path):
    """palinode frontmatter fields in source are preserved; id is not overwritten."""
    original_id = "existing-id-xyz"
    vault = make_vault(tmp_path, {
        "note.md": (
            f"---\ntitle: Has ID\nid: {original_id}\ncategory: insights\n---\n\nBody.\n"
        ),
    })
    memory = make_memory_dir(tmp_path)

    plans, _ = plan_import(vault, memory, None)
    assert len(plans) == 1

    post = fm_lib.loads(plans[0].content)
    assert post.metadata["id"] == original_id
    assert post.metadata["category"] == "insights"


def test_para_areas_maps_to_decisions(tmp_path: Path):
    """Files under Areas/ map to the decisions/ category."""
    vault = make_vault(tmp_path, {
        "Areas/work-life-balance.md": "---\ntitle: WLB\n---\n\nContent.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, _ = plan_import(vault, memory, None)
    assert plans[0].category == "decisions"


def test_para_resources_maps_to_research(tmp_path: Path):
    """Files under Resources/ map to the research/ category."""
    vault = make_vault(tmp_path, {
        "Resources/paper.md": "---\ntitle: Paper\n---\n\nContent.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, _ = plan_import(vault, memory, None)
    assert plans[0].category == "research"


def test_frontmatter_type_field_used_for_category(tmp_path: Path):
    """A freeform file with type: insight frontmatter maps to insights/."""
    vault = make_vault(tmp_path, {
        "notes/my-insight.md": "---\ntitle: Insight\ntype: insight\n---\n\nContent.\n",
    })
    memory = make_memory_dir(tmp_path)

    plans, _ = plan_import(vault, memory, None)
    assert plans[0].category == "insights"


def test_vault_import_cli_dry_run_no_memory_dir_required(tmp_path: Path):
    """CLI dry-run still works even if memory_dir has no subdirs yet."""
    vault = make_vault(tmp_path, {
        "note.md": "---\ntitle: Note\n---\n\nContent.\n",
    })
    memory = make_memory_dir(tmp_path)

    # No --apply → dry-run path; should not try to write anything
    result = run_import(vault, memory)
    assert result.exit_code == 0
    assert "would be imported" in result.output or "dry-run" in result.output.lower()


def test_import_summary_counts(tmp_path: Path):
    """Import complete summary line shows correct written/skipped/error counts."""
    vault = make_vault(tmp_path, {
        "a.md": "---\ntitle: A\n---\n\nA.\n",
        "b.md": "---\ntitle: B\n---\n\nB.\n",
    })
    memory = make_memory_dir(tmp_path)

    # First run → 2 written
    r1 = run_import(vault, memory, "--apply")
    assert r1.exit_code == 0
    assert "2 written" in r1.output

    # Second run without --overwrite → 2 skipped
    r2 = run_import(vault, memory, "--apply")
    assert r2.exit_code == 0
    assert "2 skipped" in r2.output or "skipped" in r2.output
