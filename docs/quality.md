# Quality evaluation

Quality evaluation is a stage after cleaning, and it always runs. It checks the
result with deterministic rules, gives it a score from 0 to 100, and writes the
verdict into the header: `status: ok` or `status: bad`. The evaluation does not
change the text. The stage has no flag of its own.

## How the evaluation works

The evaluation runs after cleaning, and again after each LLM stage that is on.
Each check looks for one kind of defect in the body. A check is one of three
kinds:

- a **graded** check gives a score from 0 to 100, and the score falls as the
  defect grows;
- a **veto** marks a defect that spoils the whole result: the total score is 0,
  and the status is `bad`;
- a **signal** has no score and never changes the status, because a correct
  document shows the same picture. Only the log shows it.

### The score of a check

A graded check scores `100 * 2^(-x/h)`. Here `x` measures the defect, and the
halving value `h` is the amount of the defect that halves the score. At
`x = h`, the score is 50. At `x = 2h`, it is 25.

Most checks count their defects against a pair "minimum / per 1,000 lines",
such as `1 / 2`. The minimum is the number of defects that do not count. The
halving value is the larger of the minimum and the given number per 1,000
lines of the body. Thus a long book does not lose its score for a few defects
that would spoil a short document. For example, the `headings` check has the
pair `1 / 2`:

| Body | Halving value | Heading jumps | Score |
|---|---|---|---|
| 300 lines | 1 | 1 | 100 |
| 300 lines | 1 | 3 | 25 |
| 3,000 lines | 6 | 1 | 100 |
| 3,000 lines | 6 | 7 | 50 |
| 3,000 lines | 6 | 8 | 45 |

A check keeps the score 100 up to its minimum, and only the defects past the
minimum lower the score. The `formulas` check has the pair `2 / 1`. In a body
of 500 lines, its halving value is 2. Thus 2 invalid formulas give 100, and 4
give 50. A check with the minimum 0, such as `tables`, loses score from the
first defect.

The other checks measure a share. For example, `x` of `junk_lines` is the share
of junk lines, and its halving value is 2%. The tables below give the halving
value of each check.

### The total score

The total score is `100 * 2^(-sum of x/h)` over all graded checks. Thus it is
the product of the check scores, each taken as a fraction of 100. For example,
two checks with the scores 71 and 63 give the total score 45. All checks
weigh the same. A veto sets the total score to 0. A signal does not change it.
The header shows the total score rounded to an integer.

### The status

The status is `ok` when no veto fired and the total score is at least
`ok_score`. The `quality.ok_score` field in
[`settings.json`](reference.md#settingsjson) sets it: 50 by default. Thus one
check at its halving value keeps the status `ok`, and two such checks give
`bad`. A veto gives `bad` at any `ok_score`, 0 included.

### The `issues` field

The `issues` field of the header lists each veto that fired and each check with
a score below 50, in the order of the tables below. A signal never goes into
`issues`. With the default `ok_score`, an `ok` result has no `issues`. A `bad`
result has no `issues` when several checks lower the total score and none of
them is below 50.

### Findings of cleaning

Three checks count the [findings of cleaning](cleaning.md#findings), not the
body. A formula that recognition cut short, a word break, and a flattened block
no longer show in the text. Their number is fixed after cleaning and does not
change after the LLM stages. Therefore post-processing that repaired such a
defect does not remove it from the evaluation.

## The checks

The checks are in the same order as in `issues`. The column "`h` / veto" gives
the halving value of a graded check, or the defect that sets a veto.

### 1. Text

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `text_density` | fewer than 350 characters per page of the source; only for `pdf` and `djvu` | veto | 10 pages of a scan gave 2,000 characters |
| `empty_body` | fewer than 20 letters and digits in the whole body | veto | a body of one link, `![](fig1.png)` |
| `unreadable_chars` | letters of a foreign script and impossible characters, as a share of all letters and impossible characters; only when the body has 200 of them or more. A wrong encoding: more than 15% of the letters are Latin with diacritics while Cyrillic is 5% or more | 15%; a wrong encoding is a veto | `Ïðèâåò ìèð` instead of `Привет мир`; `�` in place of letters |

For `unreadable_chars`, the main script of the body is the script of most of
its letters. Kana, hangul, and CJK ideographs count as one script. A letter is
foreign when its script is not the main script. Latin is never foreign, and
Cyrillic is not foreign in a Latin body. Thus a correct text in Chinese,
Japanese, Greek, or Arabic passes, and so does a Russian text with Latin
formulas. An impossible character is the replacement character `U+FFFD`, a
private use or unassigned code point, or a control character other than a tab
or a line break.

The rule has one known limit. In a Chinese or Japanese text with more Latin
letters than CJK letters, Latin is the main script, and the CJK letters count
as foreign.

### 2. Formulas

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `formulas` | a formula that KaTeX does not render; an empty formula; a formula with a repeat loop | `2 / 1` | `$\frac{a}{b$` |
| `lost_formulas` | the `broken-formula` findings of cleaning: a formula cut because of a repeat, or an unclosed environment | `2 / 1` | `$a_{1}+a_{1}+a_{1}+…$`, which cleaning cut to two terms |
| `math_span_drift` | the number of formulas after the LLM stages differs from the number after cleaning | veto | 3 formulas after cleaning, 2 after post-processing |
| `runaway_math` | an unpaired `$$`; a `$$…$$` block with a heading, an image, or a table delimiter row inside; a block longer than 40 lines or 3,000 characters | veto | `$$`, `x = 1`, `## Results`, `$$` |
| `greek_units` | a formula of an integer, a space, and two joined Greek letters or more, in a line with Cyrillic text: this is how recognition reads a Russian unit of measurement | 1 formula | `$55~\kappa\Gamma$` instead of `55 кГ` |

The pair `\mu\Omega` (microohm) is a real unit, and `greek_units` does not
count it.

### 3. Headings

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `headings` | the level grows by more than one; no space after `#` | `1 / 2` | `# Pumps`, then `### Seals`; `##Seals` |
| `heading_ladder` | a heading not at the level of its group: identical headings (2 or more), a numbered series (3 headings or more: `Chapter 1`, `Chapter 2`, and so on), or headings of the same numbering depth (`2.1.8`) | signal | `## Summary` in part 1, `### Summary` in part 2 |
| `flat_ladder` | more than two thirds of the headings (3 at least) sit at one level, but the document sets several ranks with the bookmarks of the source, a printed table of contents, or numbering such as `4.2.1` | `0 / 2` | `## 1 Pumps`, `## 1.1 Body`, `## 1.2 Seals`, `## 2 Valves` |
| `lost_chapters` | a chapter from the table of contents printed in the text that is not among the headings | the first lost chapter does not count; then a quarter of the chapters in the table of contents, 1 at least | the table of contents names 4 chapters; the text has headings for only two: the score is 50 |

In `lost_chapters`, a chapter is an entry of the top level of the table of
contents, as [cleaning reads it](cleaning.md#1-headings). A heading of a rank
word and a number alone (`## CHAPTER IV.`) joins with the next heading or with
the first line of the paragraph under it, because the source can print the
title on a line of its own. A line that opens a list, a table, or a quote, or
that starts with a digit, does not join.

In `heading_ladder`, the level of a group is the level of most of its headings.
In a tie, it is the higher level. Cleaning repairs these levels with
[the rule for series and repeats](cleaning.md#1-headings). The cases that
remain also occur in a correct document: identical subsections in sections of
different depth.

### 4. Markup

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `tables` | a table row with a different number of cells than the delimiter row; the values of a row in one cell; a table without a header row | `0 / 1` | `\| M8 \| 25 \| 0.9 \|` under a header row of two columns |
| `junk_lines` | non-empty lines that hold only structural symbols, as a share of the non-empty lines | 2% | the line `•••` |
| `repeats` | one line of up to 80 characters repeats `3 / 1` times or more, and the median gap between the repeats is 3 lines at most | `0 / 1` repeated lines; one line that repeats more than 10 times the minimum is a veto | `Press the button.` three times in a row |

Headings, table rows, lines of one formula, and HTML image wrappers
(`<figure>`, `<img>`) do not count as repeats. A single word of up to 3 letters
does not count either, and neither do lines spread evenly through the
document. An example of the last kind is a field in each entry of a catalog.

### 5. Images

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `images` | a `![]()` or `<img>` link to a file that does not exist, is smaller than 512 bytes, or is filled with one color | 1 image | `![](media/fig1.png)` without the file |
| `repeated_images` | one image path occurs 3 times or more | signal | a logo on each page |

### 6. Findings of cleaning

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `hyphenation` | the `hyphenation` and `hyphenation-gap` findings: a word break that nothing confirms as a join | `2 / 2` | `The pres-`, `sure rises.` |
| `flattened_blocks` | the `flattened-block`, `flattened-paragraphs`, and `run-in-heading` findings: a flattened block, a broken paragraph, a heading merged with a paragraph | `2 / 2` | `Name`, `Age`, `City`, `John`, `30`, `NYC`, one per line |

The halving value uses the number of body lines after cleaning. Each check
counts its own findings.

### 7. LLM stages

| Check | What it finds | `h` / veto | Example |
|---|---|---|---|
| `llm_ocr_markers` | the `[unreadable]` and `[?]` markers that the model puts in LLM-OCR mode | 1 marker | `The [unreadable] valve.` |
| `lost_pages` | a page that the model did not recognize in LLM-OCR mode | veto | `[page 3 not recognized]` |
| `inspection_coverage` | inspection did not complete all chunks of the document, as a share of the chunks | half of the chunks not done; fewer than half of the chunks done is a veto | 3 chunks of 4 are done: the score is 71 |

### Thresholds

Constants in `src/raw2md/quality/evaluator.py` set the thresholds.

| Threshold | Constant |
|---|---|
| 50: the default `ok_score` | `DEFAULT_OK_SCORE` |
| 50: a check below it goes into `issues` | `_ISSUE_MAX_SCORE` |
| the weights of the checks, all 1 | `_CHECK_WEIGHTS` |
| 350 characters per page: `text_density` | `_DENSITY_MIN_CHARS_PER_PAGE` |
| 20 letters and digits: `empty_body` | `_EMPTY_BODY_MIN_ALNUM` |
| 200 letters and impossible characters, 15%, 15%, 5%: `unreadable_chars` | `_UNREADABLE_MIN_LETTERS`, `_UNREADABLE_HALVING_SHARE`, `_MOJIBAKE_MAX_ACCENTED_SHARE`, `_MOJIBAKE_MIN_CYRILLIC_SHARE` |
| `2 / 1`: `formulas`, `lost_formulas` | `_FORMULA_FLOOR`, `_FORMULA_HALVING_*`, `_LOST_FORMULA_*` |
| 40 lines, 3,000 characters: `runaway_math` | `_MATH_BLOCK_MAX_LINES`, `_MATH_BLOCK_MAX_CHARS` |
| 1 defect: `greek_units`, `images`, `llm_ocr_markers` | `_ONE_DEFECT` |
| `1 / 2`: `headings` | `_HEADING_FLOOR`, `_HEADING_HALVING_*` |
| `0 / 2`: `flat_ladder` | `_FLAT_LADDER_*` |
| a quarter, 1: `lost_chapters` | `_LOST_CHAPTER_HALVING_SHARE`, `_LOST_CHAPTER_FLOOR` |
| `0 / 1`: `tables` | `_TABLE_FLOOR`, `_TABLE_HALVING_*` |
| 2%: `junk_lines` | `_JUNK_HALVING_SHARE` |
| 80 characters, `3 / 1`, a median of 3 lines, 10 times: `repeats` | `_REPEAT_MAX_LEN`, `_REPEAT_MIN_*`, `_REPEAT_MAX_MEDIAN_GAP`, `_REPEAT_LOOP_MULTIPLE` |
| `0 / 1` repeated lines: `repeats` | `_REPEAT_FLOOR`, `_REPEAT_HALVING_*` |
| 512 bytes: `images` | `_IMAGE_MIN_BYTES` |
| 3 times: `repeated_images` | `_REPEATED_IMAGE_MIN_COUNT` |
| `2 / 2`: `hyphenation`, `flattened_blocks` | `_REPORTED_FLOOR`, `_REPORTED_HALVING_*` |
| half of the chunks: `inspection_coverage` | `_INSPECTION_HALVING_SHARE`, `_INSPECTION_VETO_DONE_SHARE` |

## What the evaluation does not see

The evaluation does not compare the text with the pages of the source. It does
not find misrecognized words and numbers. It also does not find a value that
moved into the adjacent table column without a change in the row width. The
text density covers the whole document, not each page. Therefore one missing
page in a thick book does not change it.

KaTeX checks only the syntax of a formula. A formula with the wrong content but
with correct markup counts as valid.

Recognition garbage spread over a page with mixed Latin and Cyrillic text can
keep a high score. The result then gets `ok`. Latin garbage in a body of
another script is not seen either, because Latin is never foreign.

## Hints in the log

The log can suggest the next step. A file gets one hint at most, and the first
row of the table has priority over the second.

| Hint | When it shows | What to do |
|---|---|---|
| `recognition failure suspected for <file>; consider --engine` | low text density; an empty body; a wrong encoding; more than 15% unreadable characters; more than `5 / 2` formulas that do not render; more than `5 / 2` `greek_units` formulas; more than `10 / 4` `hyphenation` and `flattened_blocks` findings together; more than 5% junk lines; a lost page. Only for `pdf` and `djvu`, and not in LLM-OCR mode | recognize the document again in LLM-OCR mode (`-e <model>`) |
| `formatting defects look repairable for <file>; consider --llm-post` | `status: bad`, and one of the checks `formulas`, `headings`, `tables`, `repeats`, `hyphenation`, `flattened_blocks` fired, more than 2% of the lines are junk, or an image link points to a missing file. Only if post-processing was off | turn on [post-processing](post.md) (`--llm-post <model>`) |

Post-processing does not repair the LLM-OCR markers, lost formulas, the heading
ladder, lost chapters, or images that exist but are empty. Therefore no hint
covers them.

## How to see the result

Three places show the result of the stage:

- the header of the result: `status`, the total score in `score`, and
  `issues`, which appears only when the list is not empty;
- the console: with `status: bad`, a warning with the total score and the
  checks in `issues`, each with its measured value and its score, for example
  `quality bad for book.pdf, score 25: headings (3 level/space issues) score 25`,
  and a hint from the table above. When `issues` is empty, the warning lists
  each check that lowered the total score. With `status: ok`, the console
  shows nothing;
- the log `~/.raw2md/logs/raw2md.log`: the same lines, and the lines below.

The log adds these lines:

| Line | When it shows |
|---|---|
| `quality ok for <file>, score <N>, below threshold: …` | `status: ok`, and a check fired; the line lists all such checks with their measured values |
| `<file>: <check> at body line <N>` | at the `DEBUG` level, once for each defect that a check finds at a line of the body; the count starts at 1 on the first line after the header |
| `<file>: lost_chapters missing '<entry>'` | at the `DEBUG` level, once for each lost chapter: the entry of the table of contents |
| the share of the result words that occur in the source, and the share of the source words that reach the result | a `pdf` or `djvu` with a text layer; these shares do not change the status |

A check that reads the findings of cleaning writes no `DEBUG` line here: the
log already gives each finding with its line number.
