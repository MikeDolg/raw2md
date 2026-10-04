# Quality evaluation

Quality evaluation is a stage after cleaning, and it always runs. It checks the
result with deterministic rules and writes the verdict into the header:
`status: ok` or `status: bad`. The evaluation does not change the text. The
stage has no flag of its own.

## How the evaluation works

The evaluation runs after cleaning, and again after each LLM stage that is on.
Each check looks for one kind of defect in the body. A check that fires goes
into the `issues` field of the header. But not every check sets the status
`bad`:

- a **decisive** check sets `bad` for any number of defects;
- a **threshold** check sets `bad` only when it finds more defects than the
  threshold. Below the threshold, it stays in `issues` with `status: ok`;
- a **signal** never sets `bad`, because a correct document shows the same
  picture.

A threshold has the form "minimum / per 1,000 lines". The result gets `bad`
when the check finds more defects than the minimum and more than the given
number per 1,000 lines of the body. Thus a long book does not get `bad`
for a few defects that would decide the status of a short document. For
example, at the threshold `0 / 2`, one jump of a heading level decides the
status of a 300-line document. In a body of 3,000 lines, only 7 jumps or more
decide the status.

Three checks count the [findings of cleaning](cleaning.md#findings), not the
body. A formula that recognition cut short, a word break, and a flattened block
no longer show in the text. Their number is fixed after cleaning and does not
change after the LLM stages. Therefore post-processing that repaired such a
defect does not remove it from the evaluation.

## Why a result gets `bad`

The checks are in the same order as in `issues`.

### 1. Text

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `text_density` | fewer than 350 characters per page of the source; only for `pdf` and `djvu` | always | 10 pages of a scan gave 2,000 characters |
| `empty_body` | fewer than 20 letters and digits in the whole body | always | a body of one link, `![](fig1.png)` |
| `unreadable_chars` | with 200 letters or more: more than 15% of the letters are neither Latin nor Cyrillic, or more than 15% of the letters are Latin with diacritics while Cyrillic is 5% or more (a wrong encoding) | always | `Ïðèâåò ìèð` instead of `Привет мир` |

### 2. Formulas

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `formulas` | a formula that KaTeX does not render; an empty formula; a formula with a repeat loop | `2 / 1` | `$\frac{a}{b$` |
| `lost_formulas` | the `broken-formula` findings of cleaning: a formula cut because of a repeat, or an unclosed environment | `2 / 1` | `$a_{1}+a_{1}+a_{1}+…$`, which cleaning cut to two terms |
| `math_span_drift` | the number of formulas after the LLM stages differs from the number after cleaning | always | 3 formulas after cleaning, 2 after post-processing |
| `runaway_math` | an unpaired `$$`; a `$$…$$` block with a heading, an image, or a table delimiter row inside; a block longer than 40 lines or 3,000 characters | always | `$$`, `x = 1`, `## Results`, `$$` |
| `greek_units` | a formula of an integer, a space, and two joined Greek letters or more, in a line with Cyrillic text: this is how recognition reads a Russian unit of measurement | always | `$55~\kappa\Gamma$` instead of `55 кГ` |

The pair `\mu\Omega` (microohm) is a real unit, and `greek_units` does not
count it.

### 3. Headings

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `headings` | the level grows by more than one; no space after `#` | `0 / 2` | `# Pumps`, then `### Seals`; `##Seals` |
| `heading_ladder` | a heading not at the level of its group: identical headings (2 or more), a numbered series (3 headings or more: `Chapter 1`, `Chapter 2`, and so on), or headings of the same numbering depth (`2.1.8`) | never | `## Summary` in part 1, `### Summary` in part 2 |
| `flat_ladder` | more than two thirds of the headings (3 at least) sit at one level, but the document sets several ranks with the bookmarks of the source, a printed table of contents, or numbering such as `4.2.1` | `0 / 2` | `## 1 Pumps`, `## 1.1 Body`, `## 1.2 Seals`, `## 2 Valves` |
| `lost_chapters` | a chapter from the table of contents printed in the text that is not among the headings | more than a quarter of the chapters in the table of contents, and more than 1 | the table of contents names 4 chapters; the text has headings for only two |

In `heading_ladder`, the level of a group is the level of most of its headings.
In a tie, it is the higher level. Cleaning repairs these levels with
[the rule for series and repeats](cleaning.md#1-headings). The cases that
remain also occur in a correct document: identical subsections in sections of
different depth.

### 4. Markup

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `tables` | a table row with a different number of cells than the delimiter row; the values of a row in one cell; a table without a header row | `0 / 1` | `\| M8 \| 25 \| 0.9 \|` under a header row of two columns |
| `junk_lines` | more than 2% of the non-empty lines hold only structural symbols | always | the line `•••` |
| `repeats` | one line of up to 80 characters repeats `3 / 1` times or more, and the median gap between the repeats is 3 lines at most | `0 / 1` repeated lines; or one line repeats more than 10 times the minimum | `Press the button.` three times in a row |

Headings, table rows, lines of one formula, and HTML image wrappers
(`<figure>`, `<img>`) do not count as repeats. A single word of up to 3 letters
does not count either, and neither do lines spread evenly through the
document. An example of the last kind is a field in each entry of a catalog.

### 5. Images

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `images` | a `![]()` or `<img>` link to a file that does not exist, is smaller than 512 bytes, or is filled with one color | always | `![](media/fig1.png)` without the file |
| `repeated_images` | one image path occurs 3 times or more | never | a logo on each page |

### 6. Findings of cleaning

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `hyphenation` | the `hyphenation` and `hyphenation-gap` findings: a word break that nothing confirms as a join | `2 / 2` | `The pres-`, `sure rises.` |
| `flattened_blocks` | the `flattened-block`, `flattened-paragraphs`, and `run-in-heading` findings: a flattened block, a broken paragraph, a heading merged with a paragraph | `2 / 2` | `Name`, `Age`, `City`, `John`, `30`, `NYC`, one per line |

The threshold uses the number of body lines after cleaning. Each check counts
its own findings.

### 7. LLM stages

| Check | What it finds | When `bad` | Example |
|---|---|---|---|
| `llm_ocr_markers` | the `[unreadable]` and `[?]` markers that the model puts in LLM-OCR mode | always | `The [unreadable] valve.` |
| `lost_pages` | a page that the model did not recognize in LLM-OCR mode | always | `[page 3 not recognized]` |
| `inspection_coverage` | inspection did not complete all chunks of the document | fewer than half of the chunks are done | 1 chunk of 4 is done |

### Thresholds

Constants in `src/raw2md/quality/evaluator.py` set the thresholds.

| Threshold | Constant |
|---|---|
| 350 characters per page: `text_density` | `_DENSITY_MIN_CHARS_PER_PAGE` |
| 20 letters and digits: `empty_body` | `_EMPTY_BODY_MIN_ALNUM` |
| 200 letters, 15%, 5%: `unreadable_chars` | `_UNREADABLE_MIN_LETTERS`, `_UNREADABLE_MAX_OTHER_SHARE`, `_MOJIBAKE_MAX_ACCENTED_SHARE`, `_MOJIBAKE_MIN_CYRILLIC_SHARE` |
| `2 / 1`: `formulas`, `lost_formulas` | `_FORMULA_BAD_*`, `_LOST_FORMULA_BAD_*` |
| 40 lines, 3,000 characters: `runaway_math` | `_MATH_BLOCK_MAX_LINES`, `_MATH_BLOCK_MAX_CHARS` |
| `0 / 2`: `headings`, `flat_ladder` | `_HEADING_BAD_*`, `_FLAT_LADDER_BAD_*` |
| a quarter, 1: `lost_chapters` | `_LOST_CHAPTER_BAD_SHARE`, `_LOST_CHAPTER_BAD_COUNT` |
| `0 / 1`: `tables` | `_TABLE_BAD_*` |
| 2%: `junk_lines` | `_JUNK_REPAIRABLE_SHARE` |
| 80 characters, `3 / 1`, a median of 3 lines, 10 times: `repeats` | `_REPEAT_MAX_LEN`, `_REPEAT_MIN_*`, `_REPEAT_MAX_MEDIAN_GAP`, `_REPEAT_LOOP_MULTIPLE` |
| `0 / 1` repeated lines: `repeats` | `_REPEAT_BAD_*` |
| 512 bytes: `images` | `_IMAGE_MIN_BYTES` |
| 3 times: `repeated_images` | `_REPEATED_IMAGE_MIN_COUNT` |
| `2 / 2`: `hyphenation`, `flattened_blocks` | `_REPORTED_BAD_*` |
| half of the chunks: `inspection_coverage` | `_INSPECTION_COVERAGE_BAD_SHARE` |

## What the evaluation does not see

The evaluation does not compare the text with the pages of the source. It does
not find misrecognized words and numbers. It also does not find a value that
moved into the adjacent table column without a change in the row width. The
text density covers the whole document, not each page. Therefore one missing
page in a thick book does not change it.

KaTeX checks only the syntax of a formula. A formula with the wrong content but
with correct markup counts as valid.

Recognition garbage spread over a page with mixed Latin and Cyrillic text can
stay below every threshold. The result then gets `ok`.

## Hints in the log

With `status: bad`, the log can suggest the next step. A file gets one hint at
most, and the first row of the table has priority over the second.

| Hint | When it shows | What to do |
|---|---|---|
| `recognition failure suspected for <file>; consider --engine` | any check of the [Text](#1-text) group fired; more than `5 / 2` formulas that do not render; more than `5 / 2` `greek_units` formulas; more than `10 / 4` `hyphenation` and `flattened_blocks` findings together; more than 5% junk lines; a lost page. Only for `pdf` and `djvu`, and not in LLM-OCR mode | recognize the document again in LLM-OCR mode (`-e <model>`) |
| `formatting defects look repairable for <file>; consider --llm-post` | one of the checks `formulas`, `headings`, `tables`, `junk_lines`, `repeats`, `hyphenation`, `flattened_blocks` fired, or an image link points to a missing file. Only if post-processing was off | turn on [post-processing](post.md) (`--llm-post <model>`) |

Post-processing does not repair the LLM-OCR markers, lost formulas, the heading
ladder, lost chapters, or images that exist but are empty. Therefore no hint
covers them.

## How to see the result

Three places show the result of the stage:

- the `status` and `issues` fields in the header of the result: `issues` lists
  all checks that fired, below the threshold too, and appears only when the
  list is not empty;
- the console: with `status: bad`, a warning with the checks and the measured
  values, for example
  `quality bad for book.pdf: headings (3 level/space issues), tables (1 broken rows)`,
  and a hint from the table above; with `status: ok`, the console shows
  nothing;
- the log `~/.raw2md/logs/raw2md.log`: the same lines; with `status: ok` and a
  non-empty `issues`, the line `quality ok for <file>, below threshold: …`; for
  a `pdf` or `djvu` with a text layer, the share of the result words that occur
  in the source, and the share of the source words that reach the result.
  These shares do not change the status.
