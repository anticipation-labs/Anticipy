# Anticipy engineer field handoff

Read the [64-page PDF](../../output/pdf/Anticipy-engineer-field-brief-500-scenarios.pdf), then copy the [500-row result sheet](Anticipy-500-scenario-result-sheet.csv) to a new file for your results.

The assignment is to install Anticipy on your own iPhone, use it in ordinary life, trace failures through the harness, repair causes and prove the shipped experience. The first 14 pages are the working brief and index. The remaining 50 pages contain 500 distinct proposed cases in 25 categories, each with a setup, an action/input and an observable expected result.

## Start tonight

1. Read `HARNESS-LAWS.md`, `CLAUDE.md` and `AGENTS.md` from `cloudflare-backend`; establish an isolated checkout or worktree before concurrent repairs.
2. Confirm your own TestFlight invitation, installed build, test owner, Chrome extension and provider accounts. The release baseline in this handoff is dated evidence, not a fresh inspection of your devices.
3. Complete the first-hour phone journeys in the brief. Begin with the first two cases in each category: 50 initial checks. Start all journeys from their stated real surface; record injected faults and simulated time separately.
4. Reproduce failures before changing code. Fix missing context and general behavior, not strings from this catalogue. Recheck the original failure and unseen variations.
5. Leave an issue ledger, a recorded phone demonstration, completed case results and an independently verified release receipt.

## What these files contain

- `brief.md`: editable source for the practical brief, current evidence boundaries, architecture, overnight allocation and acceptance requirements.
- `scenarios.txt`: authored test catalogue, 25 categories with 20 cases each.
- `scenarios.json`: machine-readable catalogue with stable IDs `001` through `500`.
- `Anticipy-500-scenario-result-sheet.csv`: editable template, initially **NOT RUN** for all 500 cases. Fields include observations, evidence, failure cause, fix commit, retest, latency, model cost, versions and tester.
- `build_brief.py`: reproducible PDF and catalogue exporter. Requires Python, ReportLab and pypdf. Uses the fonts bundled with ReportLab.
- `validation.json`: document QA receipt; this proves the document was checked, not that the product passed these scenarios.

The last four cases in each category form 100 reserved cases for initial evaluation outside prompt-tuning examples. Once a failure informs a fix, retain it as a regression and write new reserved variations.

**No new product tests were executed while authoring this handoff.** Prior fifteen-person lab evidence and its limits are linked inside the brief. This catalogue is not an automated test runner. Missing capabilities, blocked cases and unrun cases must remain visible; a reassuring reply does not count as a completed task.

## Rebuild

From the repository root, with the Python dependencies installed:

```sh
python3 docs/engineer-handoff-2026-09-07/build_brief.py
```

The builder regenerates the blank CSV and JSON templates; keep your completed results in a separately named file. It checks category/case counts, unique inputs, page overflow and the presence of every case exactly once. Render the resulting PDF with Poppler and inspect all pages after changing layout or content. The delivered version was rendered and visually checked across all 64 pages, with full-page checks of dense text and case layouts.
