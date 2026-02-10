"""Kindle PDF extraction using pdfplumber."""
import re
from collections import Counter
from pathlib import Path
from typing import Optional

import pdfplumber

from src.extractors.chapter_detector import ChapterDetector, ChapterBoundary
from src.models.book import Book, BookMetadata, Chapter, Part


class KindlePDFExtractor:
    """Extract structured book content from Kindle PDF files.

    Handles:
    - Page-by-page text extraction via pdfplumber
    - Recurring header/footer removal
    - Hyphenated word rejoining at line breaks
    - Chapter/part detection and text segmentation
    """

    def __init__(
        self,
        path: Path | str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        chapter_detector: Optional[ChapterDetector] = None,
    ):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.path}")
        if not self.path.suffix.lower() == ".pdf":
            raise ValueError(f"File is not a PDF: {self.path}")

        self.title = title
        self.author = author
        self.detector = chapter_detector or ChapterDetector()

    def extract(self) -> Book:
        """Extract full book structure from PDF.

        Returns:
            Book model with metadata, parts, and chapters.
        """
        # Step 1: Raw page extraction
        raw_pages = self._extract_raw_pages()

        # Step 2: Clean pages (remove headers/footers, fix hyphenation)
        cleaned_pages = self._clean_pages(raw_pages)

        # Step 3: Detect chapters and parts
        page_tuples = [(i + 1, text) for i, text in enumerate(cleaned_pages)]
        parts_found, chapters_found = self.detector.detect(page_tuples)

        # Step 4: Build book structure
        book = self._build_book(cleaned_pages, parts_found, chapters_found)

        return book

    def _extract_raw_pages(self) -> list[str]:
        """Extract raw text from each page."""
        pages = []
        with pdfplumber.open(self.path) as pdf:
            # Try to get metadata
            if not self.title and pdf.metadata:
                self.title = pdf.metadata.get("Title", "")
            if not self.author and pdf.metadata:
                self.author = pdf.metadata.get("Author", "")

            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
        return pages

    def _clean_pages(self, pages: list[str]) -> list[str]:
        """Clean extracted pages: remove headers/footers, fix hyphenation."""
        # Detect recurring headers/footers
        recurring = self._detect_recurring_lines(pages)

        cleaned = []
        for page_text in pages:
            lines = page_text.split("\n")
            filtered = []
            for line in lines:
                stripped = line.strip()
                # Skip recurring headers/footers
                if stripped in recurring:
                    continue
                # Skip standalone page numbers
                if re.match(r"^\d{1,4}$", stripped):
                    continue
                filtered.append(line)

            text = "\n".join(filtered)
            # Fix hyphenated word breaks: "word-\nrest" -> "wordrest"
            text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
            cleaned.append(text)

        return cleaned

    def _detect_recurring_lines(self, pages: list[str], threshold: float = 0.3) -> set[str]:
        """Find lines that appear on many pages (headers/footers)."""
        line_counts: Counter = Counter()
        for page_text in pages:
            # Only check first 3 and last 3 lines of each page
            lines = page_text.split("\n")
            check_lines = lines[:3] + lines[-3:]
            seen = set()
            for line in check_lines:
                stripped = line.strip()
                if stripped and stripped not in seen:
                    seen.add(stripped)
                    line_counts[stripped] += 1

        total_pages = len(pages)
        recurring = set()
        for line, count in line_counts.items():
            if count >= total_pages * threshold and len(line) < 100:
                recurring.add(line)
        return recurring

    def _build_book(
        self,
        pages: list[str],
        parts_found: list,
        chapters_found: list[ChapterBoundary],
    ) -> Book:
        """Build Book model from detected structure."""
        metadata = BookMetadata(
            title=self.title or self._infer_title(pages),
            author=self.author or "",
        )

        # If no chapters detected, create a single chapter with all text
        if not chapters_found:
            full_text = "\n\n".join(p for p in pages if p.strip())
            single_chapter = Chapter(number=1, title="Full Text", text=full_text)
            single_part = Part(number=1, title="", chapters=[single_chapter])
            return Book(metadata=metadata, parts=[single_part])

        # Assign end pages
        for i, ch in enumerate(chapters_found):
            if i + 1 < len(chapters_found):
                ch.end_page = chapters_found[i + 1].start_page - 1
            else:
                ch.end_page = len(pages)

        # Extract introduction (text before first chapter)
        intro_text = ""
        first_ch_page = chapters_found[0].start_page
        if first_ch_page > 1:
            intro_pages = pages[:first_ch_page - 1]
            intro_text = "\n\n".join(p for p in intro_pages if p.strip())

        # Build chapters with their text
        chapters = []
        for boundary in chapters_found:
            start = boundary.start_page - 1  # 0-indexed
            end = boundary.end_page  # exclusive
            chapter_pages = pages[start:end]
            text = "\n\n".join(p for p in chapter_pages if p.strip())

            # Remove the chapter heading from the text body
            text = self._strip_chapter_heading(text, boundary)

            chapters.append(Chapter(
                number=boundary.chapter_number,
                title=boundary.title,
                text=text,
                part_number=boundary.part_number,
                part_title=boundary.part_title,
                start_page=boundary.start_page,
                end_page=boundary.end_page,
            ))

        # Group chapters into parts
        parts = self._group_into_parts(chapters, parts_found)

        return Book(metadata=metadata, introduction=intro_text, parts=parts)

    def _group_into_parts(self, chapters: list[Chapter], parts_found: list) -> list[Part]:
        """Group chapters into parts based on detected part boundaries."""
        if not parts_found:
            # No parts detected — wrap all chapters in a single part
            return [Part(number=1, title="", chapters=chapters)]

        parts = []
        part_map: dict[int, list[Chapter]] = {}

        for ch in chapters:
            pn = ch.part_number or 0
            if pn not in part_map:
                part_map[pn] = []
            part_map[pn].append(ch)

        # Build from detected parts
        for pb in parts_found:
            chs = part_map.get(pb.part_number, [])
            parts.append(Part(number=pb.part_number, title=pb.title, chapters=chs))

        # Add any orphan chapters (no part assigned)
        orphans = part_map.get(0, [])
        if orphans and not any(p.number == 0 for p in parts):
            parts.insert(0, Part(number=0, title="", chapters=orphans))

        return parts

    def _strip_chapter_heading(self, text: str, boundary: ChapterBoundary) -> str:
        """Remove the chapter heading line from chapter text."""
        lines = text.split("\n")
        pattern = re.compile(
            rf"(?i)^Chapter\s+{re.escape(str(boundary.chapter_number))}"
            r"|\bChapter\s+\w+\s*[:\-—–]\s*" + re.escape(boundary.title[:30]),
            re.IGNORECASE,
        )
        filtered = []
        heading_removed = False
        for line in lines:
            if not heading_removed and pattern.search(line.strip()):
                heading_removed = True
                continue
            filtered.append(line)
        return "\n".join(filtered)

    def _infer_title(self, pages: list[str]) -> str:
        """Try to infer title from the first page."""
        if pages and pages[0].strip():
            first_lines = pages[0].strip().split("\n")
            for line in first_lines[:5]:
                line = line.strip()
                if len(line) > 3 and not line.isdigit():
                    return line
        return self.path.stem.replace("_", " ").replace("-", " ").title()

    def write_chapters(self, book: Book, output_dir: Path) -> list[Path]:
        """Write individual chapter markdown files.

        Returns:
            List of paths to written chapter files.
        """
        chapters_dir = output_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for chapter in book.all_chapters:
            filename = f"{chapter.slug}.md"
            filepath = chapters_dir / filename

            content = f"# Chapter {chapter.number}: {chapter.title}\n\n"
            if chapter.part_title:
                content += f"*Part {chapter.part_number}: {chapter.part_title}*\n\n"
            content += "---\n\n"
            content += chapter.text

            filepath.write_text(content, encoding="utf-8")
            paths.append(filepath)

        return paths
