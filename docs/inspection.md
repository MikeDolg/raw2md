# Inspection

Inspection is an optional LLM stage after cleaning. The model compares the text
with the pages of the source and repairs the recognition errors. The
`--llm-inspection <model>` flag (`-i`) turns the stage on. The `<model>` value
is a model key from `settings.json`. The key must be in
`operations.inspection.allowed`, which holds `gemini_api` by default.

Inspection works only on a `pdf` or `djvu` input, because a `docx` or `md`
file has no pages to compare with. It does not depend on
[post-processing](post.md) (`--llm-post`). If both stages are on, inspection
runs first.

## How the stage edits the text

The model does not rewrite the document. It returns a list of edits. Each edit
holds the page number, the line number on the page, the original fragment
("before") letter for letter, and its replacement ("after"). The tool applies
the edit itself: it finds the fragment by the address and replaces only that
fragment. Before the tool applies an edit, the guard checks it. If the guard
rejects the edit, the text from cleaning stays in the document.

The model does not see the valid formulas. In the request, the marker
`⟦valid formula N⟧` replaces each of them. After the edits, the tool puts the
formula back from the document without a change. The tool counts a formula as
broken when KaTeX does not render it. A formula with a repeat loop or with a
subscript that spaces break up (`M_{y  n  1}`) is broken too.

### Acceptance pass

After the edits, deterministic rules check once more the lines that inspection
changed, without an LLM. The acceptance pass does not change the rest of the
text, and it does not undo the edits.

| Defect | What the acceptance pass does |
|---|---|
| Invisible characters and spaces at the end of a line | deletes them |
| A table row where an edit changed the number of cells | does not repair it; writes the number of such rows to the log |
| Rows with `\|` and no delimiter row | adds a `\|---\|` delimiter row, or attaches the rows to a table of the same width above them |

## What goes to the provider

Inspection can send the entire document to the provider of the model key, in page chunks.

## What inspection repairs

| Defect | Before | After |
|---|---|---|
| A misrecognized word | `The shaft is rnade of steel.` | `The shaft is made of steel.` |
| The wrong case in a designation | `Valve type hv-12` | `Valve type HV-12` |
| The wrong heading level | `## 4.2 Bearings` | `### 4.2 Bearings` |
| A broken formula; no new number can appear in it | `$\left( a + b$` | `$\left( a + b \right)$` |
| A word inside a formula | `$F = m a where$ m is the mass` | `$F = m a$ where m is the mass` |
| A lost hyphen; repaired when the hyphenated spelling occurs in the document or in the text layer of the source | `a costeffective design` | `a cost-effective design` |
| A flattened line of 100 characters or more, or 6 short lines or more in a row; all words and numbers stay | `Size Torque Weight M6 10 0.5 M8 25 0.9 …` | a table |
| A punctuation mark after the closing `$$` | `$$ v = s / t $$,` | `$$ v = s / t,$$` |

## What inspection does not change

The model repairs recognition errors, not the document itself. Typos of the
edition, lowercase letters, abbreviations, punctuation, and the alphabet of the
letters stay as they are on the page. A word break at the edge of a printed
line belongs to the layout. Therefore the model does not join it into a whole
word.

An edit does not apply when it falls into the YAML header, a code block, or an
HTML table. Inspection does not repair broken image links.

## When an edit does not apply

### Guard

The guard rejects an edit that breaks one of these rules:

| Rule | Before | Rejected edit |
|---|---|---|
| Numbers outside formulas do not change | `Rated pressure 16 bar` | `Rated pressure 10 bar` |
| A valid formula does not change | `$$ x = y^2 $$` | `$$ x = y^3 $$` |
| No new number appears in a broken formula | `$$ x = \frac{a}{ $$` | `$$ x = \frac{a}{3} $$` |
| The number of formulas in a line does not change, and no `$` or `$$` sign is left without a pair | `$a$ and $b$` | `$a and b$` |
| On the line of a display formula, only `,` `.` `;` can follow `$$` | `$$ v = s / t $$` | `$$ v = s / t $$ where v is…` |
| The number, the addresses, and the order of the image links do not change | `See Figure 3 ![](fig3.png)` | `See Figure 3` |
| The number of cells in a table row does not change; a data row stays a data row, and a delimiter row stays a delimiter row | `\| M6 \| steel \| brass \|` | `\| M6 \| steel \|` |
| Different cells of a row do not become identical | `\| a \| b \|` | `\| a \| a \|` |
| A plain line does not become a heading, and a heading does not become a plain line | `Wear limit` | `## Wear limit` |
| A space does not split a word unless both halves occur in the text layer of the page | `maintenanceinterval` | `maintenance interval` |
| A hyphen does not split a word unless that spelling occurs in the document or in the text layer | `maintenance` | `mainte-nance` |
| The hyphen of a word break at the end of a line stays | `heavy and actu-` | `heavy and` |
| The `<sub>` and `<sup>` tags stay | `CO<sub>2</sub> level` | `CO2 level` |
| A one-letter variable keeps its emphasis and its alphabet | `mass *m* here` | `mass m here` |
| The text next to a formula does not repeat what the formula already shows | `width $w\,\mathrm{mm}$ here` | `width $w\,\mathrm{mm}$ mm here` |
| No LaTeX commands appear outside formulas | `plain text` | `plain \textbf{text}` |
| No technical residue appears: a literal `\n`, JSON, or the name of a defect | `plain text` | `hyphenation` |
| One line becomes several lines only when the edit restores a flattened line or a cut formula | `Line one` | `Line one`, `Line two` |

An edit that restores a flattened line can change the number of cells, the `#`
signs of a heading, and the `<sub>` and `<sup>` tags. The model gets a
formula cut into several `$$...$$` lines under one address and repairs it as a
whole.

### Skipped edits

The tool skips an edit in these cases:

- the edit has no page number;
- the tool does not find the "before" fragment at the address or in the 40
  lines around it, or finds it more than once;
- the "before" fragment starts or ends in the middle of a word;
- the "after" fragment repeats the text of the line around the quoted
  fragment;
- two edits change the same fragment of a line.

A skipped edit does no damage: the defect stays in place.

## Settings

### `--llm-latex-fix`

The flag opens all formulas to the model, so the model can rewrite a valid
formula and add a new number to it. The other rules of the guard still apply.
A rewritten formula renders, but it can state something else. Only a manual
comparison with the page tells a repair from an invention. Therefore each run
with the flag writes a warning to the log. Without `--llm-inspection`, the tool
rejects the flag.

### Request size

Three model settings in `settings.json` limit the size of the chunk that goes
into one request:

| Setting | What it limits | Default |
|---|---|---|
| `pages_per_request` | the number of pages in a request | 8 |
| `max_request_bytes` | the size of a request | 20 MB |
| `tpm` | the number of tokens per minute; a chunk takes half of the limit at most, and the requests go with pauses | a chunk of 100,000 tokens at most |

## Large documents and errors

The tool divides the document into chunks of whole pages and sends each chunk
in a separate request. The settings in [Request size](#request-size) set the
size of a chunk.

| Situation | Result |
|---|---|
| The reply of the model is unusable | the request repeats; if the repeat fails too, the chunk divides into two halves |
| A provider error on a chunk | the tool skips the chunk and processes the other chunks; the run ends with an LLM error |
| The quota is spent, or the key is rejected | inspection stops, and the run ends with an LLM error; the edits of the chunks already done apply |
| The first chunk got no reply | inspection does not apply; the header shows `inspection: failed` |
| Not all chunks are done | `inspection_coverage` goes into `issues` |
| Fewer than half of the chunks are done | `status: bad` |

## How to see the result

Four places show the result of the stage:

- the `inspection` field in the header of the result: the model key if the
  stage succeeded; `none` if the stage was off or had nothing to compare with;
  `failed` if the stage failed;
- the files `cleaning.md`, `inspection.md`, and `acceptance.md` in the
  `<name>.debug/` folder, after a run with `--debug` (`-d`): the text before
  the edits, after the edits, and after the acceptance pass;
- the `llm/inspection.txt` file in the same folder: the requests and the
  replies of the model as they are, without the page images;
- the log `~/.raw2md/logs/raw2md.log`: for each edit, whether the tool applied,
  skipped, or rejected it, and why; each rewritten formula in the form
  "before → after".
