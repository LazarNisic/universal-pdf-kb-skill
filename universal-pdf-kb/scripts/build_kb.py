"""
Universal PDF Knowledge Base Builder

Build a 4-layer knowledge system from any PDF file(s).
Works with any domain — technical, legal, medical, academic, business, etc.

Usage:
    python build_kb.py <pdf_path_or_folder> <output_folder> [--batch] [--tags "tag1,tag2"] [--chunk-size N]

Layer 1 (raw/): Original PDFs copied here.
Layer 2 (parsed/): Structured Markdown chunks per document.
Layer 3 (index/): Catalog with metadata for every chunk.
Layer 4 (decisions/): Decision log template.
"""

import sys
import re
import json
import hashlib
import shutil
import threading
from datetime import date
from pathlib import Path

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

if not HAS_PYPDF and not HAS_PDFPLUMBER:
    print("ERROR: Neither pypdf nor pdfplumber installed.")
    print("Run: pip install pypdf pdfplumber")
    sys.exit(1)


# ---------------------------------------------------------------------------
# General-purpose topic detection rules
# Covers broad categories applicable to any document domain
# ---------------------------------------------------------------------------
TOPIC_RULES = {
    # Technical / Engineering
    "software": ["software", "code", "programming", "algorithm", "api", "developer"],
    "architecture": ["architecture", "design pattern", "microservice", "component", "module"],
    "database": ["database", "schema", "table", "column", "sql", "query", "data model"],
    "networking": ["network", "protocol", "tcp", "http", "dns", "routing", "firewall"],
    "security": ["security", "encryption", "authentication", "authoriz", "vulnerabilit", "access control"],
    "cloud": ["cloud", "aws", "azure", "gcp", "kubernetes", "container", "docker"],
    "devops": ["devops", "ci/cd", "pipeline", "deployment", "infrastructure"],

    # Science / Academic
    "research": ["research", "study", "hypothesis", "methodology", "findings", "abstract"],
    "mathematics": ["theorem", "proof", "equation", "mathematical", "calculus", "algebra"],
    "physics": ["physics", "quantum", "thermodynamic", "electromagnetic", "particle"],
    "chemistry": ["chemical", "molecule", "reaction", "compound", "synthesis"],
    "biology": ["biology", "cell", "organism", "genetic", "protein", "evolution"],
    "medicine": ["medical", "clinical", "patient", "diagnosis", "treatment", "therapy", "symptom"],

    # Business / Finance
    "finance": ["finance", "revenue", "profit", "investment", "portfolio", "market"],
    "accounting": ["accounting", "ledger", "audit", "balance sheet", "tax", "fiscal"],
    "strategy": ["strategy", "competitive", "market analysis", "swot", "growth"],
    "management": ["management", "leadership", "organizational", "stakeholder"],
    "marketing": ["marketing", "brand", "customer", "campaign", "conversion"],
    "hr": ["human resources", "recruitment", "employee", "compensation", "onboarding"],

    # Legal
    "legal": ["legal", "law", "regulation", "compliance", "statute", "liability"],
    "contract": ["contract", "agreement", "clause", "term", "obligation", "party"],
    "intellectual-property": ["patent", "trademark", "copyright", "intellectual property"],
    "privacy": ["privacy", "gdpr", "data protection", "consent", "personal data"],

    # Education / Training
    "education": ["education", "curriculum", "learning", "student", "teacher", "course"],
    "training": ["training", "workshop", "certification", "competency", "skill"],

    # Engineering / Manufacturing
    "mechanical": ["mechanical", "torque", "stress", "material", "manufacture"],
    "electrical": ["electrical", "circuit", "voltage", "current", "semiconductor"],
    "civil": ["civil engineering", "structural", "foundation", "construction"],

    # Government / Policy
    "policy": ["policy", "regulation", "government", "public sector", "governance"],
    "environmental": ["environment", "sustainability", "emission", "climate", "ecology"],

    # Documentation types
    "specification": ["specification", "requirement", "technical spec", "standard"],
    "manual": ["manual", "user guide", "instruction", "how-to", "procedure"],
    "report": ["report", "analysis", "summary", "findings", "conclusion"],
    "reference": ["reference", "glossary", "terminology", "definition", "appendix"],
    "installation": ["install", "deploy", "setup", "upgrade", "migration"],
    "configuration": ["configur", "parameter", "setting", "option", "preference"],
    "release": ["release", "version", "changelog", "enhancement", "update"],
    "troubleshooting": ["troubleshoot", "error", "issue", "debug", "workaround", "fix"],
}


def sanitize_filename(name: str) -> str:
    """Convert PDF name to a safe folder/file name."""
    stem = Path(name).stem
    safe = re.sub(r'[^\w\s-]', '', stem).strip()
    safe = re.sub(r'[\s]+', '_', safe)
    return safe


def _extract_page_text_with_timeout(page, timeout_seconds=15):
    """Extract text from a single page with a timeout to avoid hangs."""
    result = [None]

    def worker():
        try:
            result[0] = page.extract_text() or ""
        except Exception:
            result[0] = ""

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if t.is_alive():
        return ""

    return result[0] if result[0] is not None else ""


def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """Extract text page by page. Uses pypdf (fast), falls back to pdfplumber."""
    pages = []

    # Primary: pypdf
    if HAS_PYPDF:
        try:
            reader = PdfReader(str(pdf_path))
            for i, page in enumerate(reader.pages, 1):
                text = _extract_page_text_with_timeout(page, timeout_seconds=15)
                pages.append({"page_number": i, "text": text})

            total_text = sum(len(p["text"]) for p in pages)
            if total_text > 100:
                return pages
        except Exception as e:
            print(f"  pypdf failed: {e}")
            pages = []

    # Fallback: pdfplumber
    if HAS_PDFPLUMBER and not pages:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = _extract_page_text_with_timeout(page, timeout_seconds=15)
                    pages.append({"page_number": i, "text": text})
            return pages
        except Exception as e:
            print(f"  pdfplumber also failed: {e}")

    return pages


def chunk_document(pages: list[dict], doc_id: str, chunk_size: int = 5) -> list[dict]:
    """Split pages into logical chunks based on heading detection.

    Args:
        pages: List of page dicts with 'page_number' and 'text'.
        doc_id: Document identifier for chunk naming.
        chunk_size: Number of pages per chunk when no headings are detected.
    """
    full_text = "\n\n".join(p["text"] for p in pages)

    # Try multiple heading patterns
    # Pattern 1: Numbered sections (e.g., "1.2 Some Title", "1.2.3 Title")
    numbered_pattern = r'(?=\n\d+(?:\.\d+)*\s+[A-Z])'
    # Pattern 2: Markdown-style headings (e.g., "# Title", "## Subtitle")
    markdown_pattern = r'(?=\n#{1,4}\s+\S)'
    # Pattern 3: ALL-CAPS headings on their own line
    caps_pattern = r'(?=\n[A-Z][A-Z\s]{4,}(?:\n|$))'

    raw_sections = re.split(numbered_pattern, full_text)

    if len(raw_sections) <= 1:
        raw_sections = re.split(markdown_pattern, full_text)

    if len(raw_sections) <= 1:
        raw_sections = re.split(caps_pattern, full_text)

    # Fallback: chunk by page groups
    if len(raw_sections) <= 1:
        raw_sections = []
        for i in range(0, len(pages), chunk_size):
            group = pages[i:i + chunk_size]
            section_text = "\n\n".join(p["text"] for p in group)
            raw_sections.append(section_text)

    chunks = []
    for i, section in enumerate(raw_sections, 1):
        section = section.strip()
        if not section or len(section) < 20:
            continue

        # Extract heading from first line
        first_line = section.split('\n')[0].strip()
        heading = first_line[:120] if first_line else f"Section {i}"

        # Find which pages this chunk spans
        page_start = None
        page_end = None
        for p in pages:
            if section[:80] in p["text"] or (len(section) > 50 and section[20:70] in p["text"]):
                if page_start is None:
                    page_start = p["page_number"]
                page_end = p["page_number"]

        if page_start is None:
            page_start = i
            page_end = i

        chunk_id = f"{doc_id}_chunk_{i:03d}"
        content_hash = hashlib.md5(section.encode()).hexdigest()[:8]

        chunks.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "heading": heading,
            "page_start": page_start,
            "page_end": page_end,
            "content": section,
            "content_hash": content_hash,
            "char_count": len(section)
        })

    return chunks


def assign_topic_tags(doc_title: str, content_sample: str, custom_tags: list[str] = None) -> list[str]:
    """Assign topic tags based on document title and content keywords.

    Uses a broad, general-purpose set of topic detection rules that work
    across any domain.

    Args:
        doc_title: Document title (usually the PDF filename stem).
        content_sample: First few pages of text for keyword matching.
        custom_tags: Optional user-supplied tags to include.
    """
    tags = []
    title_lower = doc_title.lower()
    sample_lower = content_sample[:8000].lower()
    combined = title_lower + " " + sample_lower

    for tag, keywords in TOPIC_RULES.items():
        if any(kw in combined for kw in keywords):
            tags.append(tag)

    # Add custom tags if provided
    if custom_tags:
        for tag in custom_tags:
            tag = tag.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)

    if not tags:
        tags.append("general")

    return tags


def write_parsed_markdown(parsed_dir: Path, doc_id: str, doc_title: str, chunks: list[dict], tags: list[str]):
    """Write parsed chunks as Markdown files."""
    doc_dir = parsed_dir / doc_id
    doc_dir.mkdir(exist_ok=True)

    # Write full document markdown
    md_path = doc_dir / f"{doc_id}.md"
    lines = [
        f"# {doc_title}\n",
        f"**Document ID:** {doc_id}  ",
        f"**Topics:** {', '.join(tags)}  ",
        f"**Chunks:** {len(chunks)}  ",
        f"**Parsed:** {date.today().isoformat()}  ",
        "\n---\n",
    ]

    for chunk in chunks:
        lines.append(f"## [{chunk['chunk_id']}] {chunk['heading']}\n")
        lines.append(f"*Pages {chunk['page_start']}-{chunk['page_end']} | {chunk['char_count']} chars*\n")
        lines.append(chunk['content'][:3000])
        if chunk['char_count'] > 3000:
            lines.append(f"\n\n... (truncated, full content: {chunk['char_count']} chars)")
        lines.append("\n\n---\n")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Write individual chunk files for granular retrieval
    chunks_dir = doc_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    for chunk in chunks:
        chunk_path = chunks_dir / f"{chunk['chunk_id']}.md"
        chunk_lines = [
            f"# {chunk['heading']}\n",
            f"**Chunk ID:** {chunk['chunk_id']}  ",
            f"**Document:** {doc_title}  ",
            f"**Pages:** {chunk['page_start']}-{chunk['page_end']}  ",
            f"**Characters:** {chunk['char_count']}  ",
            "\n---\n",
            chunk['content']
        ]
        chunk_path.write_text("\n".join(chunk_lines), encoding="utf-8")


def build_index_entry(doc_id: str, doc_title: str, pdf_name: str, chunks: list[dict], tags: list[str]) -> dict:
    """Build an index entry for one document."""
    return {
        "doc_id": doc_id,
        "title": doc_title,
        "source_file": pdf_name,
        "topics": tags,
        "chunk_count": len(chunks),
        "total_chars": sum(c["char_count"] for c in chunks),
        "page_count": max((c["page_end"] for c in chunks), default=0),
        "parsed_date": date.today().isoformat(),
        "version": "1.0",
        "superseded_by": None,
        "confidence": "high",
        "chunks": [
            {
                "chunk_id": c["chunk_id"],
                "heading": c["heading"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "char_count": c["char_count"],
                "content_hash": c["content_hash"]
            }
            for c in chunks
        ]
    }


def process_pdf(pdf_path: Path, raw_dir: Path, parsed_dir: Path,
                custom_tags: list[str] = None, chunk_size: int = 5) -> tuple:
    """Process a single PDF file. Returns (index_entry, error) tuple."""
    pdf_name = pdf_path.name
    doc_title = pdf_path.stem
    doc_id = sanitize_filename(pdf_name)

    print(f"\nProcessing: {pdf_name}")
    print(f"  Doc ID: {doc_id}")

    # Copy to raw layer if not already there
    raw_copy = raw_dir / pdf_name
    if not raw_copy.exists():
        shutil.copy2(pdf_path, raw_copy)
        print(f"  Copied to raw/")

    try:
        # Extract text
        pages = extract_text_from_pdf(pdf_path)
        print(f"  Pages extracted: {len(pages)}")

        if not pages or all(not p["text"].strip() for p in pages):
            print(f"  WARNING: No text extracted (possibly scanned/image PDF)")
            return None, {"file": pdf_name, "error": "No text extracted - possibly scanned/image PDF. Try OCR with ocrmypdf."}

        # Chunk
        chunks = chunk_document(pages, doc_id, chunk_size=chunk_size)
        print(f"  Chunks created: {len(chunks)}")

        # Tag
        content_sample = "\n".join(p["text"] for p in pages[:10])
        tags = assign_topic_tags(doc_title, content_sample, custom_tags)
        print(f"  Topics: {tags}")

        # Write parsed markdown
        write_parsed_markdown(parsed_dir, doc_id, doc_title, chunks, tags)
        print(f"  Parsed written to: parsed/{doc_id}/")

        # Build index entry
        entry = build_index_entry(doc_id, doc_title, pdf_name, chunks, tags)
        return entry, None

    except Exception as e:
        print(f"  ERROR: {e}")
        return None, {"file": pdf_name, "error": str(e)}


def write_index(index_dir: Path, catalog: list[dict], errors: list[dict]):
    """Write all index layer files."""
    # Master catalog
    catalog_path = index_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    # Topic index
    topic_index = {}
    for entry in catalog:
        for topic in entry["topics"]:
            if topic not in topic_index:
                topic_index[topic] = []
            topic_index[topic].append({
                "doc_id": entry["doc_id"],
                "title": entry["title"],
                "chunk_count": entry["chunk_count"]
            })

    topic_path = index_dir / "topic_index.json"
    topic_path.write_text(json.dumps(topic_index, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary markdown
    summary_path = index_dir / "SUMMARY.md"
    summary_lines = [
        "# Knowledge Base Summary\n",
        f"**Generated:** {date.today().isoformat()}  ",
        f"**Documents:** {len(catalog)}  ",
        f"**Total Chunks:** {sum(e['chunk_count'] for e in catalog)}  ",
        f"**Topics:** {', '.join(sorted(topic_index.keys()))}  ",
        "\n---\n",
        "## Documents\n",
        "| # | Document | Topics | Chunks | Pages | Chars |",
        "|---|----------|--------|--------|-------|-------|",
    ]
    for i, entry in enumerate(catalog, 1):
        summary_lines.append(
            f"| {i} | {entry['title']} | {', '.join(entry['topics'])} | "
            f"{entry['chunk_count']} | {entry['page_count']} | {entry['total_chars']:,} |"
        )

    if errors:
        summary_lines.append("\n\n## Errors\n")
        for err in errors:
            summary_lines.append(f"- **{err['file']}**: {err['error']}")

    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    # Errors log
    if errors:
        error_path = index_dir / "errors.json"
        error_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")

    return topic_index


def create_decision_log(decisions_dir: Path):
    """Create decision log template if it doesn't exist."""
    decision_log = decisions_dir / "decision_log.md"
    if not decision_log.exists():
        decision_log.write_text(
            "# Decision Log\n\n"
            "Record interpretations, conflict resolutions, and choices not explicitly stated in source documents.\n\n"
            "| Date | Topic | Decision | Rationale | Source Docs |\n"
            "|------|-------|----------|-----------|-------------|\n",
            encoding="utf-8"
        )


def parse_args(argv: list[str]) -> dict:
    """Parse command-line arguments."""
    args = {
        "source": None,
        "output": None,
        "batch": False,
        "tags": [],
        "chunk_size": 5,
    }

    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--batch":
            args["batch"] = True
        elif arg == "--tags" and i + 1 < len(argv):
            i += 1
            args["tags"] = [t.strip() for t in argv[i].split(",") if t.strip()]
        elif arg == "--chunk-size" and i + 1 < len(argv):
            i += 1
            try:
                args["chunk_size"] = int(argv[i])
            except ValueError:
                print(f"WARNING: Invalid chunk-size '{argv[i]}', using default 5")
        elif not arg.startswith("--"):
            positional.append(arg)
        i += 1

    if len(positional) >= 1:
        args["source"] = positional[0]
    if len(positional) >= 2:
        args["output"] = positional[1]

    return args


def main():
    if len(sys.argv) < 3:
        print("Universal PDF Knowledge Base Builder")
        print("=" * 40)
        print()
        print("Usage: python build_kb.py <pdf_path_or_folder> <output_folder> [options]")
        print()
        print("Arguments:")
        print("  pdf_path_or_folder  Path to a single PDF or a folder containing PDFs")
        print("  output_folder       Where to create the 4-layer knowledge base")
        print()
        print("Options:")
        print("  --batch             Process all PDFs in the given folder")
        print('  --tags "t1,t2,t3"   Add custom topic tags to all documents')
        print("  --chunk-size N      Pages per chunk when no headings detected (default: 5)")
        print()
        print("Examples:")
        print('  python build_kb.py report.pdf ./my_kb')
        print('  python build_kb.py ./pdf_folder ./my_kb --batch')
        print('  python build_kb.py spec.pdf ./kb --tags "api,v2" --chunk-size 3')
        sys.exit(1)

    args = parse_args(sys.argv[1:])
    source = Path(args["source"]).resolve()
    output_dir = Path(args["output"]).resolve()
    batch_mode = args["batch"]
    custom_tags = args["tags"]
    chunk_size = args["chunk_size"]

    # Determine PDF list
    if source.is_dir() or batch_mode:
        if not source.is_dir():
            print(f"ERROR: {source} is not a directory (--batch requires a folder)")
            sys.exit(1)
        pdf_files = sorted(source.glob("*.pdf"))
        if not pdf_files:
            print(f"ERROR: No PDF files found in {source}")
            sys.exit(1)
    elif source.is_file() and source.suffix.lower() == ".pdf":
        pdf_files = [source]
    else:
        print(f"ERROR: {source} is not a valid PDF file or directory")
        sys.exit(1)

    print(f"Universal PDF Knowledge Base Builder")
    print(f"{'=' * 40}")
    print(f"PDF source: {source}")
    print(f"Output folder: {output_dir}")
    print(f"Files to process: {len(pdf_files)}")
    print(f"Mode: {'batch' if batch_mode or len(pdf_files) > 1 else 'single'}")
    print(f"Chunk size: {chunk_size} pages")
    if custom_tags:
        print(f"Custom tags: {custom_tags}")

    # Create 4-layer structure
    raw_dir = output_dir / "raw"
    parsed_dir = output_dir / "parsed"
    index_dir = output_dir / "index"
    decisions_dir = output_dir / "decisions"

    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    decisions_dir.mkdir(parents=True, exist_ok=True)

    # Process each PDF
    catalog = []
    errors = []

    for pdf_path in pdf_files:
        entry, error = process_pdf(pdf_path, raw_dir, parsed_dir,
                                   custom_tags=custom_tags, chunk_size=chunk_size)
        if entry:
            catalog.append(entry)
        if error:
            errors.append(error)

    # Write index layer
    print(f"\n{'=' * 60}")
    topic_index = write_index(index_dir, catalog, errors)

    # Create decision log
    create_decision_log(decisions_dir)

    # Final report
    print(f"Knowledge base built: {output_dir}")
    print(f"Documents processed: {len(catalog)}")
    print(f"Total chunks: {sum(e['chunk_count'] for e in catalog)}")
    print(f"Topics: {', '.join(sorted(topic_index.keys()))}")
    if errors:
        print(f"Errors: {len(errors)}")
        for err in errors:
            print(f"  - {err['file']}: {err['error']}")
    print(f"\nFiles written:")
    print(f"  index/catalog.json")
    print(f"  index/topic_index.json")
    print(f"  index/SUMMARY.md")
    print(f"  decisions/decision_log.md")
    for entry in catalog:
        print(f"  parsed/{entry['doc_id']}/{entry['doc_id']}.md ({entry['chunk_count']} chunks)")


if __name__ == "__main__":
    main()
