# Rollable tables

Random tables from your own PDF books seed variation into the story. For each scene the narrator
gets table results it has to work in; the opening scene rolls two, every later scene rolls one.

## How it works

1. **Index (offline, once).** `tools/import_rollable_tables.py` reads the PDFs in
   `server/storage/rollable_tables/source/` and writes `server/storage/rollable_tables/index.json`.
   Needs poppler (`pdftotext`, `pdftoppm`). Both the PDFs and the index are gitignored (copyrighted, local only).
   ```
   python tools/import_rollable_tables.py            # default source dir; scanned PDFs are OCR'd
   python tools/import_rollable_tables.py /path/to/pdfs
   python tools/import_rollable_tables.py --no-ocr   # skip scanned PDFs
   ```
   **Scanned PDFs** (no text layer, detected automatically) are rendered at 150 dpi and read through
   Steward's OCR nodes (`STEWARD_HOST`, default `http://127.0.0.1:5555`; ColemanPC then HeatherPC,
   see DOCUMENTATION.md). Each page is OCR'd twice: the sparse pass reads body text but drops isolated
   single-digit die numbers, so pages with a number gutter get a block-layout pass whose numbers are
   merged in. Pages are cached in `server/storage/rollable_tables/ocr_cache/`, so an interrupted
   import resumes; delete that folder to force a re-read. A full first run over the three scanned
   books takes roughly an hour on the Jetson (page rendering dominates); later runs take about a minute.
2. **Extraction.** `server/agents/rollable_tables_extract.py` finds a gutter of die results
   (`1`, `2-3`, ...) in word coordinates, keeps it only if it counts up like a real die, joins
   tables split across columns, and reads the lead-in ("The party encounters..."). For scans it also
   splits a single d100 gutter into its separate result columns (one table each, named from the
   column header), chains a table across pages, repairs misread/missing gutter numbers from row
   spacing, and splits glued articles ("Agroup") using the system word list.
   `rollable_tables.build_tables` then drops rule text (DCs, damage, page references), rows tied
   to one adventure (Door 9, named NPCs) and PDF artefacts, and tags each table with a category.
3. **Rolling.** `roll_for_scene` picks a table that suits the scene type (dialogue favours NPC and
   rumour tables, travel favours encounters, ...) and context, *actually rolls its die*, and reads the
   matching row. Recently used tables are de-prioritised.
4. **Weaving.** `narrative.generate_narrative` rolls once per scene (so retries see the same result)
   and puts the result in the system prompt and the user message. If the first draft ignores a roll it
   gets one rescue retry; after that the draft is accepted so a roll can never force the template
   fallback. `score_detail.table_rolls` / `table_rolls_woven` record what was rolled.

Story Truth and the players' own actions stay authoritative: the prompt tells the narrator to adapt
or reskin a result to fit, never to override what is established, and never to mention dice or tables.

## Controls

- `TAVERNTAILS_ROLLABLE_TABLES=0` disables rolling globally.
- `campaign_contract["random_tables"] = false` opts one campaign out.
- Non-fantasy genres (sci-fi, cyberpunk, modern, western, ...) are skipped automatically.
- No index file means no rolls, silently.

## Known limits

- Extraction is heuristic: expect some odd rows. The row filters err toward dropping (rule text,
  adventure-specific names, fragments, lists of bare words), so only about 3,300 of the rows are kept.
- OCR sometimes loses the first few rows of a table that begins at the foot of a page; those rows are
  left blank and never rolled (the die still covers them, and the nearest surviving row is used).
- Legendary Dragons and the Random Encounters map pack contain no numbered tables to extract.
- The player-facing Proactive Roleplaying handbook is excluded on purpose.
