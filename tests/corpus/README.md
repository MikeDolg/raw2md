# Reference corpus

The corpus contains the reference Markdown files for the round-trip tests. A test
renders a fixture into a source format, converts the file back with raw2md,
and compares the result with the fixture.

Each fixture is correct by definition. The defects come from the format
generation and from the conversion, not from the fixture. A change to a
fixture therefore changes the expected result of every test that reads it.

## Tests

Two layers of tests read the corpus:

| Layer | Tests | What they check |
|---|---|---|
| Fast | `tests/synthesis/test_corpus_fast.py`, `tests/test_cleaner.py`, `tests/test_katex.py` | the structure counts of a fixture; the targeted check does not fire on the fixture; a second cleaning gives the same text as the first; KaTeX renders every formula |
| Round-trip | `tests/synthesis/test_roundtrip.py` | the conversion ends with exit code `0` and a valid header; the structure counts of the result match the fixture within the tolerance of the format; the checks of each fixture from the table below |

## Run

The fast tests run with the rest of the suite:

```bash
uv run pytest
```

The round-trip tests run only on request:

```bash
uv run pytest -m roundtrip            # all formats
uv run pytest -m roundtrip -k docx    # docx only, without marker
```

Each format needs its own tools. A test skips when a tool is not installed.

| Format | Fixtures | Tools |
|---|---|---|
| `docx` | all except `handwriting.md` | pandoc |
| `pdf` | `mixed.md`, `headers.md`, `tables.md`, `formulas.md`, `images.md`, `nested_lists.md`, `multilang.md`, `long_doc.md` | pandoc, XeLaTeX, marker |
| `scan`, `scan_degraded` | `mixed.md` | pandoc, XeLaTeX, `img2pdf`, marker |
| `handwriting_scan` | `handwriting.md` | pandoc, XeLaTeX, `img2pdf`, marker |
| `djvu` | `mixed.md` | pandoc, XeLaTeX, DjVuLibre (`c44`, `djvm`, `ddjvu`), marker |

To run one round-trip by hand and keep its result, give a fixture and a format
from the table:

```bash
uv run python -m tests.synthesis.roundtrip tests/corpus/tables.md docx --work-dir rt
```

The command prints the exit code, the status, and the structure difference. It
writes the fixture and the result side by side to `rt/pair/` and prints the
`git diff --no-index` command that compares them. Without `--work-dir`, the
command uses a new temporary folder.

## Fixtures

| File | What it contains | What it checks |
|---|---|---|
| `headers.md` | headings H1 to H4 without a skipped level; one setext H2, a text underlined with `---` | heading levels and the space after `#`; a setext underline is not a junk line |
| `tables.md` | six tables: left, right, and center alignment, numbers, dashes, and empty cells | table integrity; a dash in a cell is a meaningful character |
| `formulas.md` | inline and display formulas; an escaped `\$`, deep fractions, a multi-line display formula, `$$` on lines of their own | the `$…$` and `$$…$$` markup; an escaped `\$` is not a formula; a `$$` alone on a line is not junk |
| `mixed.md` | a Russian document of two pages: lists, a table, a quote, formulas | text density, lists, tables, and formulas together; the input of the scan and `djvu` tests |
| `handwriting.md` | Russian lecture notes: headings, a list, a table, text; no formulas | recognition of handwriting; junk characters |
| `images.md` | two embedded images | media extraction and relative links; the `images` check: a missing file, a file under 512 bytes, a file of one color |
| `table_formulas.md` | display and inline formulas in the cells of a pipe table; a figure with explicit `width` and `height` | a formula in a cell stays on its table row; the figure becomes an HTML `<img>` with a portable `src` |
| `table_math_pipes.md` | in table cells, a display formula with a modulus bar and a formula that the Word equation editor splits over lines | a bare `\|` in a formula gets an escape; the line breaks in a formula collapse into one table row |
| `multiline_display_math.md` | a system of equations outside a table, from the Word equation editor: the environment opens on the first line and closes several lines below | a balanced multi-line display formula gives no false `broken-formula` finding on its first line |
| `single_glyph_math.md` | single glyphs from the Word equation editor (`\varnothing`, `\circ`, bare `°` and `℃`) beside one-letter variables (`R`, `D`, `\theta`) | a glyph from the closed mapping table becomes prose; a real variable stays a formula |
| `chart_series.md` | three figures with the same axis-label formula under each | a legitimate repeat of a formula line does not fire `repeats` |
| `nested_lists.md` | lists of three levels: bullet in bullet in bullet, numbered in numbered, bullet in numbered in bullet; long items over several lines | the blank lines around a list; no false defect |
| `footnotes.md` | footnotes `[^name]` with multi-line definitions | the references survive pandoc; no defect |
| `multilang.md` | Russian text with Latin identifiers, abbreviations, and a table | mixed Latin and Cyrillic text does not fire `unreadable_chars` |
| `long_doc.md` | the longest fixture: six sections on three pages | the `text_density` floor of 350 characters per page; no false `repeats` |
| `engineering_prose.md` | a Russian page of an engineering handbook: Latin grades and standards, a bold figure caption, a symbol legend, author initials | homoglyph repair does not touch a Latin token without a Cyrillic anchor; a `•` in the middle of a line is not a list marker; a short bold caption and a bold phrase keep `**`; a whole Roman number such as `XI.37` stays whole |
| `math_legend.md` | a Russian calculation page: a `\begin{cases}` environment, an equation with a text condition, a prose symbol legend beside formulas, escaped sums `\$` | the prose stays in the environment; a text condition without a dash stays part of the equation; a prose legend next to a formula stays out of it; `\$` does not open a formula |

## Assets

The `assets/` folder contains the images of the fixtures and the handwriting font.
Pillow drew the images, and they have no external source.

| File | Fixtures | Note |
|---|---|---|
| `sample.png` | `images.md` | a color gradient and simple shapes |
| `chart.png` | `images.md`, `table_formulas.md`, `chart_series.md` | a grid and a bar chart |
| `chart-2.png`, `chart-3.png` | `chart_series.md` | byte copies of `chart.png` under their own names: `repeated_images` counts paths, not content, and one path in three places would fire it |
| `diagram (v2).png` | none | a space and parentheses in the name, for the fast test of a percent-encoded link |
| `fonts/Caveat-Regular.ttf` | `handwriting.md` | a handwriting font with Cyrillic, SIL OFL 1.1; the source is in `fonts/sources.md`, the license text in `fonts/OFL.txt` |

## Conventions

- The content is invented. The language is English. Russian stays only where a
  fixture checks Cyrillic: `mixed.md` (scan), `handwriting.md` (handwriting
  font), `multilang.md` (mixed scripts), `engineering_prose.md` (homoglyphs),
  and `math_legend.md` (Cyrillic units).
- A fixture renders to three pages at most.
- `images.md`, `table_formulas.md`, and `chart_series.md` link an image as
  `assets/<name>.png`, a path relative to the fixture. The other fixtures contain
  no image.
- The Markdown is compatible with pandoc: pipe tables and `$` math.
- A fixture contains only what its targeted checks need.

### Formulas in a special form

Three fixtures write a formula in a form that is not the obvious one. Only
that form gives the shape that the test needs after the docx round-trip.

`table_math_pipes.md` writes the modulus as `\left\lvert…\right\rvert`, not as
`\left|…\right|`. The source then contains no bare `|`, and markdownlint does not
count an extra table column (`MD056`). When pandoc writes the docx, it turns
`\lvert` and `\rvert` into a literal `|`, and the bar stays after the read
back. That bare bar is the target of the cleaning rule. The escaped form `\left\|` does not work:
pandoc reads it as `\parallel`, a different symbol.

`single_glyph_math.md` writes the degree sign as a bare `°` in a formula, not
as `{^\circ}`. A source `{^\circ}` comes back from the docx as `^{\circ}`. The
closed mapping table of the cleaning rule does not contain that form, so the
formula stays a formula. A bare `°` comes back as `{^\circ}`, the form that the
rule knows. A space separates each formula from the next character. A digit
right after the closing `$` stops pandoc from reading `$…$` as a formula, so
this fixture cannot contain that case. The unit tests of cleaning cover it.

`multiline_display_math.md` writes the system as `\left\{ \begin{array}{r}…`.
The docx round-trip turns it into `\left\{ \begin{matrix}…`, because the
column specification `{r}` does not survive OMML. The shape stays exact: the
environment opens on the first line of the formula and closes several lines
below. The `broken-formula` rule must tell this shape from an environment that
marker cut short.
