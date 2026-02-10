"""Data models for book representation."""
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class BookMetadata(BaseModel):
    """Book metadata for YAML frontmatter."""
    title: str = ""
    author: str = ""
    published: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    """A single chapter from the book."""
    number: int
    title: str
    text: str = ""
    part_number: Optional[int] = None
    part_title: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None

    @property
    def slug(self) -> str:
        """Generate a filename-safe slug."""
        clean = self.title.lower()
        for char in ":/\\?*\"<>|'.,;!()[]{}":
            clean = clean.replace(char, "")
        clean = clean.replace(" ", "_").replace("--", "_").replace("__", "_")
        return f"ch{self.number:02d}_{clean[:50].strip('_')}"

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class Part(BaseModel):
    """A part/section grouping chapters."""
    number: int
    title: str
    chapters: list[Chapter] = Field(default_factory=list)


class Book(BaseModel):
    """Complete book representation."""
    metadata: BookMetadata = Field(default_factory=BookMetadata)
    introduction: str = ""
    parts: list[Part] = Field(default_factory=list)

    @property
    def all_chapters(self) -> list[Chapter]:
        """Flat list of all chapters across all parts."""
        chapters = []
        for part in self.parts:
            chapters.extend(part.chapters)
        return chapters

    @property
    def total_chapters(self) -> int:
        return len(self.all_chapters)

    @property
    def total_words(self) -> int:
        words = len(self.introduction.split()) if self.introduction else 0
        for ch in self.all_chapters:
            words += ch.word_count
        return words

    def to_json(self, path: Path | str) -> None:
        """Serialize book to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path | str) -> "Book":
        """Deserialize book from JSON file."""
        data = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(data)
