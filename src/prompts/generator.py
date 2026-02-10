"""Prompt generation for Claude CLI calls."""
from pathlib import Path

from src.models.book import Book, BookMetadata, Chapter


# Resolve templates directory relative to project root
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _load_template(name: str) -> str:
    """Load a template file by name."""
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


class PromptGenerator:
    """Generate prompts for each stage of the pipeline."""

    def __init__(self, templates_dir: Path | str | None = None):
        self.templates_dir = Path(templates_dir) if templates_dir else _TEMPLATES_DIR

    def _load(self, name: str) -> str:
        path = self.templates_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        return path.read_text(encoding="utf-8")

    def generate_chapter_prompt(self, chapter: Chapter, meta: BookMetadata) -> str:
        """Generate distillation prompt for a single chapter."""
        template = self._load("distillation_chapter.md")
        return template.format(
            num=chapter.number,
            title=chapter.title,
            book=meta.title,
            author=meta.author,
            chapter_text=chapter.text,
        )

    def generate_assembly_prompt(
        self, chapter_analyses: dict[int, str], meta: BookMetadata
    ) -> str:
        """Generate assembly prompt for all chapter analyses.

        Args:
            chapter_analyses: Dict of chapter_number -> analysis text
            meta: Book metadata
        """
        template = self._load("distillation_assembly.md")

        # Format chapter analyses
        parts = []
        for num in sorted(chapter_analyses.keys()):
            parts.append(f"### Chapter {num}\n\n{chapter_analyses[num]}")
        analyses_text = "\n\n---\n\n".join(parts)

        return template.format(
            book=meta.title,
            author=meta.author,
            chapter_analyses=analyses_text,
        )

    def generate_insights_prompt(self, distillation_text: str, meta: BookMetadata) -> str:
        """Generate insights synthesis prompt."""
        template = self._load("insights_synthesis.md")
        return template.format(
            book=meta.title,
            author=meta.author,
            distillation_text=distillation_text,
        )
