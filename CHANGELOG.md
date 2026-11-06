# Changelog

Each section holds the notes of one release, newest first. The GitHub release
of the version carries the same text.

## v0.3.0 - 2026-11-06

### Bug fixes

- Fix the deterministic defects of the engine copy ([#26](https://github.com/MikeDolg/raw2md/pull/26))
- Stop two quality checks from failing correct output ([#30](https://github.com/MikeDolg/raw2md/pull/30))

### Features

- Grade each quality check and write a score to the header ([#31](https://github.com/MikeDolg/raw2md/pull/31))
- Save the engine's HTML and block tree in the .debug folder ([#32](https://github.com/MikeDolg/raw2md/pull/32))
- Show engine phase progress and log it for agents ([#35](https://github.com/MikeDolg/raw2md/pull/35))
- Move to torch 2.14 and current releases; the engine output changes ([#36](https://github.com/MikeDolg/raw2md/pull/36))
- Score Figure F1 and Overall in the MPDocBench benchmark ([#38](https://github.com/MikeDolg/raw2md/pull/38))

Full changelog: <https://github.com/MikeDolg/raw2md/compare/v0.2.2...v0.3.0>

## v0.2.2 - 2026-10-23

### Bug fixes

- Pin the Python range in the `uv tool install` commands, so that a default Python newer than 3.14 no longer picks an old release

### Maintenance

- Move the MPDocBench scorer to Python 3.14 and current pins ([#24](https://github.com/MikeDolg/raw2md/pull/24))

Full changelog: <https://github.com/MikeDolg/raw2md/compare/v0.2.1...v0.2.2>

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
