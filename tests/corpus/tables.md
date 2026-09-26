# Summary tables

The section collects tabular data of different kinds: plain lists, numeric
summaries, and tables with aligned columns. The tables must survive conversion
without losing columns or the order of rows.

## Format list

| Format | Processing | Media |
|---|---|---|
| PDF | recognition | yes |
| DOCX | direct conversion | yes |
| DjVu | through an image | yes |
| Markdown | cleaning only | no |

## Numeric summary

Numbers are aligned right, names left.

| Month | Received | Processed | Rejected |
|:---|---:|---:|---:|
| January | 1240 | 1198 | 42 |
| February | 1105 | 1077 | 28 |
| March | 1390 | 1352 | 38 |
| Total | 3735 | 3627 | 108 |

## Table with gaps

An empty cell is marked with a dash and must survive as a meaningful character.

| Parameter | Value | Note |
|---|---|---|
| Resolution | 300 dpi | — |
| Colour | greyscale | for scans |
| Margins | — | cropped automatically |
| Skew | up to 2° | corrected |

## Mode comparison

| Mode | Speed | Quality | When to use |
|---|---|---|---|
| Basic | high | medium | clean text layer |
| Recognition | low | high | scans without text |
| With post-processing | low | high | complex layout |

## Centre alignment

All columns are centred – an edge case of alignment that checks that the
alignment type does not raise a false positive of §7.

| Code | Status | Action |
|:---:|:---:|:---:|
| 0 | success | continue |
| 1 | partial | check the log |
| 2 | error | fix the configuration |
| 3 | failure | install the dependencies |

## Empty cells without a dash

Cells without content (nothing between the separators) must not break the §7
column count or shift the neighbouring data.

| Parameter | Primary | Backup |
|---|---|---|
| Host | server.local | |
| Port | 8080 | 9090 |
| Timeout | | 30 s |
| Protocol | HTTPS | HTTP |
