---
name: universal-pdf-kb
description: "Build a general-purpose 4-layer knowledge base from any PDF document. Use this skill whenever the user wants to build a knowledge base from a PDF, create structured knowledge from a document, parse a PDF into searchable chunks, index a PDF for future retrieval, or convert a PDF into a knowledge layer. Also trigger when the user says 'build knowledge base', 'create KB from PDF', 'parse PDF into chunks', 'index this document', '4-layer knowledge', or mentions wanting to make a PDF searchable/queryable by Copilot. If the user has multiple PDFs to process, run this for each one or in batch mode. Works with any domain — technical, legal, medical, academic, business, or any other type of document."
---

# Universal PDF Knowledge Base Builder

## Purpose

Convert any PDF file into a 4-layer knowledge system that enables structured retrieval, citation tracking, and version management. The output is a self-contained folder of Markdown and JSON files that Copilot (or any agent) can search and reference without re-reading the original PDF.

This skill is domain-agnostic — it works with technical documentation, legal contracts, academic papers, medical literature, business reports, manuals, specifications, or any other PDF content.

## The 4 Layers

| Layer | Folder | Contents | Purpose |
|-------|--------|----------|---------|
| 1. Raw | `raw/` | Original PDF (copied) | Immutable source of truth |
| 2. Parsed | `parsed/<doc_id>/` | Markdown per section + individual chunk files | Human-readable, searchable text |
| 3. Index | `index/` | `catalog.json`, `topic_index.json`, `SUMMARY.md` | Fast lookup, metadata, topic routing |
| 4. Decisions | `decisions/` | `decision_log.md` | Track interpretations and conflict resolutions |

## Prerequisites

- Python 3.10+
- `pypdf` package installed (`pip install pypdf`)
- Optional: `pdfplumber` for better table/layout extraction (`pip install pdfplumber`)

If neither package is installed, the script will prompt the user to install them.

## Workflow

### Step 1: Determine Inputs

Gather from the user:
- **PDF file path** — the source document (required)
- **Output folder** — where the knowledge base should be created (default: a `knowledge_base/` folder next to the PDF, or a user-specified location)
- **Custom topic tags** — optional extra tags to apply beyond auto-detection

If the user provides a folder of PDFs, process each one in sequence (batch mode).

### Step 2: Create Folder Structure

Create the output directory with the 4-layer structure:

```
<output_folder>/
├── raw/           ← copy or link the original PDF here
├── parsed/        ← generated Markdown chunks go here
│   └── <doc_id>/
│       ├── <doc_id>.md         ← full document with all chunks
│       └── chunks/
│           ├── <doc_id>_chunk_001.md
│           ├── <doc_id>_chunk_002.md
│           └── ...
├── index/         ← catalog and topic index
│   ├── catalog.json
│   ├── topic_index.json
│   └── SUMMARY.md
└── decisions/     ← manual decision log
    └── decision_log.md
```

### Step 3: Locate and Run the Build Script

The build script is located at `scripts/build_kb.py` relative to this skill file.

To find the script path dynamically, use the skill's own directory:

```powershell
# The script is at: <this_skill_directory>/scripts/build_kb.py
python "<this_skill_directory>/scripts/build_kb.py" "<pdf_path>" "<output_folder>"
```

For batch mode (entire folder of PDFs):
```powershell
python "<this_skill_directory>/scripts/build_kb.py" "<folder_with_pdfs>" "<output_folder>" --batch
```

Optional flags:
- `--tags "tag1,tag2,tag3"` — Add custom topic tags to all documents
- `--chunk-size N` — Override default chunk size in pages (default: 5)

The script will:
1. Copy the PDF into `raw/`
2. Extract text page-by-page (pypdf primary, pdfplumber fallback)
3. Chunk by section headings (numbered sections like "1.2 Title", or Markdown-style `#` headings) — falls back to page groups if no headings detected
4. Auto-assign topic tags based on title and content keywords (general-purpose detection)
5. Write parsed Markdown (full doc + individual chunk files)
6. Build `catalog.json` with full metadata per chunk (ID, heading, pages, char count, content hash)
7. Build `topic_index.json` grouped by topic
8. Write `SUMMARY.md` for human review
9. Create `decision_log.md` template

### Step 4: Review Output

After the script completes, verify:
1. Check `index/SUMMARY.md` — confirms document count, chunk count, topics detected
2. If any PDFs failed (scanned/image-only), they appear in `index/errors.json`
3. Spot-check a parsed chunk file to confirm text quality

If text quality is poor (garbled, missing content), the PDF may be image-based. Suggest OCR preprocessing with `ocrmypdf` before re-running.

### Step 5: Report to User

Provide a summary:
- Documents processed (with/without errors)
- Total chunks created
- Topics detected
- Any issues or recommendations

## Retrieval Instructions (for agents using the KB)

Once a knowledge base is built, use this retrieval pattern:

1. Start with `index/SUMMARY.md` to identify relevant documents.
2. Use `index/topic_index.json` to find documents by topic.
3. Use `index/catalog.json` for detailed chunk metadata.
4. Read specific chunks in `parsed/<doc_id>/chunks/<chunk_id>.md`.
5. Record any interpretation decisions in `decisions/decision_log.md`.
