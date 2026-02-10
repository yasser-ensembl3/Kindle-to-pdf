"""Chapter and part detection from PDF text using regex patterns."""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChapterBoundary:
    """Detected chapter boundary in the text."""
    chapter_number: int
    title: str
    start_page: int
    part_number: Optional[int] = None
    part_title: Optional[str] = None


@dataclass
class PartBoundary:
    """Detected part boundary in the text."""
    part_number: int
    title: str
    start_page: int


# Number words for matching "Chapter One", "Part TWO", etc.
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22,
    "twenty-three": 23, "twenty-four": 24, "twenty-five": 25,
    "twenty-six": 26, "twenty-seven": 27, "twenty-eight": 28,
    "twenty-nine": 29, "thirty": 30, "thirty-one": 31, "thirty-two": 32,
    "thirty-three": 33, "thirty-four": 34, "thirty-five": 35,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


def _parse_number(text: str) -> Optional[int]:
    """Parse a number from text (digit or word)."""
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    return NUMBER_WORDS.get(text)


class ChapterDetector:
    """Detect chapter and part boundaries in book text.

    Uses configurable regex patterns to detect headings like:
    - "PART ONE: The Nature of..."
    - "Chapter 1 - So Much Soup..."
    - "Chapter 1: Title"
    - "CHAPTER ONE Title"
    """

    # Default patterns - can be overridden
    DEFAULT_PART_PATTERNS = [
        # "PART ONE: Title" or "PART ONE Title" or "Part 1: Title"
        r"(?i)^PART\s+([\w-]+)(?:\s*[:\-—–]\s*|\s+)(.+?)$",
        # "PART ONE" alone on a line
        r"(?i)^PART\s+([\w-]+)\s*$",
    ]

    DEFAULT_CHAPTER_PATTERNS = [
        # "Chapter 1 - Title" or "Chapter 1: Title" or "Chapter One - Title"
        r"(?i)^Chapter\s+([\w-]+)\s*[:\-—–]\s*(.+?)$",
        # "Chapter 1" alone on a line
        r"(?i)^Chapter\s+([\w-]+)\s*$",
        # "CHAPTER 1 Title" (no separator)
        r"(?i)^CHAPTER\s+(\d+)\s+(.+?)$",
    ]

    def __init__(
        self,
        part_patterns: list[str] | None = None,
        chapter_patterns: list[str] | None = None,
    ):
        self.part_patterns = [
            re.compile(p) for p in (part_patterns or self.DEFAULT_PART_PATTERNS)
        ]
        self.chapter_patterns = [
            re.compile(p) for p in (chapter_patterns or self.DEFAULT_CHAPTER_PATTERNS)
        ]

    def detect(
        self, pages: list[tuple[int, str]]
    ) -> tuple[list[PartBoundary], list[ChapterBoundary]]:
        """Detect parts and chapters from page text.

        Args:
            pages: List of (page_number, page_text) tuples.

        Returns:
            Tuple of (parts, chapters) boundary lists.
        """
        parts: list[PartBoundary] = []
        chapters: list[ChapterBoundary] = []

        current_part: Optional[PartBoundary] = None

        for page_num, page_text in pages:
            lines = page_text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check for part boundaries
                part = self._match_part(line, page_num)
                if part:
                    current_part = part
                    parts.append(part)
                    continue

                # Check for chapter boundaries
                chapter = self._match_chapter(line, page_num, current_part)
                if chapter:
                    chapters.append(chapter)

        return parts, chapters

    def _match_part(self, line: str, page_num: int) -> Optional[PartBoundary]:
        """Try to match a line as a part heading."""
        for pattern in self.part_patterns:
            m = pattern.match(line)
            if m:
                num_text = m.group(1)
                num = _parse_number(num_text)
                if num is None:
                    continue
                title = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                return PartBoundary(part_number=num, title=title, start_page=page_num)
        return None

    def _match_chapter(
        self, line: str, page_num: int, current_part: Optional[PartBoundary]
    ) -> Optional[ChapterBoundary]:
        """Try to match a line as a chapter heading."""
        for pattern in self.chapter_patterns:
            m = pattern.match(line)
            if m:
                num_text = m.group(1)
                num = _parse_number(num_text)
                if num is None:
                    continue
                title = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                return ChapterBoundary(
                    chapter_number=num,
                    title=title,
                    start_page=page_num,
                    part_number=current_part.part_number if current_part else None,
                    part_title=current_part.title if current_part else None,
                )
        return None
