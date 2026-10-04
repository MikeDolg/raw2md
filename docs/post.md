# Post-processing

Post-processing is an optional LLM stage, the last one before
[quality evaluation](quality.md). The model repairs the markup that the
deterministic [cleaning](cleaning.md) could not repair. The
`--llm-post <model>` flag (`-p`) turns the stage on. The `<model>` value is a model key from `settings.json`.
The key must be in `operations.post.allowed`, which holds `claude_cli` and
`gemini_api` by default.

Post-processing works on any input: `pdf`, `djvu`, `docx`, and `md`. The model
does not get the source and sees only the text. If [inspection](inspection.md)
is on too, post-processing runs after it.

## How the stage edits the text

Post-processing does not send the whole document. The tool itself finds the
zones with defects in the text and sends each zone in a separate request. The
model repairs only the zone: it gets the adjacent paragraphs above and below
for context only, and it cannot edit them. The guard checks the reply of the
model. The tool sends a rejected zone once more, with the reason for the
rejection. After a second rejection, the zone stays as it was.

The tool processes the zones in this order:

1. **Heading ladder**: the whole list of headings in one request.
2. **Blocks and tables**: in the order of the text, one request for each zone.
3. **Letter spacing**: all letter-spaced words in one request, on the text that
   the earlier zones already repaired.

If the text has no zones, the tool sends no requests.

## What goes to the provider

Post-processing sends only the zones with defects to the provider of the model
key. These are the headings, the damaged blocks and tables, and the
letter-spaced words, with up to 4,000 characters of adjacent text. The source
and the rest of the text do not go out. With `claude_cli`, the tool runs
`claude -p`. That program works with its own settings, and raw2md does not
control what it adds to the request.

## What post-processing repairs

| Zone | When it opens | Before | After |
|---|---|---|---|
| Flattened block | 6 short paragraphs or more in a row (up to 200 characters each), and at least one of them continues the phrase of the previous one; list items count too | `- Check the`, `oil level`, `- Replace the`, `filter`, and so on | `- Check the oil level`, `- Replace the filter`, and so on |
| Text inside a formula | the formula holds two words of 3 letters or more that start with a lowercase letter, with only a space between them | `$v = s / t where the time$ is measured` | `$v = s / t$ where the time is measured` |
| A formula that does not render | KaTeX does not render the formula, and all `$` signs have a pair | `$\frac{a}{b$` | `$\frac{a}{b}$` |
| A table row of the wrong width | the number of cells does not match the delimiter row | `\| M8 \| \| 25 \| 0.9 \|` | `\| M8 \| 25 \| 0.9 \|` |
| The values of a row in one cell | empty cells stand next to it, and the values match the kinds of the columns | `\| M8 25 0.9 \| \| \|` | `\| M8 \| 25 \| 0.9 \|` |
| Heading ladder | a level is skipped, or identical headings sit at different levels | `### Notes` in chapter 1, `## Notes` in chapter 2 | both at the level of their place in the table of contents |
| Letter-spaced word | 3 letters or more with spaces between them, which cleaning did not join | `the i m p o r t a n t part` | `the important part` |
| Letter spacing with a tail | a part of a word is attached to the letter-spaced letters | `s u m m ary` | `summary` |

In a flattened block, the model joins a word break only when the document
confirms the word. The document must hold the whole word, or another form that
matches for at least 3 letters past the break. The model keeps letter-spaced
letters that do not make a word (for example, `A B C` in a symbol legend) as
they are.

## What post-processing does not change

Post-processing does not see the pages of the source. Therefore misrecognized
words, numbers, and the content of formulas stay as cleaning or inspection left
them. Post-processing does not find a value that moved into the adjacent
column without a change in the row width. Only the page shows such a shift.

The YAML header, code blocks, and HTML tables never go into a zone. An adjacent
paragraph stays out of the request if one of these elements separates it from
the zone. A paragraph longer than 4,000 characters stays out too.

## When an edit does not apply

The guard checks the reply of the model. Its rules depend on the kind of zone.

### Flattened block

| Rule | Before | Rejected reply |
|---|---|---|
| Words, punctuation marks, list markers, and emphasis do not change | `The pump`, `is started` | `The pump starts` |
| Formulas do not change | `the sum $x + y$` | `the sum $x$ + y` |
| No table appears | `Size`, `10 mm` | `\| Size \| 10 mm \|` |
| No code block or HTML table appears | `plain text` | the same text in a code block |
| A word break joins only into a word that occurs in the document | `pre-`, `load`; the text does not hold the word `preload` | `preload` |
| The defect is gone: a second cleaning pass finds nothing in the reply | `The pump`, `is started` | the same paragraphs in a different order |

### Text inside a formula

| Rule | Before | Rejected reply |
|---|---|---|
| Only the `$` signs move, and their number does not change | `$v = s / t where the time$` | `$v = s / t$ where time` |
| The other formulas of the zone do not change | `$a$ and $b c where the d$` | `$a + 1$ and $b c$ where the d` |

### A formula that does not render

| Rule | Before | Rejected reply |
|---|---|---|
| The reply can add or delete only `{ }`, `\left`, `\right`, `\begin`, and `\end` | `$\frac{a}{b$` | `$\frac{a}{b}+c$` |
| An unpaired `\left` closes with the invisible `\right.`, not with its own bracket | `$\left( a + b$` | `$\left( a + b \right]$` |
| An environment can only be the one that the formula already declares | `$\begin{cases} x & y$` | `$\begin{pmatrix} x & y \end{pmatrix}$` |
| The formula renders after the repair | `$\frac{a}{b$` | `$\frac{a}{{b}$` |
| The valid formulas of the zone do not change | `$x^2$ and $\frac{a}{b$` | `$x^3$ and $\frac{a}{b}$` |

### Table row

| Rule | Before | Rejected reply |
|---|---|---|
| Only the row that the request marks as open can change | the valid row `\| M6 \| 10 \| 0.5 \|` | any edit of it |
| The delimiter row and a continuation row are closed to edits | `\| \| wrapped text \| \|` | the row merged with the row above |
| A row stays one row | `\| M8 25 0.9 \| \| \|` | two rows |
| The number of cells matches the delimiter row | `\| M8 25 0.9 \| \| \|` | `\| M8 \| 25 \|` |
| The values do not stay in one cell | `\| M8 25 0.9 \| \| \|` | `\| M8 25 \| 0.9 \| \|` |
| The formulas of the row do not change | `\| $x$ 3 \| \|` | `\| $y$ \| 3 \|` |
| The values stay, in the same order | `\| M8 25 0.9 \| \| \|` | `\| 25 \| M8 \| 0.9 \|` |

The model can lay out the values in cells but leave the old empty cells in
place. The tool then deletes the extra empty cells, on the condition that the
number of filled cells equals the number of columns.

### Heading ladder

| Rule | Before | Rejected edit |
|---|---|---|
| Only the level changes; the text of the heading stays the same | `## Notes` | `### Remarks` |
| A heading underlined with `===` or `---` does not change | `Notes`, `---` | `### Notes` |
| The level is from 1 to 6 | `###### Notes` | level 7 |
| The level moves by two at most, unless the document itself sets the level with a numbered series of 4 headings or more, or with a table of contents in the text | `## Notes` | `##### Notes` |
| The number of skipped levels does not grow | `#`, `##`, `###` | `#`, `###`, `###` |
| The number of identical headings at different levels does not grow | `## Summary`, `## Summary` | `## Summary`, `### Summary` |
| No level becomes empty, and the fullest level does not grow | `#`, `##`, `##` | `#`, `#`, `#` |

First, the guard checks the ladder edits together. If together they make the
ladder worse, the guard checks each edit in order and drops the edits that make
it worse. The last two rules do not apply to an edit whose level the document
itself sets.

### Letter spacing

| Rule | Before | Rejected reply |
|---|---|---|
| Only the spaces between the letters change | `i m p o r t a n t` | `importent` |
| All spaces of the word go at once | `i m p o r t a n t` | `impor t a n t` |
| The tail joins only when all spaces are gone | `s u m m ary` | `s u m mary` |

## Large documents and errors

| Situation | Result |
|---|---|
| A reply for a table or for letter spacing longer than 8,000 characters | the tool sends the rows and the words in parts; each part of a table holds the header row and the delimiter row |
| A table does not fit into a request | the request holds only the header row, the delimiter row, and the open rows |
| The reply repeats the zone without a change | the zone stays as it was; the tool sends no repeat |
| A provider error on a zone | the tool skips the zone and processes the other zones; the run ends with an LLM error |
| The quota is spent, or the key is rejected | post-processing stops, and the run ends with an LLM error; the edits of the zones already done apply |
| Not all zones came back | `post: partial (N/M)` |
| No zone came back | post-processing does not apply; `post: failed` |

After post-processing, [quality evaluation](quality.md) runs again. If
post-processing is off and the result gets `status: bad`, the log can suggest
the `--llm-post` flag. The log does this when the defects look like the ones
that post-processing repairs.

## How to see the result

Four places show the result of the stage:

- the `post` field in the header of the result: the model key if the stage
  succeeded, also with no zones; `none` if the stage was off; `failed` if no
  zone came back; `partial (N/M)` if N zones of M came back;
- the `post.md` file in the `<name>.debug/` folder, after a run with `--debug`
  (`-d`): the text after post-processing; the text before it is in
  `acceptance.md` after inspection, and in `cleaning.md` without inspection;
- the `llm/post.txt` file in the same folder: the requests and the replies of
  the model as they are;
- the log `~/.raw2md/logs/raw2md.log`: one line for each file, with a summary
  of the repaired and the rejected zones, the joined word breaks, the table
  rows, the heading levels, and the letter-spaced words.
