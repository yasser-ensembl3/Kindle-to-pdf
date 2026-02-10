"""Parse an existing book markdown file into a Book model.

Handles multiple formats:
- Obsidian style: "## Chapter 1 - Title"
- Epub-converted: "# C[HAPTER]{.small} 1" followed by "# **Title**"
- Numbered: "## 1. Title"
"""
import re
from pathlib import Path
from typing import Optional

from src.models.book import Book, BookMetadata, Chapter, Part


class MarkdownBookParser:
    """Parse a structured book .md file into a Book model."""

    def parse(self, text: str, source_path: str = "") -> Book:
        """Parse markdown text into a Book."""
        meta = self._parse_metadata(text, source_path)

        # Try multiple chapter detection strategies
        chapters = (
            self._detect_epub_chapters(text)
            or self._detect_standard_chapters(text)
            or self._detect_numbered_chapters(text)
        )

        if not chapters:
            clean = self._strip_frontmatter_and_toc(text)
            chapters = [Chapter(number=1, title="Full Text", text=clean.strip())]

        # Strip notes/appendix sections from last chapter
        chapters = self._trim_backmatter(chapters, text)

        # Detect parts and group
        parts = self._detect_and_group_parts(chapters, text)

        return Book(metadata=meta, parts=parts)

    def parse_file(self, path: Path | str) -> Book:
        """Parse a markdown file into a Book."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        return self.parse(text, source_path=str(path))

    # ── Chapter detection strategies ──────────────────────────

    def _detect_epub_chapters(self, text: str) -> list[Chapter]:
        """Detect epub-converted format: # ...C[HAPTER]{.small} N ... followed by # **Title**"""
        # Pattern: "# []{...}C[HAPTER]{.small} N {..."
        pattern = re.compile(
            r"^#\s+.*?C\[HAPTER\]\{\.small\}\s+(\d+)\s*\{",
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return []

        chapters: list[Chapter] = []
        for i, m in enumerate(matches):
            num = int(m.group(1))
            # Title is on the next "# **Title**" line
            title = self._find_next_title(text, m.end())
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chapter_text = text[start:end].strip()
            chapters.append(Chapter(number=num, title=title, text=chapter_text))

        return chapters

    def _detect_standard_chapters(self, text: str) -> list[Chapter]:
        """Detect standard format: ## Chapter N - Title"""
        pattern = re.compile(
            r"^#{1,3}\s*Chapter\s+(\d+)\s*[:\-—–]\s*(.+?)$",
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return []

        chapters: list[Chapter] = []
        for i, m in enumerate(matches):
            num = int(m.group(1))
            title = m.group(2).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chapter_text = text[start:end].strip()
            chapter_text = re.sub(r"\n---\s*$", "", chapter_text).strip()
            chapters.append(Chapter(number=num, title=title, text=chapter_text))

        return chapters

    def _detect_numbered_chapters(self, text: str) -> list[Chapter]:
        """Detect numbered format: ## 1. Title"""
        pattern = re.compile(
            r"^#{1,3}\s*(\d+)\.\s+(.+?)$",
            re.MULTILINE,
        )
        matches = list(pattern.finditer(text))
        if len(matches) < 3:  # need at least 3 to be confident
            return []

        chapters: list[Chapter] = []
        for i, m in enumerate(matches):
            num = int(m.group(1))
            title = m.group(2).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chapter_text = text[start:end].strip()
            chapters.append(Chapter(number=num, title=title, text=chapter_text))

        return chapters

    # ── Part detection ────────────────────────────────────────

    def _detect_and_group_parts(self, chapters: list[Chapter], text: str) -> list[Part]:
        """Detect part boundaries and group chapters."""
        # Epub format: # **ESSENCE** {... .part} or # []{...}**EXPLORE** {... .part}
        epub_part = re.compile(
            r"^#\s+.*?\*\*([A-Z][A-Z\s]+?)\*\*\s*\{[^}]*\.part\b",
            re.MULTILINE,
        )
        # Standard: # Part ONE: Title
        std_part = re.compile(
            r"^#\s*Part\s+(\w+)\s*[:\-—–]\s*(.+?)$",
            re.MULTILINE | re.IGNORECASE,
        )

        part_boundaries: list[tuple[int, str, int]] = []  # (num, title, text_pos)

        # Try epub parts first
        epub_matches = list(epub_part.finditer(text))
        if epub_matches:
            for idx, m in enumerate(epub_matches, 1):
                title = m.group(1).strip().title()
                part_boundaries.append((idx, title, m.start()))
        else:
            # Try standard parts
            from src.extractors.chapter_detector import _parse_number
            for m in std_part.finditer(text):
                num = _parse_number(m.group(1))
                if num:
                    part_boundaries.append((num, m.group(2).strip(), m.start()))

        if not part_boundaries:
            return [Part(number=1, title="", chapters=chapters)]

        part_boundaries.sort(key=lambda x: x[2])

        # Find chapter title line position (use start of chapter text)
        def _ch_pos(ch: Chapter) -> int:
            idx = text.find(ch.text[:80]) if ch.text else -1
            return idx if idx != -1 else 0

        parts: list[Part] = []
        for i, (pnum, ptitle, pstart) in enumerate(part_boundaries):
            pend = part_boundaries[i + 1][2] if i + 1 < len(part_boundaries) else len(text)
            part_chs = [ch for ch in chapters if pstart <= _ch_pos(ch) < pend]
            for ch in part_chs:
                ch.part_number = pnum
                ch.part_title = ptitle
            if part_chs:
                parts.append(Part(number=pnum, title=ptitle, chapters=part_chs))

        # Orphans (before first part)
        assigned = {id(ch) for p in parts for ch in p.chapters}
        orphans = [ch for ch in chapters if id(ch) not in assigned]
        if orphans:
            parts.insert(0, Part(number=0, title="", chapters=orphans))

        return parts

    # ── Helpers ────────────────────────────────────────────────

    def _find_next_title(self, text: str, pos: int) -> str:
        """Find the next # **Title** line after a given position."""
        # Look for "# **Title** {.subchapter}" within ~200 chars
        snippet = text[pos:pos + 300]
        m = re.search(r"^#\s+\*\*(.+?)\*\*", snippet, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return ""

    def _parse_metadata(self, text: str, source_path: str) -> BookMetadata:
        """Extract metadata from frontmatter or first heading."""
        # YAML frontmatter
        fm = re.match(r"^---\s*\n(.+?)\n---", text, re.DOTALL)
        if fm:
            body = fm.group(1)
            title = self._fm_val(body, "title")
            author = self._fm_val(body, "author")
            published = self._fm_val(body, "published")
            tags_m = re.search(r"tags:\s*\[([^\]]*)\]", body)
            tags = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else []
            if title:
                return BookMetadata(title=title, author=author, published=published, tags=tags)

        # First # heading as title
        h1 = re.search(r"^#\s+(.+?)$", text, re.MULTILINE)
        if h1:
            title = re.sub(r"\s*--\s*", " - ", h1.group(1).strip())
            # Try to split "Title -- Author" from filename
            parts = title.split(" - ")
            if len(parts) >= 2:
                return BookMetadata(title=parts[0].strip(), author=parts[-1].strip())
            return BookMetadata(title=title)

        # Fallback to filename
        name = Path(source_path).stem if source_path else "Unknown"
        clean = re.sub(r"\s*--\s*", " - ", name.replace("_", " "))
        return BookMetadata(title=clean)

    @staticmethod
    def _fm_val(fm: str, key: str) -> str:
        m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
        return m.group(1).strip().strip('"').strip("'") if m else ""

    def _strip_frontmatter_and_toc(self, text: str) -> str:
        """Remove YAML frontmatter and TOC."""
        text = re.sub(r"^---\s*\n.+?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
        text = re.sub(r"# \*\*CONTENTS\*\*.*?(?=\n# )", "", text, flags=re.DOTALL)
        return text

    def _trim_backmatter(self, chapters: list[Chapter], text: str) -> list[Chapter]:
        """Remove Notes/Appendix/Acknowledgments from the chapter list."""
        backmatter_keywords = {"notes", "acknowledgments", "acknowledgements", "appendix", "index", "bibliography"}
        trimmed = []
        for ch in chapters:
            if ch.title.lower().strip("* ") in backmatter_keywords:
                break
            trimmed.append(ch)
        return trimmed if trimmed else chapters
