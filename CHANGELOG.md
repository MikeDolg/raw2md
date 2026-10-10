# Changelog

Each section holds the notes of one release, newest first. The GitHub release
of the version carries the same text.

## v0.1.0 - 2026-10-06

raw2md 0.1.0 is the first public release.

raw2md is a command-line tool that converts PDF, DjVu, and DOCX documents into clean Markdown for RAG and other LLM pipelines. It runs the conversion with `marker`, `pandoc`, or Gemini, then repairs the defects that these engines leave in headings, tables, formulas, lists, and text. The cleaning uses deterministic rules and no LLM. Two optional LLM stages repair what the rules leave.

Install with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install raw2md --torch-backend cu130
```

Requirements: Python 3.11 to 3.13, Linux or Windows, and an NVIDIA GPU of the Turing generation or newer for `marker`. DOCX needs `pandoc` 3.1.9 or later, and DjVu needs DjVuLibre.

Documentation: <https://github.com/MikeDolg/raw2md/blob/main/docs/README.md>
