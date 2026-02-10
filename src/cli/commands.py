"""CLI commands for Kindle-to-MD pipeline."""
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)

from src.extractors.pdf import KindlePDFExtractor
from src.converters.book_markdown import BookMarkdownConverter
from src.models.book import Book
from src.prompts.generator import PromptGenerator

app = typer.Typer(
    name="kindle2md",
    help="Kindle PDF → Structured Markdown → Distillation → Insights pipeline.",
    add_completion=False,
)
console = Console()


def _slugify(text: str) -> str:
    """Convert title to filename-safe slug."""
    slug = text.lower().strip()
    for char in ":/\\?*\"<>|'.,;!()[]{}—–":
        slug = slug.replace(char, "")
    slug = slug.replace(" ", "_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")[:60]


def _call_claude(prompt: str, model: str = "sonnet") -> str:
    """Call Claude CLI with a prompt and return the response.

    Uses `claude -p` (pipe mode) with the user's existing Claude subscription.
    No API key needed.
    """
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--model", model,
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Claude CLI error (exit {result.returncode}): {stderr}")
    return result.stdout.strip()


MAX_PARALLEL = 10  # concurrent claude calls
CHUNK_MAX_WORDS = 15_000  # max words per Claude call


def _chunk_text(text: str, max_words: int = CHUNK_MAX_WORDS) -> list[str]:
    """Split text into chunks of ~max_words, breaking on paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        pw = len(para.split())
        if current_words + pw > max_words and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = pw
        else:
            current.append(para)
            current_words += pw

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _distill_chapters_parallel(
    chapters,
    gen,
    meta,
    model: str,
    console: Console,
) -> dict[int, str]:
    """Distill all chapters in parallel, with chunking for large chapters."""
    from src.models.book import Chapter

    # Build work items: (chapter_number, title, chunk_index, total_chunks, Chapter)
    work_items: list[tuple[int, str, int, int, Chapter]] = []
    for ch in chapters:
        wc = len(ch.text.split())
        if wc > CHUNK_MAX_WORDS:
            chunks = _chunk_text(ch.text)
            for ci, chunk_text in enumerate(chunks):
                chunk_ch = Chapter(
                    number=ch.number,
                    title=f"{ch.title} (part {ci + 1}/{len(chunks)})",
                    text=chunk_text,
                )
                work_items.append((ch.number, ch.title, ci, len(chunks), chunk_ch))
        else:
            work_items.append((ch.number, ch.title, 0, 1, ch))

    total_jobs = len(work_items)
    if total_jobs != len(chapters):
        console.print(
            f"  [dim]{len(chapters)} chapters → {total_jobs} jobs "
            f"(chunked chapters > {CHUNK_MAX_WORDS:,} words)[/dim]"
        )

    # Process all jobs in parallel
    # Result key: (chapter_number, chunk_index)
    chunk_results: dict[tuple[int, int], str] = {}

    def _process_one(item):
        ch_num, _, ci, _, chunk_ch = item
        prompt = gen.generate_chapter_prompt(chunk_ch, meta)
        result = _call_claude(prompt, model=model)
        return ch_num, ci, result

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        ptask = progress.add_task("Distilling...", total=total_jobs)

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            futures = {pool.submit(_process_one, item): item for item in work_items}
            for future in as_completed(futures):
                item = futures[future]
                ch_num, ch_title, ci, total_c, _ = item
                try:
                    num, chunk_idx, result = future.result()
                    chunk_results[(num, chunk_idx)] = result
                    if total_c == 1:
                        console.print(f"  [green]✓[/green] Ch.{num}: {ch_title[:40]}")
                    else:
                        console.print(
                            f"  [green]✓[/green] Ch.{num} chunk {ci + 1}/{total_c}"
                        )
                except Exception as e:
                    chunk_results[(ch_num, ci)] = f"*Error: {e}*"
                    console.print(f"  [red]✗[/red] Ch.{ch_num} chunk {ci + 1}: {e}")
                progress.advance(ptask)

    # Merge chunks per chapter
    chapter_analyses: dict[int, str] = {}
    for ch in chapters:
        ch_chunks = sorted(
            [(ci, text) for (num, ci), text in chunk_results.items() if num == ch.number],
            key=lambda x: x[0],
        )
        chapter_analyses[ch.number] = "\n\n".join(text for _, text in ch_chunks)

    return chapter_analyses


def _synthesize_chunked(distillation: str, gen, meta, model: str, console: Console) -> str:
    """Synthesize insights, chunking the distillation if too large."""
    dist_words = len(distillation.split())
    if dist_words <= CHUNK_MAX_WORDS:
        prompt = gen.generate_insights_prompt(distillation, meta)
        return _call_claude(prompt, model=model)

    # Split distillation by chapter sections, group into chunks
    chunks = _chunk_text(distillation)
    console.print(
        f"  [dim]Distillation too large ({dist_words:,} words), "
        f"synthesizing in {len(chunks)} passes...[/dim]"
    )

    # Pass 1: synthesize each chunk separately (parallel)
    partial_insights: list[str] = [None] * len(chunks)

    def _synth_one(idx, chunk):
        prompt = gen.generate_insights_prompt(chunk, meta)
        return idx, _call_claude(prompt, model=model)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(_synth_one, i, c): i for i, c in enumerate(chunks)}
        for future in as_completed(futures):
            try:
                idx, result = future.result()
                partial_insights[idx] = result
            except Exception as e:
                idx = futures[future]
                partial_insights[idx] = f"*Error: {e}*"

    # Pass 2: merge partial insights into final synthesis
    merged = "\n\n---\n\n".join(p for p in partial_insights if p)
    if len(merged.split()) <= CHUNK_MAX_WORDS:
        merge_prompt = gen.generate_insights_prompt(merged, meta)
        return _call_claude(merge_prompt, model=model)

    # If still too large, return concatenated partials
    return merged


def _assemble_distillation(chapter_analyses: dict[int, str], meta) -> str:
    """Assemble chapter analyses into a single distillation document (no LLM call)."""
    lines = [
        f"# {meta.title} — Distillation",
        f"**Author:** {meta.author}",
        f"**Chapters:** {len(chapter_analyses)}",
        "",
        "---",
    ]
    for num in sorted(chapter_analyses.keys()):
        lines.append(f"\n## Chapter {num}\n")
        lines.append(chapter_analyses[num])
        lines.append("\n---")
    return "\n".join(lines)


def _resolve_output_dir(output_dir: Optional[Path], pdf_path: Path) -> Path:
    """Resolve the output directory."""
    if output_dir:
        out = output_dir
    else:
        out = pdf_path.parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _load_or_extract(
    pdf_path: Path,
    output_dir: Path,
    title: Optional[str],
    author: Optional[str],
) -> Book:
    """Load existing book JSON or extract from PDF."""
    slug = _slugify(title or pdf_path.stem)
    json_path = output_dir / f"{slug}.json"

    if json_path.exists():
        console.print(f"  [dim]Loading cached book from {json_path.name}[/dim]")
        return Book.from_json(json_path)

    extractor = KindlePDFExtractor(pdf_path, title=title, author=author)
    book = extractor.extract()
    book.to_json(json_path)
    return book


# ─── EXTRACT ──────────────────────────────────────────────────

@app.command()
def extract(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the Kindle PDF file",
        exists=True,
        dir_okay=False,
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Book title"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Book author"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Output directory"
    ),
):
    """Step 1: Extract PDF → structured book.md + individual chapter files."""
    out = _resolve_output_dir(output_dir, pdf_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Extracting PDF content...", total=None)
        try:
            extractor = KindlePDFExtractor(pdf_path, title=title, author=author)
            book = extractor.extract()
        except Exception as e:
            console.print(f"[red]Extraction failed:[/red] {e}")
            raise typer.Exit(1)

        progress.add_task("Writing book markdown...", total=None)
        slug = _slugify(book.metadata.title or pdf_path.stem)

        # Save JSON cache
        book.to_json(out / f"{slug}.json")

        # Write full book.md
        converter = BookMarkdownConverter()
        md_path = converter.convert_to_file(book, out / f"{slug}.md")

        # Write individual chapters
        progress.add_task("Writing chapter files...", total=None)
        chapter_paths = extractor.write_chapters(book, out)

    console.print(Panel(
        f"[green]Extraction complete![/green]\n\n"
        f"[bold]Book:[/bold] {book.metadata.title}\n"
        f"[bold]Author:[/bold] {book.metadata.author}\n"
        f"[bold]Parts:[/bold] {len(book.parts)}\n"
        f"[bold]Chapters:[/bold] {book.total_chapters}\n"
        f"[bold]Words:[/bold] {book.total_words:,}\n\n"
        f"[bold]Output:[/bold] {md_path}\n"
        f"[bold]Chapters:[/bold] {len(chapter_paths)} files in {out / 'chapters'}",
        title="kindle2md extract",
        border_style="green",
    ))


# ─── DISTILL ──────────────────────────────────────────────────

@app.command()
def distill(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the Kindle PDF file",
        exists=True,
        dir_okay=False,
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Book title"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Book author"),
    model: str = typer.Option("sonnet", "--model", "-m", help="Claude model (sonnet/haiku/opus)"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Output directory"
    ),
):
    """Step 2: Distill each chapter through 3 lenses → distillation.md."""
    out = _resolve_output_dir(output_dir, pdf_path)
    book = _load_or_extract(pdf_path, out, title, author)
    slug = _slugify(book.metadata.title or pdf_path.stem)
    gen = PromptGenerator()

    chapters = book.all_chapters
    if not chapters:
        console.print("[red]No chapters found in book.[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Distilling {len(chapters)} chapters with Claude ({model}) — {MAX_PARALLEL} parallel...[/bold]\n")

    chapter_analyses = _distill_chapters_parallel(
        chapters, gen, book.metadata, model, console
    )

    # Assembly (local — no LLM call)
    distillation = _assemble_distillation(chapter_analyses, book.metadata)

    dist_path = out / f"{slug}_distillation.md"
    dist_path.write_text(distillation, encoding="utf-8")

    console.print(Panel(
        f"[green]Distillation complete![/green]\n\n"
        f"[bold]Chapters processed:[/bold] {len(chapter_analyses)}\n"
        f"[bold]Output:[/bold] {dist_path}",
        title="kindle2md distill",
        border_style="blue",
    ))


# ─── SYNTHESIZE ───────────────────────────────────────────────

@app.command()
def synthesize(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the Kindle PDF file",
        exists=True,
        dir_okay=False,
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Book title"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Book author"),
    model: str = typer.Option("sonnet", "--model", "-m", help="Claude model (sonnet/haiku/opus)"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Output directory"
    ),
):
    """Step 3: Synthesize distillation → thematic insights.md."""
    out = _resolve_output_dir(output_dir, pdf_path)
    slug = _slugify(title or pdf_path.stem)

    # Load existing distillation
    dist_path = out / f"{slug}_distillation.md"
    if not dist_path.exists():
        console.print(
            f"[red]Distillation file not found:[/red] {dist_path}\n"
            f"[dim]Run `kindle2md distill` first, or use `kindle2md pipeline`.[/dim]"
        )
        raise typer.Exit(1)

    distillation_text = dist_path.read_text(encoding="utf-8")

    # Load book metadata
    json_path = out / f"{slug}.json"
    if json_path.exists():
        book = Book.from_json(json_path)
        meta = book.metadata
    else:
        from src.models.book import BookMetadata
        meta = BookMetadata(title=title or slug.replace("_", " ").title(), author=author or "")

    gen = PromptGenerator()

    console.print(f"\n[bold]Synthesizing insights with Claude ({model})...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Generating thematic synthesis...", total=None)
        prompt = gen.generate_insights_prompt(distillation_text, meta)
        try:
            insights = _call_claude(prompt, model=model)
        except Exception as e:
            console.print(f"[red]Synthesis failed:[/red] {e}")
            raise typer.Exit(1)

    insights_path = out / f"{slug}_insights.md"
    insights_path.write_text(insights, encoding="utf-8")

    console.print(Panel(
        f"[green]Synthesis complete![/green]\n\n"
        f"[bold]Output:[/bold] {insights_path}",
        title="kindle2md synthesize",
        border_style="magenta",
    ))


# ─── PIPELINE ─────────────────────────────────────────────────

@app.command()
def pipeline(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the Kindle PDF file",
        exists=True,
        dir_okay=False,
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Book title"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Book author"),
    model: str = typer.Option("sonnet", "--model", "-m", help="Claude model (sonnet/haiku/opus)"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Output directory"
    ),
):
    """Run the full pipeline: extract → distill → synthesize."""
    console.print(Panel(
        f"[bold]Starting full pipeline[/bold]\n\n"
        f"[bold]PDF:[/bold] {pdf_path}\n"
        f"[bold]Model:[/bold] {model}",
        title="kindle2md pipeline",
        border_style="cyan",
    ))

    # Step 1: Extract
    console.print("\n[bold cyan]━━━ Step 1/3: Extract ━━━[/bold cyan]\n")
    out = _resolve_output_dir(output_dir, pdf_path)

    extractor = KindlePDFExtractor(pdf_path, title=title, author=author)
    book = extractor.extract()
    slug = _slugify(book.metadata.title or pdf_path.stem)

    book.to_json(out / f"{slug}.json")
    converter = BookMarkdownConverter()
    md_path = converter.convert_to_file(book, out / f"{slug}.md")
    extractor.write_chapters(book, out)

    console.print(
        f"  [green]✓[/green] Extracted {book.total_chapters} chapters "
        f"({book.total_words:,} words) → {md_path.name}"
    )

    # Step 2: Distill
    console.print("\n[bold cyan]━━━ Step 2/3: Distill ━━━[/bold cyan]\n")
    gen = PromptGenerator()
    chapters = book.all_chapters

    console.print(f"  [dim]Distilling {len(chapters)} chapters ({MAX_PARALLEL} parallel)...[/dim]")
    chapter_analyses = _distill_chapters_parallel(
        chapters, gen, book.metadata, model, console
    )

    # Assembly (local — no LLM call)
    distillation = _assemble_distillation(chapter_analyses, book.metadata)

    dist_path = out / f"{slug}_distillation.md"
    dist_path.write_text(distillation, encoding="utf-8")
    console.print(f"  [green]✓[/green] Distillation → {dist_path.name}")

    # Step 3: Synthesize
    console.print("\n[bold cyan]━━━ Step 3/3: Synthesize ━━━[/bold cyan]\n")
    console.print("  [dim]Generating thematic insights...[/dim]")
    try:
        insights = _synthesize_chunked(distillation, gen, book.metadata, model, console)
    except Exception as e:
        console.print(f"  [red]Synthesis failed:[/red] {e}")
        raise typer.Exit(1)

    insights_path = out / f"{slug}_insights.md"
    insights_path.write_text(insights, encoding="utf-8")
    console.print(f"  [green]✓[/green] Insights → {insights_path.name}")

    # Final summary
    console.print(Panel(
        f"[green bold]Pipeline complete![/green bold]\n\n"
        f"[bold]Book:[/bold] {book.metadata.title}\n"
        f"[bold]Author:[/bold] {book.metadata.author}\n"
        f"[bold]Chapters:[/bold] {book.total_chapters}\n\n"
        f"[bold]Files generated:[/bold]\n"
        f"  📖 {md_path.name}\n"
        f"  🔬 {dist_path.name}\n"
        f"  💡 {insights_path.name}\n"
        f"  📁 {book.total_chapters} chapter files in chapters/",
        title="✅ kindle2md pipeline",
        border_style="green",
    ))


# ─── DRIVE-PULL ───────────────────────────────────────────────

@app.command("drive-sync")
def drive_sync(
    folder: str = typer.Argument(
        ...,
        help="Google Drive folder ID or URL (each subfolder = one book with .md)",
    ),
    credentials: Path = typer.Option(
        "credentials.json",
        "--credentials", "-c",
        help="Path to Google OAuth credentials JSON",
    ),
    model: str = typer.Option("sonnet", "--model", "-m", help="Claude model"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Local output directory",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", help="Max number of books to process",
    ),
):
    """Download book .md files from Drive, distill + synthesize, upload back."""
    from src.drive.client import DriveClient
    from src.extractors.markdown_parser import MarkdownBookParser

    # Connect — opens browser on first run
    console.print("[bold]Authenticating with Google Drive...[/bold]")
    try:
        client = DriveClient(credentials)
    except Exception as e:
        console.print(f"[red]Auth failed:[/red] {e}")
        raise typer.Exit(1)
    console.print("[green]Authenticated.[/green]\n")

    folder_id = DriveClient.parse_folder_id(folder)

    try:
        folder_name = client.get_folder_name(folder_id)
    except Exception as e:
        console.print(f"[red]Cannot access folder:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]Drive folder:[/bold] {folder_name}\n")

    # List .md files recursively (each book in its own subfolder)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning for book .md files...", total=None)
        md_files = client.list_markdowns(folder_id, recursive=True)

    # Filter out our own generated files
    md_files = [
        f for f in md_files
        if not f["name"].endswith(("_distillation.md", "_insights.md"))
    ]

    # Sort alphabetically by name
    md_files.sort(key=lambda f: f["name"].lower())

    if not md_files:
        console.print("[yellow]No .md files found.[/yellow]")
        raise typer.Exit(0)

    total_found = len(md_files)
    if limit and limit < len(md_files):
        md_files = md_files[:limit]

    console.print(f"[bold]Found {total_found} book(s), processing {len(md_files)}:[/bold]")
    for f in md_files:
        path_prefix = f"{f.get('path', '')}/" if f.get("path") else ""
        console.print(f"  {path_prefix}{f['name']}")
    console.print()

    # Local output
    out = Path(output_dir) if output_dir else Path("output")
    out.mkdir(parents=True, exist_ok=True)

    parser = MarkdownBookParser()
    gen = PromptGenerator()
    success_count = 0
    fail_count = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        for i, file_info in enumerate(md_files, 1):
            name = file_info["name"]
            parent_id = file_info["parent_folder_id"]

            console.print(
                f"\n[bold cyan]━━━ Book {i}/{len(md_files)}: {name} ━━━[/bold cyan]\n"
            )

            # Download .md
            local_md = tmp_path / name
            try:
                client.download_file(file_info["id"], local_md)
                console.print(f"  [green]↓[/green] Downloaded")
            except Exception as e:
                console.print(f"  [red]✗[/red] Download failed: {e}")
                fail_count += 1
                continue

            try:
                # ── Parse markdown into Book ──
                book = parser.parse_file(local_md)
                slug = _slugify(book.metadata.title or local_md.stem)

                book_out = out / local_md.stem
                book_out.mkdir(parents=True, exist_ok=True)
                book.to_json(book_out / f"{slug}.json")

                console.print(
                    f"  [green]✓[/green] Parsed: {book.total_chapters} chapters, "
                    f"{book.total_words:,} words"
                )

                chapters = book.all_chapters
                if not chapters:
                    console.print("  [yellow]⚠[/yellow] No chapters detected, skipping")
                    fail_count += 1
                    continue

                # ── Distill (parallel) ──
                console.print(
                    f"  [dim]Distilling {len(chapters)} chapters "
                    f"({MAX_PARALLEL} parallel)...[/dim]"
                )
                chapter_analyses = _distill_chapters_parallel(
                    chapters, gen, book.metadata, model, console
                )

                # Assembly (local — no LLM call)
                distillation = _assemble_distillation(
                    chapter_analyses, book.metadata
                )

                dist_path = book_out / f"{slug}_distillation.md"
                dist_path.write_text(distillation, encoding="utf-8")
                client.upload_file(dist_path, parent_id)
                console.print(
                    f"  [green]✓[/green] Distilled + uploaded {dist_path.name}"
                )

                # ── Synthesize (with chunking if needed) ──
                console.print("  [dim]Synthesizing insights...[/dim]")
                try:
                    insights = _synthesize_chunked(
                        distillation, gen, book.metadata, model, console
                    )
                    insights_path = book_out / f"{slug}_insights.md"
                    insights_path.write_text(insights, encoding="utf-8")
                    client.upload_file(insights_path, parent_id)
                    console.print(
                        f"  [green]✓[/green] Synthesized + uploaded "
                        f"{insights_path.name}"
                    )
                except Exception as e:
                    console.print(f"  [yellow]⚠[/yellow] Synthesis failed: {e}")

                success_count += 1

            except Exception as e:
                console.print(f"  [red]✗[/red] Failed: {e}")
                fail_count += 1

    console.print(Panel(
        f"[green bold]Drive sync complete![/green bold]\n\n"
        f"[bold]Folder:[/bold] {folder_name}\n"
        f"[bold]Books:[/bold] {len(md_files)}\n"
        f"[green]Success:[/green] {success_count}\n"
        f"[red]Failed:[/red] {fail_count}\n\n"
        f"Each book's Drive folder now contains:\n"
        f"  book.md + _distillation.md + _insights.md",
        title="kindle2md drive-sync",
        border_style="green",
    ))


# ─── VERSION ──────────────────────────────────────────────────

@app.command()
def version():
    """Show version information."""
    console.print("[bold]kindle2md[/bold] version 0.1.0")


if __name__ == "__main__":
    app()
