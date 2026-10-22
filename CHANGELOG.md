# Changelog

Each section holds the notes of one release, newest first. The GitHub release
of the version carries the same text.

## v0.2.1 - 2026-10-22

### Security

- Require fixed certifi and keep dev lock files out of the sdist ([#20](https://github.com/MikeDolg/raw2md/pull/20))
- Require Pillow 13.0.0 ([#22](https://github.com/MikeDolg/raw2md/pull/22))

Full changelog: <https://github.com/MikeDolg/raw2md/compare/v0.2.0...v0.2.1>

## v0.2.0 - 2026-10-20

### Bug fixes

- Check media asset names against the media folder ([#17](https://github.com/MikeDolg/raw2md/pull/17))

### Features

- feat: bundle the conversion engine as raw2md-engine ([#10](https://github.com/MikeDolg/raw2md/pull/10))
- Replace PyMuPDF with pypdfium2 for PDF analysis ([#14](https://github.com/MikeDolg/raw2md/pull/14))

### Maintenance

- Move to transformers 5 ([#15](https://github.com/MikeDolg/raw2md/pull/15))
- Keep the real subprocess.run in tests and run Windows CI on every Python ([#18](https://github.com/MikeDolg/raw2md/pull/18))

Full changelog: <https://github.com/MikeDolg/raw2md/compare/v0.1.1...v0.2.0>

## v0.1.1 - 2026-10-13

### Bug fixes

- fix(llm): isolate claude_cli and add the security policy ([#4](https://github.com/MikeDolg/raw2md/pull/4))
- fix(cleaning): fold edge punctuation of heading titles ([#7](https://github.com/MikeDolg/raw2md/pull/7))
- fix(cleaning): drop contents headings on continuation pages ([#8](https://github.com/MikeDolg/raw2md/pull/8))

### Maintenance

- Default claude_cli model: Sonnet 5.5 ([#2](https://github.com/MikeDolg/raw2md/pull/2))

Full changelog: <https://github.com/MikeDolg/raw2md/compare/v0.1.0...v0.1.1>

## v0.1.0 - 2026-10-06

raw2md 0.1.0 is the first public release.

raw2md is a command-line tool that converts PDF, DjVu, and DOCX documents into clean Markdown for RAG and other LLM pipelines. It runs the conversion with `marker`, `pandoc`, or Gemini, then repairs the defects that these engines leave in headings, tables, formulas, lists, and text. The cleaning uses deterministic rules and no LLM. Two optional LLM stages repair what the rules leave.

Install with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install raw2md --torch-backend cu130
```

Requirements: Python 3.11 to 3.13, Linux or Windows, and an NVIDIA GPU of the Turing generation or newer for `marker`. DOCX needs `pandoc` 3.1.9 or later, and DjVu needs DjVuLibre.

Documentation: <https://github.com/MikeDolg/raw2md/blob/main/docs/README.md>
