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

The insights file reorganizes all chapter analyses by *theme* (not by chapter), consolidating related ideas from across the entire book into coherent sections (6-10 themes with roman numeral numbering).

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

See [INSTALL.md](INSTALL.md) for detailed setup instructions including Google Drive OAuth configuration.

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

## Architecture

```
Kindle-to-md/
├── src/
│   ├── cli/commands.py            # CLI entry point (Typer) — all 5 commands
│   ├── extractors/
│   │   ├── pdf.py                 # PDF extraction (pdfplumber) — header/footer removal, hyphen fix
│   │   ├── markdown_parser.py     # .md book parser (epub-converted / standard / numbered formats)
│   │   └── chapter_detector.py    # Chapter/Part boundary detection (regex, supports word numbers)
│   ├── converters/
│   │   └── book_markdown.py       # Book → Obsidian-format Markdown (YAML frontmatter, wiki-link TOC)
│   ├── models/
│   │   └── book.py                # Pydantic models: Book, Chapter, Part, BookMetadata (JSON serializable)
│   ├── prompts/
│   │   └── generator.py           # Prompt generation from Jinja-style templates
│   ├── drive/
│   │   └── client.py              # Google Drive API v3 client (OAuth2, download, upload, recursive listing)
│   └── config.py                  # Project paths and defaults
├── templates/
│   ├── distillation_chapter.md    # Per-chapter 3-lens prompt template
│   ├── distillation_assembly.md   # Full distillation assembly prompt
│   └── insights_synthesis.md      # Thematic synthesis prompt
├── watch.sh                       # launchd watcher script for inbox/ auto-processing
├── com.kindle2md.watcher.plist    # macOS launchd config
├── pyproject.toml
├── requirements.txt
├── INSTALL.md
└── README.md
```

## How It Works

### Extraction
- **PDF**: pdfplumber extracts page-by-page text → detects recurring headers/footers (>30% frequency) and removes them → fixes hyphenated line breaks → detects chapter/part boundaries via regex patterns (supports "Chapter One", "Chapter 1", "CHAPTER 1 Title", etc.)
- **Markdown**: Custom parser handles 3 formats — epub-converted (`C[HAPTER]{.small}`), standard (`## Chapter N - Title`), and numbered (`## 1. Title`) → auto-detects parts, strips backmatter (notes, appendix, etc.)

### LLM Calls
- Uses **Claude Code CLI** (`claude -p`) in pipe mode — leverages your existing Claude subscription, zero API cost
- Each chapter gets its own Claude call with a structured 3-lens prompt
- Large chapters (>15,000 words) are automatically chunked and processed in parts

### Parallelism
- **ThreadPoolExecutor** with 10 concurrent workers for chapter distillation
- Synthesis also supports chunking + parallel passes for large distillations
- Distillation assembly is done locally (string concatenation, no LLM call)

### Drive Sync
`drive-sync` connects to a Google Drive folder where each subfolder contains a book `.md` file. It:
1. Downloads each book's .md file
2. Parses chapters automatically (auto-detects format)
3. Distills all chapters in parallel (10 concurrent Claude calls)
4. Synthesizes thematic insights (with chunking if needed)
5. Uploads `_distillation.md` and `_insights.md` back to the same Drive subfolder

### Performance

| Book Size | Chapters | Time |
|-----------|----------|------|
| ~60k words | 20 | ~2.5 min |

### Watcher (Optional)
A macOS `launchd` agent watches the `inbox/` directory. Drop a PDF in, and the full pipeline runs automatically. Processed files are moved to `inbox/processed/`. See [INSTALL.md](INSTALL.md) for setup.

## Tech Stack

| Component | Library |
|-----------|---------|
| CLI framework | Typer + Rich |
| PDF extraction | pdfplumber |
| Data models | Pydantic v2 |
| LLM calls | Claude Code CLI (`claude -p`) |
| Google Drive | google-api-python-client + OAuth2 |
| Parallelism | concurrent.futures.ThreadPoolExecutor |

## Requirements

- Python 3.10+
- Claude Code CLI (installed and authenticated)
- Google OAuth credentials (for Drive sync only — see [INSTALL.md](INSTALL.md))
