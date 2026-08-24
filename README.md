# DOL foreign labor certification disclosure pipeline

Pulls LCA (H-1B, H-1B1, E-3) and PERM case disclosure data from DOL OFLC,
normalizes both into one table, and reports row counts so a rerun can be
sanity-checked. Built to be rerun each quarter when DOL publishes a new
release — see [Rerunning it](#rerunning-it-each-quarter).

## Important: read this before the first real run

This pipeline was built in a sandboxed session with **no network access to
dol.gov** (blocked by org egress policy — confirmed via direct `curl`, not
assumed). That means two things could not be done during the build and need
a first pass from you, or from a session with real internet access:

1. **Source URLs weren't verified live.** The pipeline doesn't hardcode
   URLs — it scrapes
   [the DOL performance page](https://www.dol.gov/agencies/eta/foreign-labor/performance)
   for LCA/PERM disclosure and record-layout links (`src/discover_sources.py`)
   and picks the most recent fiscal years automatically. That scraper is
   written generically (any `<a href>` ending in `.xlsx`/`.xls`/`.pdf`,
   classified by filename/link-text keywords) so it doesn't depend on guessing
   the page's exact structure, but it has never run against the live page.
   If it doesn't find the right files on first run, either fix the
   classification rules in `discover_sources.py` or — faster — list the
   files by hand in `config/sources_override.yaml`, which always takes
   priority over scraping.

2. **Column names weren't verified against the real record layout PDFs**,
   especially for `PERM_REVISED` (the new ETA-9089 form, rolled out 2025).
   `config/column_aliases.yaml` is seeded with the DOL LCA/PERM schema as
   it's been stable since the FY2020 FLAG-system rollout, but the revised
   PERM field names are a best-effort guess flagged `UNVERIFIED` in that
   file. **The pipeline never silently guesses a column** — if a required
   field can't be matched to a real header, it raises
   `ColumnResolutionError` with the file's actual headers and the closest
   fuzzy matches, and tells you exactly which line of
   `column_aliases.yaml` to fix. Expect this to fire at least once on the
   first live run against `PERM_REVISED` — check the downloaded layout PDF
   in `data/raw/layouts/` and add the correct name.

Everything downstream of column resolution — wage annualization, status
classification, fiscal-year math, the combine/write/report step — is
covered by unit tests with synthetic data (`tests/`, 30 tests, all passing)
and doesn't depend on dol.gov being reachable, so that part is verified.

## What it does

1. **Discover** (`src/discover_sources.py`): scrape the DOL performance page
   for LCA disclosure files (last 3 fiscal years), PERM disclosure files
   (last 2 fiscal years, both the legacy and revised-ETA-9089 layouts where
   both exist), and their record-layout PDFs. `config/sources_override.yaml`
   can pin exact URLs instead.
2. **Download** (`src/download.py`): fetch everything into `data/raw/`
   (data files) and `data/raw/layouts/` (record layout PDFs, for reference).
   Writes `data/raw/download_manifest.json`.
3. **Parse + normalize** (`src/parse_lca.py`, `src/parse_perm.py`,
   `src/normalize.py`): for each file, resolve DOL's actual column headers
   to canonical fields via `src/columns.py` (alias-matched, case/whitespace
   insensitive, fails loudly on a miss — never guesses), then transform to
   the common schema below.
4. **Combine + write**: concatenate all normalized files and write
   `data/processed/dol_filings.parquet` and `.csv`.
5. **Report** (`src/report.py`): row counts per source file and per
   fiscal-year × program, written to `data/processed/run_report_latest.json`
   and printed to the console.

## Output schema

One row per case, one file (`dol_filings.parquet` / `.csv`):

| column | notes |
|---|---|
| `employer_raw` | as filed, no normalization yet (that's a separate pass) |
| `program` | `LCA` or `PERM` |
| `fiscal_year` | federal FY (Oct 1–Sep 30), derived from `decision_date` |
| `decision_date` | parsed date |
| `case_status` | normalized: `CERTIFIED`, `CERTIFIED-WITHDRAWN`, `DENIED`, `WITHDRAWN` |
| `job_title_raw` | as filed |
| `soc_code` | as filed |
| `worksite_city` / `worksite_state` | as filed |
| `wage_offered` | **annualized** — see below |
| `wage_unit` | original unit of pay, kept for audit |
| `wage_level` | prevailing wage level (I–IV), as filed |
| `full_time_flag` | `True`/`False`/`None` |
| `is_denied_or_withdrawn` | `True` for `DENIED`/`WITHDRAWN` rows |
| `source_file` | which downloaded file the row came from |

Rows with a `case_status` other than those four are dropped (disclosure
files shouldn't contain anything else — if they do, it's counted in
`dropped_unknown_status` in the report rather than silently kept).

**Main counts vs. flagged rows**: `CERTIFIED` and `CERTIFIED-WITHDRAWN` rows
have `is_denied_or_withdrawn = False`; `DENIED` and `WITHDRAWN` rows have
`is_denied_or_withdrawn = True`. All four are in the same table — filter
`~is_denied_or_withdrawn` for headline/main counts, keep the flag column
around for denial-rate analysis later.

### Wage annualization

`wage_offered` = the "from" wage amount × a multiplier based on
`wage_unit`, falling back to the "to" amount if "from" is missing:

| unit | multiplier |
|---|---|
| Hour | 2080 |
| Week | 52 |
| Bi-Weekly | 26 |
| Semi-Monthly | 24 |
| Month | 12 |
| Year | 1 |

An unrecognized unit or missing amount produces `wage_offered = None`
rather than defaulting to a multiplier of 1, which would silently
understate hourly/weekly/monthly wages. See `src/wage.py`.

## Setup

```bash
cd dol_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running it

```bash
python run_pipeline.py
```

Options:

```bash
python run_pipeline.py --force-download   # re-download even if files already exist in data/raw/
python run_pipeline.py --lca-years 3 --perm-years 2
python run_pipeline.py -v                 # verbose logging
```

On success it prints row counts per source file and per fiscal-year ×
program, and writes:

- `data/processed/dol_filings.parquet` / `.csv` — the combined table
- `data/processed/run_report_latest.json` — the same counts as JSON
- `data/raw/download_manifest.json` — what was downloaded and from where

## Rerunning it each quarter

Just run `python run_pipeline.py` again. Discovery re-scrapes the DOL page
each time, so it naturally picks up whatever fiscal years/quarters are
current — no code or URL edits needed in the normal case. Compare the new
`run_report_latest.json` against the previous run's row counts as a sanity
check (a big unexplained drop usually means a column stopped resolving and
rows got dropped, not that filings actually dropped).

If DOL changes a filename pattern enough that discovery fails, or renames
a column enough that resolution fails, the pipeline stops with a specific,
actionable error — fix the one thing it names (a classification rule, an
override URL, or one alias entry) and rerun; it doesn't need a rewrite.

## Testing

```bash
python -m pytest tests/ -v
```

30 tests cover wage annualization, status classification, fiscal-year math,
column alias resolution (including the "DOL renamed a column and the alias
isn't in the config yet" failure path), and a full synthetic-file
integration test of the download→parse→normalize→combine→write→report path.

## Employer name normalization (Session 2)

Building on the row-level table above, `src/employer_normalize.py`,
`src/employer_match.py`, and `src/employer_top_n.py` collapse the many
legal-entity variants of one employer down to something matchable, and let
free-text user input ("Amazon") resolve against it.

- **`normalize_employer_name()`**: uppercase, punctuation → space (not
  deleted — `AMAZON.COM` must not fuse into `AMAZONCOM`), collapse
  whitespace, then repeatedly strip trailing legal-suffix tokens (`INC`,
  `LLC`, `CORP`, `SERVICES`, `HOLDINGS`, `AND SUBSIDIARIES`, etc. — see
  `_SUFFIX_PHRASES` in that file) so stacked suffixes like `... SERVICES
  INC` fully strip, not just the last token.
- **`src/employer_top_n.py`**: ranks normalized employers by main-count
  filing volume (denied/withdrawn excluded) and writes
  `data/processed/top_500_employers.csv` — the list to hand-build
  `config/employer_aliases.yaml` from. **That config ships empty** because
  this pipeline has never run against real DOL data in this sandbox (same
  network constraint as Session 1) — there's no real filing volume to rank
  yet. Run `run_pipeline.py` for real, then `write_top_employers()`, then
  fill in the alias file by hand.
- **`config/staffing_consulting_firms.yaml`**: a seeded (not empty) map of
  well-known staffing/IT-consulting firms and their common abbreviations
  (TCS → Tata Consultancy Services, Infosys, Cognizant, Deloitte, Wipro,
  HCL, Capgemini, Accenture, and others) — checked before fuzzy matching so
  these get flagged `is_staffing_or_consulting=True` rather than scored
  like a direct employer. Expand it by hand the same way, from
  `top_500_employers.csv` once that exists.
- **`match_employer()`**: exact match against the staffing map, then the
  alias map, then `rapidfuzz.fuzz.token_set_ratio` fuzzy matching (default
  threshold 90/100) against the combined pool. Below threshold, it returns
  `matched=False` plus the 5 closest candidates — **it never guesses**. A
  confident wrong answer ("this company doesn't sponsor" when it does) is
  worse than admitting uncertainty.

Demo: `python scripts/demo_session2_employer_match.py` runs the exact 10
inputs from the build brief (Amazon, Google, Deloitte, TCS, Infosys, Meta,
JPMorgan, Capital One, Cognizant, Walmart) against a small **synthetic**
alias-map fixture (clearly labeled in the script — real filer-name
variants for these companies, not pulled from a live file, since none was
reachable) plus the real staffing/consulting config. All 10 resolve; the 4
staffing/consulting firms come back flagged. Tests in
`tests/test_employer_normalize.py`, `tests/test_employer_match.py`, and
`tests/test_employer_top_n.py` cover the same ground without needing the
demo fixture.

## Role bucket classification (Session 3)

`src/role_taxonomy.py` classifies each filing into one of 16 role buckets
and pulls seniority into its own column. Everything is configured in
`config/role_taxonomy.yaml` — synonyms and SOC mappings are editable
without touching code.

**Seniority first**: `senior`, `sr`, `lead`, `staff`, `principal`,
`junior`, `jr`, `associate`, `entry`/`entry level` are stripped out of the
title into a `seniority` column — kept, not discarded, since it feeds the
"do they file at this level" signal later. `Sr. Data Engineer` → seniority
`senior`, title `DATA ENGINEER`.

**Then the bucket**, in this order (recorded per row in
`role_match_source` so a review pass can see *why* something landed where
it did):

1. `soc_clean` — SOC codes that map unambiguously to one bucket (15-2051
   Data Scientists, 17-2141 Mechanical Engineers). These win outright.
2. `keyword` — phrase match against the stripped title, **longest phrase
   first**, so `DATA ENGINEER` beats a bare `ENGINEER` and `MACHINE
   LEARNING ENGINEER` beats `DATA`.
3. `soc_coarse` — broad SOC codes (15-1252 Software Developers) used
   *only* as a fallback default. This ordering is the point: it lets a
   title keyword refine within a coarse SOC instead of being overruled by
   it, so `Sr. QA Automation Engineer` filed under 15-1252 correctly lands
   in `qa_engineer`, not `software_engineer` — exactly the distinction
   signal 2 depends on.
4. `other` — everything else, logged for review.

SOC codes are compared on digits only, so `15-2051`, `15-2051.00`, and
`152051` all match the same rule.

**The review loop**: every pipeline run writes
`data/processed/unmatched_titles_top_100.csv` — the most common titles
that fell through to `other`, with their SOC codes. Per the build brief,
reviewing that list once and hand-adding the top entries to
`config/role_taxonomy.yaml` is worth more than any cleverer matching
algorithm. Each run also writes `top_500_employers.csv` for the employer
alias pass described above.

## What the real data turned out to be

Verified 2026-08-24 via `--discover-only` and `--report-headers` on a GitHub
Actions runner (dol.gov is unreachable from the environment this was written
in). Recorded here because several of these contradict what the build brief
and the filenames would lead you to expect.

**Quarterly files are cumulative, not incremental.** OFLC publishes a
year-to-date file each quarter: the FY2026 Q3 file covers Oct 1 2025 –
Jun 30 2026. Concatenating Q1–Q4 of one fiscal year would have counted
early-year cases up to four times and inflated every employer's filing
volume — the single number this product reports. Source selection now keeps
only the newest release per fiscal year, and `case_number` is de-duplicated
after the concat as a backstop.

**The current window contains no legacy-layout PERM file.** The brief says
PERM is split in two because of the revised ETA-9089, and it was — but only
through FY2024. `PERM_Disclosure_Data_New_Form_FY2024_Q4.xlsx` is the
revised form for FY2024; by FY2025 OFLC folded everything onto the revised
form and dropped the `New_Form` suffix. `PERM_Disclosure_Data_FY2025_Q4` and
`..._FY2026_Q3` therefore carry revised-form columns despite filenames
suggesting otherwise. **The filename is not a reliable signal of layout**,
so both file kinds share one alias set.

**The revised ETA-9089 has no prevailing-wage-level column.** Signal 4
(level distribution) is LCA-only. For PERM rows `wage_level` is null — a
real gap in the source data, not a parsing failure, and worth stating as
such wherever the UI shows level.

**The FY2024 New_Form PERM file has no SOC code column at all.** Role
classification falls back to job-title keywords for those rows, which the
taxonomy already does by design.

**LCA needed no changes.** 98 columns, identical across FY2024 Q4, FY2025 Q4
and FY2026 Q3; every alias resolved first try.

**Volume and capacity.** 1.18 GB across the six selected files, against a
runner with 15 GB RAM, 145 GB disk, 4 CPUs. Memory was never the constraint.

## Known limitations / next steps

- The five signals are a follow-on pass (Session 4 in the build brief),
  not part of this pipeline yet.
- The role taxonomy's synonym lists are a reasonable first pass but have
  never been reviewed against real filing titles — that's what the
  `unmatched_titles_top_100.csv` loop above is for, after the first real
  run.
- `PERM_REVISED` column aliases are unverified against the live record
  layout PDF (see above) — expect to fix this on first real run.
- Discovery has never run against the live DOL page — same caveat.
- `config/employer_aliases.yaml` (the real top-500 alias map) is empty
  until the pipeline has run against real data once — see above.
- USCIS H-1B Employer Data Hub (approvals/denials) isn't pulled here; it's
  a separate source for a later pass (signal 5 in the build brief).
