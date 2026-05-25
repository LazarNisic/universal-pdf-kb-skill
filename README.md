# Universal PDF Knowledge Base Builder

A GitHub Copilot skill that converts any PDF document into a structured, searchable 4-layer knowledge base.

## Overview

This skill parses PDF files and produces a self-contained folder of Markdown and JSON files that AI agents (Copilot, ChatGPT, Claude, etc.) can search and reference without re-reading the original PDF.

It is **domain-agnostic** — works equally well with technical documentation, legal contracts, academic papers, medical literature, business reports, specifications, manuals, or any other PDF content.

## The 4-Layer Knowledge System

| Layer | Folder | Contents | Purpose |
|-------|--------|----------|---------|
| 1. Raw | `raw/` | Original PDF (copied) | Immutable source of truth |
| 2. Parsed | `parsed/<doc_id>/` | Markdown per section + individual chunks | Human-readable, searchable text |
| 3. Index | `index/` | `catalog.json`, `topic_index.json`, `SUMMARY.md` | Fast lookup, metadata, topic routing |
| 4. Decisions | `decisions/` | `decision_log.md` | Track interpretations and conflict resolutions |

## Installation

### As a Copilot Skill

Copy the `universal-pdf-kb` folder into your `.copilot/skills/` directory:

```
.copilot/
└── skills/
    └── universal-pdf-kb/
        ├── SKILL.md
        ├── README.md
        └── scripts/
            └── build_kb.py
```

### Python Dependencies

```bash
pip install pypdf pdfplumber
```

- `pypdf` — Primary PDF text extraction (fast)
- `pdfplumber` — Fallback with better table/layout support (optional but recommended)

## Usage

### Via Copilot (Natural Language)

Simply ask Copilot:
- "Build a knowledge base from this PDF"
- "Parse this PDF into searchable chunks"
- "Create a KB from the documents in this folder"
- "Index this document for future retrieval"

### Via Command Line

**Single PDF:**
```bash
python scripts/build_kb.py report.pdf ./my_knowledge_base
```

**Batch mode (folder of PDFs):**
```bash
python scripts/build_kb.py ./pdf_folder ./my_knowledge_base --batch
```

**With options:**
```bash
python scripts/build_kb.py spec.pdf ./kb --tags "api,v2" --chunk-size 3
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--batch` | Process all PDFs in the given folder | Off |
| `--tags "t1,t2,t3"` | Add custom topic tags to all documents | Auto-detect |
| `--chunk-size N` | Pages per chunk when no headings detected | 5 |

## Output Structure

```
my_knowledge_base/
├── raw/
│   └── original_document.pdf
├── parsed/
│   └── original_document/
│       ├── original_document.md        # Full document overview
│       └── chunks/
│           ├── original_document_chunk_001.md
│           ├── original_document_chunk_002.md
│           └── ...
├── index/
│   ├── catalog.json        # Full metadata per chunk
│   ├── topic_index.json    # Documents grouped by topic
│   └── SUMMARY.md          # Human-readable overview
└── decisions/
    └── decision_log.md     # Template for recording interpretations
```

## How Chunking Works

The builder tries multiple heading detection strategies in order:

1. **Numbered sections** — `1.2 Title`, `3.4.1 Subtitle`
2. **Markdown headings** — `# Title`, `## Section`
3. **ALL-CAPS headings** — `INTRODUCTION`, `METHODOLOGY`
4. **Page groups** — Falls back to grouping N pages together (configurable via `--chunk-size`)

## Topic Auto-Detection

The builder automatically assigns topic tags based on document title and content keywords. It covers 35+ topic categories across:

- **Technical:** software, architecture, database, networking, security, cloud, devops
- **Science:** research, mathematics, physics, chemistry, biology, medicine
- **Business:** finance, accounting, strategy, management, marketing, HR
- **Legal:** legal, contract, intellectual property, privacy
- **Education:** education, training
- **Engineering:** mechanical, electrical, civil
- **Government:** policy, environmental
- **Documentation types:** specification, manual, report, reference, installation, configuration, release, troubleshooting

Custom tags can be added via the `--tags` option.

## Retrieval Pattern (for AI Agents)

Once built, use this pattern to query the knowledge base:

1. Read `index/SUMMARY.md` to identify relevant documents
2. Use `index/topic_index.json` to find documents by topic
3. Use `index/catalog.json` for detailed chunk metadata
4. Read specific chunks in `parsed/<doc_id>/chunks/<chunk_id>.md`
5. Record interpretation decisions in `decisions/decision_log.md`

## Handling Image-Only PDFs

If a PDF contains scanned pages (no extractable text), the builder will report it in `index/errors.json`. To fix:

```bash
# Install OCR tool
pip install ocrmypdf

# Convert scanned PDF to searchable PDF
ocrmypdf input.pdf output.pdf

# Then re-run the knowledge base builder
python scripts/build_kb.py output.pdf ./my_kb
```

## Requirements

- Python 3.10+
- `pypdf` (required) or `pdfplumber` (fallback)
- No internet connection required — runs entirely locally

## License

MIT
