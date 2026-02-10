# Kindle-to-MD

Automated pipeline that converts books into structured Markdown, distills each chapter through 3 analytical lenses, and synthesizes thematic insights — all powered by Claude.

## What It Does

```
Book (.pdf or .md)
    |
    v
kindle2md pipeline book.pdf
    |
    +-- book.md              (structured Markdown with frontmatter + TOC)
    +-- book_distillation.md (3-lens analysis per chapter)
    +-- book_insights.md     (thematic synthesis across all chapters)
    +-- chapters/            (individual chapter files)
```

### The 3 Lenses

Each chapter is analyzed through:

- **Phenomenology** — what it *feels* like from the inside. Powerful quotes, metaphors, lived experiences.
- **Deep Facts** — 3rd-to-5th layer insights beyond common sense. Counter-intuitive truths, hidden mechanisms.
- **Action Items** — concrete, actionable recommendations the reader can apply.

### Thematic Synthesis

The insights file reorganizes all chapter analyses by *theme* (not by chapter), consolidating related ideas from across the entire book into coherent sections.

## Quick Start

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -e .

# Process a local PDF
kindle2md pipeline book.pdf --model haiku

# Process books from Google Drive
kindle2md drive-sync "https://drive.google.com/drive/folders/..." --model haiku
```

See [INSTALL.md](INSTALL.md) for detailed setup instructions.

## Commands

| Command | Description |
|---------|-------------|
| `kindle2md extract <pdf>` | Extract PDF to structured book.md + chapter files |
| `kindle2md distill <pdf>` | Distill each chapter through 3 lenses |
| `kindle2md synthesize <pdf>` | Synthesize distillation into thematic insights |
| `kindle2md pipeline <pdf>` | Run all 3 steps end-to-end |
| `kindle2md drive-sync <folder>` | Pull .md books from Drive, process, upload results back |

### Common Options

```
--model, -m     Claude model: haiku (fast), sonnet (balanced), opus (best)
--title, -t     Override book title
--author, -a    Override book author
--output-dir, -o  Custom output directory
```

## Drive Sync

`drive-sync` connects to a Google Drive folder where each subfolder contains a book `.md` file. It:

1. Downloads each book
2. Parses chapters automatically (supports epub-converted, standard, and numbered formats)
3. Distills all chapters in parallel (10 concurrent Claude calls)
4. Synthesizes thematic insights
5. Uploads `_distillation.md` and `_insights.md` back to the same Drive folder

### Performance

| Book Size | Chapters | Time |
|-----------|----------|------|
| ~60k words | 20 | ~2.5 min |

Optimized with parallel processing (10 workers) and local assembly (no LLM call for formatting).

## Project Structure

```
Kindle-to-md/
├── src/
│   ├── cli/commands.py          # CLI (Typer) — all commands
│   ├── extractors/
│   │   ├── pdf.py               # PDF extraction (pdfplumber)
│   │   ├── markdown_parser.py   # .md book parser (epub/standard/numbered)
│   │   └── chapter_detector.py  # Chapter/Part detection (regex)
│   ├── converters/
│   │   └── book_markdown.py     # Book → Obsidian-format Markdown
│   ├── models/
│   │   └── book.py              # Pydantic models (Book, Chapter, Part)
│   ├── prompts/
│   │   └── generator.py         # Prompt generation from templates
│   ├── drive/
│   │   └── client.py            # Google Drive API client
│   └── config.py
├── templates/
│   ├── distillation_chapter.md  # Per-chapter 3-lens prompt
│   ├── distillation_assembly.md # Assembly prompt
│   └── insights_synthesis.md    # Thematic synthesis prompt
├── pyproject.toml
├── requirements.txt
├── INSTALL.md
└── README.md
```

## How It Works

- **Extraction**: pdfplumber for PDFs, custom regex parser for epub-converted `.md` files
- **LLM**: Claude Code CLI (`claude -p`) — uses your existing subscription, zero API cost
- **Parallelism**: ThreadPoolExecutor with 10 workers for chapter distillation
- **Drive**: Google Drive API v3 with OAuth2 for download/upload

## Requirements

- Python 3.10+
- Claude Code CLI (authenticated)
- Google OAuth credentials (for Drive sync only)
