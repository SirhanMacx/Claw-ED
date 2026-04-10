"""BrainPage and BrainStore — markdown-backed knowledge pages.

Each page follows the compiled-truth + timeline pattern:

    ---
    type: student
    slug: julia-m
    created: 2026-04-10
    updated: 2026-04-10
    tier: 1
    ---

    # Julia M.

    ## Compiled Truth

    Strong reader, weak writer. Responds to sentence starters. IEP requires
    extended time. Best work: primary source analysis. Growth area: CRQ
    extended writing.

    ## Strengths
    - Primary source analysis
    - Oral discussion

    ## Challenges
    - Extended writing (CRQ format)

    ## Accommodations
    - Sentence starters on exit tickets
    - Extended time per IEP

    ---

    ## Timeline

    - **2026-04-09** | Exit Q3: 2/4 [Source: Lesson "Industrial Revolution"]
    - **2026-04-08** | Mock trial role [Source: Lesson "Factory Investigation"]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Valid page types
PAGE_TYPES = (
    "student", "topic", "lesson", "original", "class", "concept", "person",
)


@dataclass
class TimelineEntry:
    """A single timeline entry with source attribution."""

    date: str  # YYYY-MM-DD
    body: str  # the observation/event
    source: str = ""  # citation format: "[Source: ...]"

    def render(self) -> str:
        """Render as a markdown list item."""
        src = f" [Source: {self.source}]" if self.source else ""
        return f"- **{self.date}** | {self.body}{src}"

    @classmethod
    def parse(cls, line: str) -> Optional["TimelineEntry"]:
        """Parse a timeline line back into an entry."""
        # Format: - **YYYY-MM-DD** | body [Source: ...]
        m = re.match(
            r"^\s*-\s+\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|\s*(.+?)(?:\s+\[Source:\s*(.+?)\])?\s*$",
            line,
        )
        if not m:
            return None
        return cls(
            date=m.group(1),
            body=m.group(2).strip(),
            source=m.group(3).strip() if m.group(3) else "",
        )


@dataclass
class BrainPage:
    """A single brain page with compiled truth + timeline.

    Attributes:
        slug: URL-safe identifier (e.g. "julia-m", "industrial-revolution")
        page_type: One of PAGE_TYPES
        title: Display title
        compiled_truth: The current synthesis (multi-section markdown)
        timeline: Append-only list of evidence entries
        metadata: Front-matter dict (tier, tags, created, updated, etc.)
    """

    slug: str
    page_type: str
    title: str
    compiled_truth: str = ""
    timeline: list[TimelineEntry] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_timeline(self, body: str, source: str = "", date: str = "") -> None:
        """Append a timeline entry. Sorted reverse-chronological on save."""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        self.timeline.append(TimelineEntry(date=date, body=body, source=source))
        self.metadata["updated"] = datetime.now().strftime("%Y-%m-%d")

    def render(self) -> str:
        """Render the full markdown page."""
        lines = ["---"]
        meta = dict(self.metadata)
        meta["type"] = self.page_type
        meta["slug"] = self.slug
        if "created" not in meta:
            meta["created"] = datetime.now().strftime("%Y-%m-%d")
        if "updated" not in meta:
            meta["updated"] = datetime.now().strftime("%Y-%m-%d")
        for k, v in meta.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        # Compiled truth zone
        if self.compiled_truth.strip():
            lines.append(self.compiled_truth.strip())
        else:
            lines.append("## Compiled Truth")
            lines.append("")
            lines.append("_(empty — awaiting enrichment)_")

        # Timeline zone
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Timeline")
        lines.append("")
        # Sort timeline reverse-chronologically
        sorted_entries = sorted(
            self.timeline, key=lambda e: e.date, reverse=True,
        )
        for entry in sorted_entries:
            lines.append(entry.render())

        return "\n".join(lines) + "\n"

    @classmethod
    def parse(cls, text: str) -> "BrainPage":
        """Parse a markdown page back into a BrainPage."""
        metadata: dict = {}
        body = text

        # Parse front matter
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end > 0:
                fm = text[4:end]
                for line in fm.split("\n"):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        metadata[k.strip()] = v.strip()
                body = text[end + 5:]

        # Extract title
        title = metadata.get("slug", "untitled")
        title_m = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
        if title_m:
            title = title_m.group(1).strip()

        # Split compiled truth from timeline
        compiled = body
        timeline: list[TimelineEntry] = []
        if "## Timeline" in body:
            parts = body.rsplit("## Timeline", 1)
            compiled = parts[0].rstrip()
            # Strip trailing --- separator
            if compiled.rstrip().endswith("---"):
                compiled = compiled.rstrip()[:-3].rstrip()
            tl_section = parts[1]
            for line in tl_section.split("\n"):
                entry = TimelineEntry.parse(line)
                if entry:
                    timeline.append(entry)

        # Strip the top-level title from compiled truth
        compiled = re.sub(
            r"^#\s+.+?\n\n?", "", compiled.lstrip(), count=1, flags=re.MULTILINE,
        ).strip()

        return cls(
            slug=metadata.get("slug", "untitled"),
            page_type=metadata.get("type", "concept"),
            title=title,
            compiled_truth=compiled,
            timeline=timeline,
            metadata=metadata,
        )


class BrainStore:
    """File-system backed store for brain pages.

    Default root: ~/.eduagent/brain/

    Structure:
        brain/
          students/{slug}.md
          topics/{slug}.md
          lessons/{slug}.md
          originals/{slug}.md
          classes/{slug}.md
          concepts/{slug}.md
          people/{slug}.md
    """

    def __init__(self, root: Optional[Path] = None):
        if root is None:
            root = Path.home() / ".eduagent" / "brain"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # Create subdirectories for each page type
        for ptype in PAGE_TYPES:
            (self.root / f"{ptype}s").mkdir(exist_ok=True)

    def _page_path(self, page_type: str, slug: str) -> Path:
        """Return the file path for a page."""
        assert page_type in PAGE_TYPES, f"Unknown page type: {page_type}"
        return self.root / f"{page_type}s" / f"{slug}.md"

    def slugify(self, name: str) -> str:
        """Convert a name to a URL-safe slug."""
        s = name.lower().strip()
        s = re.sub(r"[^a-z0-9\s-]", "", s)
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"-+", "-", s)
        return s.strip("-")[:80]

    def save(self, page: BrainPage) -> Path:
        """Save a page to disk."""
        path = self._page_path(page.page_type, page.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page.render(), encoding="utf-8")
        return path

    def get(self, page_type: str, slug: str) -> Optional[BrainPage]:
        """Load a page by type and slug."""
        path = self._page_path(page_type, slug)
        if not path.exists():
            return None
        try:
            return BrainPage.parse(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def exists(self, page_type: str, slug: str) -> bool:
        """Check if a page exists."""
        return self._page_path(page_type, slug).exists()

    def list_pages(self, page_type: str) -> list[str]:
        """List slugs for a given page type."""
        d = self.root / f"{page_type}s"
        if not d.exists():
            return []
        return sorted(
            f.stem for f in d.glob("*.md") if not f.name.startswith("_")
        )

    def search(
        self,
        query: str,
        page_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[BrainPage]:
        """Simple keyword search across brain pages.

        For hybrid/vector search, use `clawed.brain.search.hybrid_search()`.
        """
        query_lower = query.lower()
        results: list[tuple[int, BrainPage]] = []

        types_to_search = [page_type] if page_type else list(PAGE_TYPES)
        for ptype in types_to_search:
            for slug in self.list_pages(ptype):
                page = self.get(ptype, slug)
                if not page:
                    continue
                # Score by keyword matches
                haystack = f"{page.title} {page.compiled_truth}".lower()
                score = haystack.count(query_lower)
                # Also check timeline
                for entry in page.timeline:
                    score += entry.body.lower().count(query_lower)
                if score > 0:
                    results.append((score, page))

        results.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in results[:limit]]

    def update_compiled_truth(
        self,
        page_type: str,
        slug: str,
        new_compiled_truth: str,
    ) -> bool:
        """Rewrite the compiled-truth zone. Returns True if updated."""
        page = self.get(page_type, slug)
        if not page:
            return False
        page.compiled_truth = new_compiled_truth
        page.metadata["updated"] = datetime.now().strftime("%Y-%m-%d")
        self.save(page)
        return True

    def append_timeline(
        self,
        page_type: str,
        slug: str,
        body: str,
        source: str = "",
        date: str = "",
        create_if_missing: bool = True,
        title: Optional[str] = None,
    ) -> bool:
        """Append a timeline entry. Creates the page if missing when allowed."""
        page = self.get(page_type, slug)
        if page is None:
            if not create_if_missing:
                return False
            page = BrainPage(
                slug=slug,
                page_type=page_type,
                title=title or slug.replace("-", " ").title(),
            )
        page.add_timeline(body, source=source, date=date)
        self.save(page)
        return True

    def stats(self) -> dict:
        """Return counts per page type."""
        return {ptype: len(self.list_pages(ptype)) for ptype in PAGE_TYPES}
