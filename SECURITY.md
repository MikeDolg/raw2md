# Security

raw2md is provided under the GPL-3.0-or-later license, without warranty
of any kind.
This document describes the principles that guide its development. It
does not add a warranty or a commitment.

## Design principles

1. **Untrusted input.** raw2md treats document content as untrusted
   data. It does not run scripts or follow links embedded in a document.
2. **Local by default.** Without LLM options (an LLM model in `--engine`,
   `--inspection`, `--post`), raw2md does not intentionally send document
   content to external services.
3. **Runtime downloads.** Some engines download models or other runtime
   assets, especially on first use. The download happens while the
   engine loads its models; the document is not passed to that step.
4. **LLM isolation.** LLM providers get no tools. The `claude_cli`
   provider runs without tools, MCP servers, or user settings, preventing
   document instructions from invoking those capabilities.
5. **LLM output.** Instructions in a document can still change what an
   LLM stage writes. Edit guards limit the extent of a change; they do
   not prove that the result is correct.
6. **Output content.** Raw HTML and links from the source may be
   preserved in the output.
7. **Debug files.** With `--debug`, raw2md writes stage snapshots and the
   text of LLM requests and replies to a `.debug` folder next to the
   result. These files hold document text.

## User responsibility

- Before you enable an LLM stage, make sure that you may disclose the
  document to that provider. With `claude_cli`, the requests run under
  your own account and the terms of your provider.
- If you render the output as HTML, use a sanitizer or a renderer that
  disables raw HTML.

## Non-goals

- raw2md assumes that the user controls the input and output
  directories. It does not defend against an attacker who can change
  them, for example through symbolic links.
- raw2md sets no limits on memory, disk, or run time for a hostile
  file. A service that converts files from untrusted users needs its
  own sandbox and resource limits.

## Reporting a vulnerability

Report a vulnerability through GitHub private vulnerability reporting in
this repository. Do not open a public issue. Include the raw2md version,
the command, and, if possible, a minimal file that shows the problem.
