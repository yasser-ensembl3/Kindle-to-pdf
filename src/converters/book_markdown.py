"""Convert Book model to Obsidian-formatted Markdown."""
from pathlib import Path

from src.models.book import Book


class BookMarkdownConverter:
    """Produce a single structured Markdown file matching Obsidian format.

    Output matches the format of scattered_minds.md:
    - YAML frontmatter
    - About section
    - Table of Contents with wiki-style links
    - Full text organized by Parts > Chapters
    """

    def convert(self, book: Book) -> str:
        """Convert a Book to a full Markdown string."""
        sections = [
            self._frontmatter(book),
            self._header(book),
            self._about(book),
            self._toc(book),
        ]

        # Introduction
        if book.introduction:
            sections.append("## Introduction\n\n" + book.introduction)
            sections.append("---")

        # Parts and chapters
        for part in book.parts:
            if part.title:
                sections.append(f"PART {self._roman(part.number)} {part.title}")
                sections.append("---")
                sections.append(f"# Part {self._word(part.number)}: {part.title}")

            for chapter in part.chapters:
                heading = f"## Chapter {chapter.number} - {chapter.title}"
                sections.append(heading)
                sections.append(chapter.text)
                sections.append("---")

        return "\n\n".join(sections).rstrip("\n-— ") + "\n"

    def convert_to_file(self, book: Book, output_path: Path | str) -> Path:
        """Write book markdown to file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.convert(book)
        path.write_text(content, encoding="utf-8")
        return path

    def _frontmatter(self, book: Book) -> str:
        """Generate YAML frontmatter."""
        meta = book.metadata
        lines = ["---"]
        lines.append(f"title: {meta.title}")
        lines.append(f"author: {meta.author}")
        if meta.published:
            lines.append(f"published: {meta.published}")
        if meta.tags:
            tags_str = ", ".join(meta.tags)
            lines.append(f"tags: [{tags_str}]")
        if meta.aliases:
            aliases_str = ", ".join(meta.aliases)
            lines.append(f"aliases: [{aliases_str}]")
        if meta.related:
            related_str = ", ".join(f'"{r}"' for r in meta.related)
            lines.append(f"related: [{related_str}]")
        lines.append("---")
        return "\n".join(lines)

    def _header(self, book: Book) -> str:
        """Generate header section."""
        meta = book.metadata
        lines = [f"# {meta.title}"]
        lines.append(f"\n**Author:** {meta.author}")
        if meta.published:
            lines.append(f"**Published:** {meta.published}")
        return "\n".join(lines)

    def _about(self, book: Book) -> str:
        """Generate About section placeholder."""
        return "---\n\n## About This Book\n"

    def _toc(self, book: Book) -> str:
        """Generate Table of Contents with Obsidian wiki-links."""
        lines = ["---\n\n## Table of Contents"]

        for part in book.parts:
            if part.title:
                lines.append(
                    f"\n### Part {self._word(part.number)}: {part.title}"
                )

            for ch in part.chapters:
                anchor = f"Chapter {ch.number} - {ch.title}"
                display = f"Chapter {ch.number}: {ch.title}"
                lines.append(f"- [[#{anchor}|{display}]]")

        return "\n".join(lines)

    @staticmethod
    def _word(n: int) -> str:
        """Convert number to word (ONE, TWO, etc.)."""
        words = {
            1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE",
            6: "SIX", 7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN",
        }
        return words.get(n, str(n))

    @staticmethod
    def _roman(n: int) -> str:
        """Convert to uppercase word for PART header."""
        words = {
            1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE",
            6: "SIX", 7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN",
        }
        return words.get(n, str(n))
