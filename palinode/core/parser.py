"""
Palinode Markdown Parse Utilities
"""
from __future__ import annotations

import logging
import os
import frontmatter
import re
from typing import Any


logger = logging.getLogger("palinode.parser")

# ADR-009 §3.3: allowed values for the `visibility` frontmatter field.
VALID_VISIBILITIES: tuple[str, ...] = ("inherited", "private", "restricted")
DEFAULT_VISIBILITY: str = "inherited"


def slugify(text: str) -> str:
    """Converts a standard text string to a URL-safe lowercase slug.

    Args:
        text (str): The raw section header or file title.

    Returns:
        str: The generated URL-safe slug stripped of special characters.
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def _build_canonical_question_prefix(metadata: dict[str, Any]) -> str:
    """Build a text prefix from canonical_question frontmatter.

    Accepts a single string or a list of strings.  Returns a formatted
    prefix like ``"Q: …\\n\\n"`` ready to be prepended to chunk content,
    or an empty string if the field is absent.
    """
    cq = metadata.get("canonical_question")
    if not cq:
        return ""

    if isinstance(cq, str):
        questions = [cq]
    elif isinstance(cq, list):
        questions = [str(q) for q in cq if q]
    else:
        return ""

    if not questions:
        return ""

    lines = [f"Q: {q}" for q in questions]
    return "\n".join(lines) + "\n\n"


def parse_markdown(content: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Parses a complete markdown string payload containing YAML frontmatter.

    Automatically handles text segmentation. If the markdown document is 
    extremely short, it will remain categorized natively as a single "root" chunk.
    Larger documents are contextually broken apart via H2 (##) or H3 (###) headers.

    Args:
        content (str): Complete file content string including frontmatter and markdown body.

    Returns:
        tuple: A nested pair containing:
            - metadata (dict[str, Any]): Loaded YAML variables extracted via 'python-frontmatter'.
            - sections (list[dict[str, str]]): Document subdivided portions comprising `section_id` 
              and their relative `content`.
    """
    try:
        post = frontmatter.loads(content)
        metadata = post.metadata
        body = post.content
    except Exception:
        metadata = {}
        body = content

    # Build canonical question prefix from frontmatter (string or list of strings).
    cq_prefix = _build_canonical_question_prefix(metadata)

    # If document is short (~500 tokens corresponds to roughly 2000 chars), keep it safely bound
    # to a single core chunk to prevent semantic fracturing.
    if len(body) < 2000:
        return metadata, [{"section_id": "root", "content": cq_prefix + body}]

    # Split by h2 or h3 natively formatted headers.
    # regex intentionally matches lines starting exclusively with ## or ###
    heading_pattern = re.compile(r'^(#{2,3})\s+(.*)$', re.MULTILINE)
    
    sections = []
    
    parts = heading_pattern.split(body)
    
    preamble = parts[0].strip()
    if preamble:
        sections.append({
            "section_id": "root",
            "content": preamble
        })
        
    for i in range(1, len(parts), 3):
        if i + 2 >= len(parts):
            break
        level = parts[i]
        heading_text = parts[i+1]
        section_content = parts[i+2]
        
        full_content = f"{level} {heading_text}\n{section_content}".strip()
        slug = slugify(heading_text)
        
        if full_content:
            sections.append({
                "section_id": slug,
                "content": full_content
            })

    # Failsafe fallback: Handle missing headers implicitly.
    if not sections:
        sections = [{"section_id": "root", "content": body}]

    # Prepend canonical question prefix to the first chunk so the
    # embedding captures the question semantics the file answers.
    if cq_prefix and sections:
        sections[0]["content"] = cq_prefix + sections[0]["content"]

    return metadata, sections


# ── ADR-009 §3.3: scope frontmatter parsing ───────────────────────────────


def _default_scope_from_path(file_path: str) -> str | None:
    """Infer a default scope entity ref from a memory file's location.

    Per ADR-009 §3.3 / §7: a memory file with no explicit ``scope`` frontmatter
    defaults to ``project/<directory>`` where ``<directory>`` is the
    immediate parent directory name (e.g. ``decisions/foo.md`` →
    ``project/decisions``). Returns ``None`` when no parent directory name
    can be determined (e.g. a bare filename or empty string), which lets the
    caller decide how to handle a path-less parse.
    """
    if not file_path:
        return None
    parent = os.path.basename(os.path.dirname(file_path))
    if not parent:
        return None
    return f"project/{parent}"


def parse_scope(
    metadata: dict[str, Any],
    file_path: str | None = None,
) -> dict[str, Any]:
    """Extract scope, visibility, and access from frontmatter (ADR-009 §3.3).

    Returns a dict with the keys ``scope`` (str | None), ``visibility``
    (str, one of :data:`VALID_VISIBILITIES`), and ``access`` (list[str]).

    Defaults:
      - ``scope``: the value of ``metadata['scope']`` if present, else the
        directory-inferred default (``project/<parent-dir>``) when
        ``file_path`` is given, else ``None``.
      - ``visibility``: ``metadata['visibility']`` if it is one of the three
        allowed strings; otherwise :data:`DEFAULT_VISIBILITY` (a warning is
        logged for invalid values, matching the parser's existing
        soft-fail style for malformed metadata).
      - ``access``: ``metadata['access']`` coerced to ``list[str]`` if it is
        a list; otherwise ``[]``. Only meaningful when
        ``visibility == "restricted"`` per ADR-009 §3.4.

    This helper is purely additive — it does not modify ``metadata`` and does
    not affect :func:`parse_markdown`'s return shape. Slice 3 will consume
    the result when wiring scope into search.
    """
    raw_scope = metadata.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        scope: str | None = raw_scope.strip()
    else:
        scope = _default_scope_from_path(file_path) if file_path else None

    raw_vis = metadata.get("visibility", DEFAULT_VISIBILITY)
    if isinstance(raw_vis, str) and raw_vis in VALID_VISIBILITIES:
        visibility = raw_vis
    else:
        if "visibility" in metadata:
            logger.warning(
                "Invalid visibility %r (expected one of %s); falling back to %r",
                raw_vis,
                VALID_VISIBILITIES,
                DEFAULT_VISIBILITY,
            )
        visibility = DEFAULT_VISIBILITY

    raw_access = metadata.get("access", [])
    if isinstance(raw_access, list):
        access = [str(a) for a in raw_access if a is not None and str(a).strip()]
    else:
        access = []

    return {"scope": scope, "visibility": visibility, "access": access}
