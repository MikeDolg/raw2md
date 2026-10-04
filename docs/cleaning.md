# Cleaning

Cleaning is the first stage after conversion, and it always runs. It repairs
the typical defects of the converters without an LLM. Therefore it runs on
every input, `md` included, and in every mode. The stage has no flag of its
own.

## How the stage edits the text

Cleaning repairs defects with deterministic rules. The same input gives the
same result, and a second cleaning pass changes nothing. A rule repairs a
defect only when the defect is unambiguous. An ambiguous defect stays in the
text and goes into the findings, which quality evaluation uses.

Constants in the code set the thresholds of the rules. A table under each group
of rules lists them. The module paths start at `src/raw2md/`.

## What cleaning repairs

### 1. Headings

| Defect | Before | After |
|---|---|---|
| Bold or italics over the whole heading | `## **2.3 Load Tables**` | `## 2.3 Load Tables` |
| A symbol before the number; `№` and `§` stay | `## ● 4 Maintenance` | `## 4 Maintenance` |
| A letter-spaced heading; repaired only when the word also occurs in the document without spaces | `## I n t r o d u c t i o n` | `## Introduction` |
| A numbered heading merged with a paragraph; the title is 60 characters at most, and each word starts with a capital letter | `### 3.1 Problem Statement. The pump runs…` | `### 3.1 Problem Statement`, with the paragraph on its own |
| A heading longer than 200 characters | `## <long line>` | the same line as a plain paragraph |
| A running head recognized as a heading: the number and the title repeat while the section is still open | a second `## 5.2 Filters` | deleted; a repeat without the number stays |
| The level does not match the depth of the number | `## 4`, `## 4.1`, `#### 4.3.1` | `# 4`, `## 4.1`, `### 4.3.1` |
| A lost heading: a separate paragraph with a multi-level number that continues the numbering of the adjacent headings | `4.2 Valves` between `## 4.1` and `## 4.3` | `## 4.2 Valves` |
| An unnumbered heading at the level of its section or higher | `## Notes` under `## 4.1 Pumps` | `### Notes` |
| A heading series (`Chapter 1`, `Chapter 2`, and so on) or a heading with 3 copies or more at different levels | `## Chapter 1`, `### Chapter 2`, `## Chapter 3` | all at the level of the majority |
| A skipped level of the structure | `#`, then `###` | `#`, then `##` |
| A docx without heading styles: bold numbered paragraphs, when 3 numbers or more follow in sequence under a section number | `**1.1 Pumps**`, `**1.2 Valves**`, `**1.3 Seals**` | `## 1.1 Pumps`, and so on |
| A docx without heading styles: paragraphs in capital letters, when the document has 3 such paragraphs or more | `PUMPS` | `## PUMPS` |

The level rules change only the number of `#` signs in the markup. The text of
the heading does not change.

Cleaning takes the level of a heading from four sources. They are, from the
most reliable: the PDF bookmarks, the table of contents in the text, the
numbering, and the nesting of sections. A less reliable source does not
overwrite a level that a more reliable source set. Some sources and rules have
extra conditions:

- **PDF bookmarks** set the levels of the whole document when the text holds at
  least half of the bookmarks, and 3 at least.
- **The table of contents in the text** counts only when the PDF has no
  bookmarks. The lines of the table of contents stay in place.
- **A docx without styles**: the rules in the last two rows of the table work
  only on a `docx` or `md` input. The document must also have no heading at
  all.

| Threshold | Constant | Module |
|---|---|---|
| 1 occurrence: the word of a letter-spaced heading occurs in the text without spaces | `_SPACED_TITLE_WITNESS_MIN` | `cleaning/headings.py` |
| 60 characters: the title of a merged heading | `_RUN_IN_TITLE_MAX_LENGTH` | `cleaning/headings.py` |
| 200 characters: the length of a heading | `_HEADING_MAX_LENGTH` | `cleaning/headings.py` |
| 3 copies: a heading series | `_HEADING_CLASS_MIN_SIZE` | `cleaning/headings.py` |
| 3 copies: a repeated heading | `_REPEATED_TITLE_MIN_COPIES` | `cleaning/headings.py` |
| 3 numbers in sequence: a docx without styles | `_LADDER_MIN` | `cleaning/headings.py` |
| 3 paragraphs in capital letters: a docx without styles | `_CAPS_SEED_MIN` | `cleaning/headings.py` |
| half of the PDF bookmarks in the text | `_OUTLINE_SKELETON_MIN_SHARE` | `cleaning/headings.py` |
| 3 PDF bookmarks in the text | `_OUTLINE_SKELETON_MIN_TITLES` | `cleaning/headings.py` |

### 2. Formulas

Cleaning repairs the markup of a formula, but not its content. A misrecognized
symbol stays: its repair is the task of [inspection](inspection.md).

| Defect | Before | After |
|---|---|---|
| A backslash joined to the closing `$$`; an escaped sign such as `5\$` stays | `$$ x = a + b \$$` | `$$ x = a + b$$` |
| A number directly before a formula, without a space; the notation `$5-$6` stays | `3$S$` | `3 $S$` |
| An inline formula longer than 16 characters, with a sign such as `=` or `<`, as a separate paragraph | `$E = m c^2 + a b c d$` | `$$E = m c^2 + a b c d$$` |
| `$` signs around a text environment | `$\begin{tabular}…\end{tabular}$` | `\begin{tabular}…\end{tabular}` |
| A formula of one symbol; a letter formula such as `$R$` stays | `$\varnothing$`, `${^\circ}$` | `∅`, `°` |
| A formula of spaces only | `gap $\,\,\,$ here` | `gap here` |
| A formula cut into parts | `$$ y = a x^2 + b x $$`, `$$ + c $$` | `$$ y = a x^2 + b x + c$$` |
| An equation number under the formula or after it | `$$ F = m a $$`, `(12)` | `$$ F = m a \tag{12}$$` |
| A punctuation mark under the formula | `$$ s = v t $$`, `.` | `$$ s = v t.$$` |
| A condition under the formula; a reference such as `[See 45.]` stays | `$$ x = y $$`, `[n \neq 1]` | `$$ x = y \quad [n \neq 1]$$` |
| Commands that KaTeX does not support | `\mbox{max}`, `\textsc{max}`, `\eqno(3)` | `\text{max}`, `\text{max}`, `\tag{3}` |
| The `\label` command | `x = 1 \label{eq:1}` | `x = 1` |
| A double subscript | `x_{a}_{b}` | `x_{a}{}_{b}` |
| A quotation mark instead of a double prime | `t"` | `t''` |
| An HTML tag inside a formula | `$<sup>^{\ast}</sup>$` | `$^{\ast}$` |
| `\left` without a matching `\right` | `$\left( a + b$` | `$\left( a + b \right.$` |
| `\left` or `\right` without a bracket | `$a + b \right$` | `$a + b$` |
| The tail of a cut environment | `a & = b \end{split}` | `a = b` |
| A line of the symbol legend inside a formula | `$$v - \text{flow velocity, m/s}$$` | `$v$ - flow velocity, m/s` |
| A display formula in a table row | `$$…\left\| y \right\|$$` in a cell | the formula on one line, with `\|` escaped |
| A `pandoc` formula in a cell of an HTML table | `<td><span class="math inline">$x$</span></td>` | blank lines around the cell content; the formula renders |

Cleaning applies a `\left` or `\right` repair only when the formula renders
after it. Otherwise the formula stays as it was.

| Threshold | Constant | Module |
|---|---|---|
| 16 characters: an inline formula as a separate paragraph | `_PARAGRAPH_FORMULA_MIN` | `cleaning/math.py` |

### 3. Lists

| Defect | Before | After |
|---|---|---|
| A numbered list recognized as a bulleted list; the numbers run in sequence | `- 1. Drain`, a nested `- 2. Remove`, `- 3. Fit` | `1. Drain`, `2. Remove`, `3. Fit` |
| A single item one level deeper after two items or more; two such items or more count as a real nested list | `- Oil`, `- Water`, a nested `- Air` | `- Oil`, `- Water`, `- Air` |
| A bold number without a space in a list item | `- **10.**Check` | `- **10.** Check` |
| The `•` symbol at the start of a line | `• Stainless steel` | `- Stainless steel` |
| The `❚` glyph at the end of an item or on a line of its own | `- Oil ❚` | `- Oil` |

Numbers with a gap (`2023.`, `2025.`) stay as they are. They are the text of
the author, not a parsed list.

### 4. Tables

| Defect | Before | After |
|---|---|---|
| Records laid out in several column groups, with a repeated header row | `\| No. \| Size \| No. \| Size \|` | `\| No. \| Size \|`, with the records one under another |
| A table cut by a page break: the header row repeats, and no text separates the parts | two tables with the same header row | one table |
| A table without data rows | `\| Size \| Weight \|`, `\|---\|---\|` | `Size Weight` |
| All values written into one cell of the header row; each column holds values of one kind | `\| Size \| Weight \| M6<br>10<br>M8<br>12… \|` | the rows `\| M6 \| 10 \|`, `\| M8 \| 12 \|`, and so on |
| Text attached to the header row | `The sizes are: \| Size \| Weight \|` | the paragraph `The sizes are:` and the table |
| Rows with `\|` and no delimiter row; at least 2 rows and 2 columns | `\| Size \| Weight \|`, `\| M6 \| 10 \|` | `\|---\|---\|` under the first row |
| The delimiter row as the first line of the block | `\|---\|---\|` above the rows | the delimiter row under the first row |
| An empty column | `\| Size \| \| Weight \|` | `\| Size \| Weight \|` |
| The values of two adjacent cells written into one cell, and the other cell is empty | `\| 1,000.0 1,027.3 \| \|` | `\| 1,000.0 \| 1,027.3 \|` |
| The values of a row shifted across the columns; repaired only when the kinds of values allow exactly one layout | a part number and the sizes in one cell | each value in its own column |
| A table of contents in one column | `\| 1 Pumps ........ 5 \|` | `1 Pumps 5` |
| `<br>` in a cell of the table of contents | `1 Pumps and<br>valves` | `1 Pumps and valves` |
| An entry of the table of contents split across two table rows | the title and the page on different rows | one row |
| Cells padded with spaces to the column width | cells of different lengths aligned with spaces | a table up to 120 characters wide stays aligned; a wider table gets one space around each value |

The rules for a table of contents work only between the heading `Contents` and
the next heading. The table rules do not change the values in the cells.

| Threshold | Constant | Module |
|---|---|---|
| 2 rows: rows with `\|` and no delimiter row | `_DELIMITERLESS_MIN_ROWS` | `cleaning/tables.py` |
| 2 columns: rows with `\|` and no delimiter row | `_DELIMITERLESS_MIN_WIDTH` | `cleaning/tables.py` |
| 120 characters: the width of an aligned table | `_TABLE_WIDTH_CEILING` | `cleaning/tables.py` |

### 5. Text

| Defect | Before | After |
|---|---|---|
| Navigation markup of `marker` | `See Table [2,](#page-49-0)` | `See Table 2,` |
| A file path instead of the image caption | `![C:\Users\me\pump.png](media/image1.png)` | `![](media/image1.png)` |
| A line of punctuation marks only; `---` and a single mark stay | `.,;:` | deleted |
| Invisible characters: the soft hyphen (U+00AD), the zero-width characters (U+200B to U+200D), and the byte order mark (U+FEFF) | `pre` + U+00AD + `ssure`, which looks like `pressure` on screen | `pressure` |
| Bold over a whole paragraph longer than 120 characters, with two sentences or more | `**The pump must be stopped… housing.**` | no `**` |
| A bold letter attached to a word | `**I**nterface` | `Interface` |
| A letter of another alphabet in a word; a word whose letters all exist in both alphabets does not change | `Cоntrol` (a Cyrillic `о`) | `Control` |
| A space inside a Roman numeral | `Fig. V II.11` | `Fig. VII.11` |
| A space inside a clause number; the sequence `1. 2. 3.` stays | `82. 1. Scope` | `82.1. Scope` |
| No space after the `#` signs of a heading | `##Text` | `## Text` |
| A running head: a title and a page number repeat 4 times or more, one page apart | `Hydraulic Pump Manual`, `Page 14` | deleted |
| A word break with a hyphen; the join needs a confirmation from the PDF text layer, or a joined word that occurs in the text 2 times or more; `S7-200` is not joined | `actu-`, `ator` | `actuator` |
| A hyphen in a compound word; repaired when the other spelling occurs 3 times more often | `costeffective`, `load-ing` | `cost-effective`, `loading` |
| A letter-spaced word; repaired when the spelling without spaces occurs in the text 2 times or more | `i m p o r t a n t` | `important` |
| A paragraph broken into lines: 6 short paragraphs or more in a row, where a phrase breaks off and continues with a lowercase letter | `The pump is started`, `only after the tank`, and so on | `The pump is started only after the tank …` |
| Consecutive blank lines and spaces at the end of a line | | one blank line; the spaces deleted |

| Threshold | Constant | Module |
|---|---|---|
| 120 characters: a bold paragraph | `_WHOLE_PARAGRAPH_EMPHASIS_MIN_CHARS` | `cleaning/prose.py` |
| 2 sentences: a bold paragraph | `_WHOLE_PARAGRAPH_EMPHASIS_MIN_SENTENCES` | `cleaning/prose.py` |
| 4 repeats: a running head | `_FURNITURE_MIN_PAIRS` | `cleaning/prose.py` |
| 2 times: the joined word of a word break in the text | `_MERGED_FORM_MIN_COUNT` | `cleaning/prose.py` |
| 3 times more often: the spelling of a compound word | `_COMPOUND_MAJORITY_RATIO` | `cleaning/prose.py` |
| 2 times: a letter-spaced word without spaces in the text | `_SPACED_WITNESS_MIN` | `cleaning/prose.py` |
| 6 paragraphs: a paragraph broken into lines | `FLATTENED_PARAGRAPH_MIN_RUN` | `cleaning/segments.py` |

### 6. Repeats

Recognition sometimes falls into a loop and prints the same piece many times in
a row. Cleaning cuts such a repeat down to one copy.

| Repeat | Threshold | Before | After |
|---|---|---|---|
| A piece of 3 to 80 characters in a formula | 6 times | `\sum_{i}\sum_{i}…\sum_{i}` | `\sum_{i}` |
| A piece of 3 to 80 characters in the text | 10 times | `abc abc … abc` | `abc` |
| The same inline formula in a row | 6 times if the formula holds one of `\ { } _ ^`, otherwise 20 | `$v_1$ $v_1$ … $v_1$` | `$v_1$` |
| A line or a block in a row | 3 copies | three identical lines | one line |

Two copies in a row do not count as a repeat. Table rows and the lines of a
multi-line formula do not count either. If the cut leaves only a fragment of a
formula, cleaning deletes the whole formula. The repeat then goes into the
findings as `broken-formula`.

| Threshold | Constant | Module |
|---|---|---|
| 3 characters: the shortest piece | `_LOOP_MIN_PERIOD` | `mdtext/loops.py` |
| 80 characters: the longest piece | `_LOOP_MAX_PERIOD` | `mdtext/loops.py` |
| 6 times: a piece in a formula; an inline formula with `\ { } _ ^` | `_LOOP_MIN_REPEATS` | `mdtext/loops.py` |
| 10 times: a piece in the text | `_PROSE_LOOP_MIN_REPEATS` | `mdtext/loops.py` |
| 20 times: an inline formula without `\ { } _ ^` | `_SPAN_RUN_PLAIN_MIN_REPEATS` | `mdtext/loops.py` |
| 3 copies: a line or a block | `_REPEATED_COPY_MIN_RUN` | `cleaning/findings.py` |

### 7. Recognition errors

Both repairs rely on a correct spelling that occurs in the text at least as
often as the threshold. The `cleaning.witness_min` field in `settings.json`
sets the threshold: 20 by default, and 2 at least. A lower threshold repairs
more words. However, it can replace a word that the document really uses only
once.

| Defect | Before | After | Condition |
|---|---|---|---|
| A code lost its case; a code is a word with a digit and 2 letters or more | `ru9101100` | `RU9101100` | `RU9101100` occurs in the text at least as often as the threshold |
| A word of 6 letters or more occurs once and differs by one letter from a frequent word | `pressuse` | `pressure` | `pressure` occurs in the text at least as often as the threshold, and no other word is that close |

| Threshold | Constant | Module |
|---|---|---|
| 20 times: the default threshold | `DEFAULT_WITNESS_MIN` | `cleaning/ocr.py` |
| 2 times: the lowest threshold | `_WITNESS_MIN_FLOOR` | `settings.py` |
| 2 letters: a code | `_MIN_CODE_LETTERS` | `cleaning/ocr.py` |
| 6 letters: a word that cleaning can repair | `_MIN_REPAIRABLE_WORD` | `cleaning/ocr.py` |

### 8. Images and links

The repairs of images and links depend on the run mode. Without image
extraction, an image link points to a file that does not exist. In LLM-OCR
mode, the model invents images and links that the source does not have.

| Mode | Before | After |
|---|---|---|
| `--disable-image-extraction` | `![Pump housing](missing.png)`, `<img src="missing.png" alt="Pump">` | the caption as a separate paragraph; the link deleted |
| LLM-OCR: an image | `![Pump](img.png)` | deleted with its caption |
| LLM-OCR: an external link | `[site](https://example.com)` | `site` |
| LLM-OCR: a model placeholder in place of an image | `[Image of a pump]` | deleted; if it repeats the caption, the caption stays without the brackets |

The model markers `[unreadable]` and `[?]` stay. Outside LLM-OCR mode,
external links do not change.

## What cleaning does not change

Cleaning edits the whole document, except for:

- the YAML header;
- code blocks;
- HTML tables. Cleaning does not change the markup of the table. In the cells,
  it makes three repairs only. It deletes a file path from `alt`. In LLM-OCR
  mode (for example, `-e gemini_api`), it deletes the images and links that the
  model invented. It also puts blank lines around the content of a cell with a
  formula, so that the formula renders.

## When a repair does not apply

### Findings

Findings are defects that cleaning detects but does not repair, because the
repair would be ambiguous. [Quality evaluation](quality.md) puts each finding
into its check. It counts some defects from the text itself.

| Finding | What it is | Quality evaluation |
|---|---|---|
| `hyphenation` | a word break that nothing confirms as a join | `hyphenation` |
| `hyphenation-gap` | the same word break, with the second half after a blank line, an image, or a page break | `hyphenation` |
| `flattened-block` | 6 lines or more in a row, each up to 25 characters long; an unnumbered heading longer than 200 characters | `flattened_blocks` |
| `flattened-paragraphs` | a paragraph broken into lines that the join rule did not repair | `flattened_blocks` |
| `run-in-heading` | a heading merged with a paragraph, with a function word in its title (`Design for Assembly`) | `flattened_blocks` |
| `broken-formula` | a formula cut because of a repeat; an unclosed environment | `lost_formulas` |
| `broken-table` | a row with a different number of cells; the values of a row in one cell; a table without a header row | counted from the text |
| `broken-image` | a link to an image file that does not exist | counted from the text |
| `letter-spacing` | a letter-spaced word whose spelling without spaces does not occur in the text | not counted |

| Threshold | Constant | Module |
|---|---|---|
| 6 lines: `flattened-block` | `FLATTEN_MIN_RUN` | `cleaning/segments.py` |
| 25 characters: `flattened-block` | `FLATTEN_MAX_CHARS` | `cleaning/segments.py` |
| 200 characters: `flattened-block` | `_HEADING_MAX_LENGTH` | `cleaning/headings.py` |

## Settings

Some rules find the parts of a document by keywords, for example `Contents`,
`Page`, `Appendix`, and `Fig.`. The [`keywords.yaml`](reference.md#keywordsyaml)
file holds the word list. To add the words of your language, run
`raw2md keywords edit`.

The `cleaning.witness_min` threshold in `settings.json` controls the repair of
recognition errors. Section 7, [Recognition errors](#7-recognition-errors),
describes it.

## How to see the result

Three places show the result of the stage:

- the difference between `conversion.md` and `cleaning.md` in the
  `<name>.debug/` folder, after a run with `--debug` (`-d`): everything that
  cleaning did;
- the log `~/.raw2md/logs/raw2md.log`: the number of findings of each kind, and
  each finding with its line number;
- the header of the result: `status` and `issues`, where quality evaluation
  sums up the findings.
