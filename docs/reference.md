# Reference

This reference describes the commands and flags of raw2md, the result files,
the header, the service files, the exit codes, and the environment
requirements. The guides to [cleaning](cleaning.md),
[inspection](inspection.md), [post-processing](post.md), and
[quality evaluation](quality.md) describe what each stage does.

## Usage

```text
raw2md [INPUT] [flags]        # convert a file or a folder
raw2md resume [show|path]     # continue an interrupted run
raw2md init [MODEL ...]       # create the missing service files
raw2md settings <action>      # path | show | edit | check
raw2md prompts  <action>      # path | show | edit | check
raw2md keywords <action>      # path | show | edit | check
raw2md doctor                 # check the tools and the settings
```

`INPUT` is a file with an extension (`raw2md book.pdf`) or a folder
(`raw2md scans`, `./scans`, `D:/books/scans`). Without `INPUT`, the tool
processes the current folder. To give a folder whose name matches a
subcommand, give it as a path: `./resume`.

| Input | Converter | Result |
|---|---|---|
| `pdf` | `marker`, or the model from `-e` | `md` and an image folder; with `-e <model>`, only `md` |
| `djvu` | `ddjvu` to PDF, then as `pdf` | the same as for `pdf` |
| `docx` | `pandoc` | `md` and an image folder |
| `md` | none: the file goes to cleaning without conversion | `md` |

The tool does not go into the subfolders of a folder. It takes the files from
the top of the folder in alphabetical order. It skips the files of other
formats without a message. It processes the files one at a time, because
`marker` takes the whole GPU.

The tool always cleans an `md` file that you give explicitly. In a folder, the
tool treats an `md` file with a raw2md header as an earlier result. It skips
such a file if the results go into the same folder. To clean such files again,
set another folder with `-o`.

## Flags

| Short | Flag | What it does | Default |
|---|---|---|---|
| `-o` | `--output-dir DIR` | writes the results to `DIR`, not next to the source | the source folder |
| `-e` | `--engine <engine>` | the engine for `pdf` and `djvu`: `marker`, or a model key for LLM-OCR mode; `pandoc` always converts `docx` | `marker` |
| `-i` | `--llm-inspection <model>` | turns on inspection; only for `pdf` and `djvu` | `none` |
| `-p` | `--llm-post <model>` | turns on post-processing | `none` |
| `-s` | `--skip-existing` | keeps a finished result and does not convert the file again | replaces the result |
| `-d` | `--debug` | saves the text after each stage next to the result | off |
| `-v` | `--version` | prints the version and exits | – |
| `-h` | `--help` | prints the list of flags and exits | – |
| – | `--llm-latex-fix` | lets inspection rewrite any formula; rejected without `-i` | off |
| – | `--disable-image-extraction` | does not extract images; the links to them are deleted, and the captions stay | extracts |
| – | `--no-yaml` | removes the header from the result | with the header |
| – | `--cuda on\|off` | `on`: the GPU if CUDA is available, otherwise the CPU with a log entry; `off`: the CPU only | `on` |
| – | `--no-log-file` | does not write the detailed log | writes the log |

The model in `-e`, `-i`, and `-p` is a key from `settings.json`. The key must
be in `operations.<operation>.allowed` for its operation: `ocr` for `-e`,
`inspection` for `-i`, and `post` for `-p`. Otherwise the run ends with an
argument error. The flags of the LLM stages are independent: you can turn on
each stage without the others.

In LLM-OCR mode, the model recognizes the whole page and does not extract
images. Therefore `--disable-image-extraction` changes nothing in this mode.

The `-e` and `-i` flags have no effect on `docx` and `md`. A `docx` file always
goes through `pandoc`, and an `md` file skips conversion. Inspection
compares the text with the pages of the source, and these formats have no
pages. Therefore the header keeps `inspection: none`.

## Result files

The tool writes the result next to the source, under the same name with the
`md` extension. The images go into a folder with the same name, without an
extension. The folder appears only when the document has something to extract.

```text
book.pdf          # source
book.md           # result
book/             # images
book.debug/       # stage snapshots, only with -d
```

The image links are relative and use the `/` separator. Therefore you can move
the result together with the image folder. In a link path, spaces and the
characters `%`, `<`, `>`, `(`, `)`, `#`, and `?` become `%xx`. Cyrillic letters
stay as they are. The tool deletes the internal page links of the converter and
keeps their visible text.

### Names

| Case | Result |
|---|---|
| `book.pdf` | `book.md`, the folder `book/` |
| `book.pdf` and `book.djvu` in one folder | `book.pdf.md` and `book.djvu.md`, the folders `book.pdf/` and `book.djvu/` |
| `notes.md` without `-o` | `notes_cleaned.md`: the source is not overwritten |
| `notes.md` with `-o` | `notes.md` in the `-o` folder |
| `Report..pdf` | `Report.md`: dots and spaces at the end of the name are deleted |

The case of the extension does not matter: `.PDF` and `.pdf` are one format.
The tool compares names without case on every system, as Windows does.
Therefore `Book.pdf` and `book.pdf` conflict. On Linux, these two files get the
names `Book.pdf.md` and `book.pdf.md`. These names still match without case, so
the second result replaces the first one.

### Repeated run

The tool decides by the name of the `md` result:

| What is at the place of the result | Without `-s` | With `-s` |
|---|---|---|
| a raw2md result | replaced, together with the image folder and the `.debug` folder | stays; the file is not converted |
| an `md` without a raw2md header, a `--no-yaml` result included | the file is not processed; an error | the same |
| the stub of an interrupted run (`status: in_progress`) | replaced | replaced |

The `-s` flag does not read the source: the result stays even if the source
changed since then. The tool deletes the old result before the conversion.
Therefore, if the conversion fails, no result remains. The exception is a
source whose bytes do not match the extension: the tool rejects it before it
deletes the old result.

### The `.debug` folder

With the `-d` flag, the `<name>.debug/` folder keeps the text after each stage
that ran:

| File | When it appears | What it holds |
|---|---|---|
| `conversion.md` | always | the output of the converter |
| `cleaning.md` | always | the text after cleaning |
| `inspection.md` | with `-i` on `pdf` and `djvu` | the text after the inspection edits |
| `acceptance.md` | together with `inspection.md` | the text after the acceptance pass |
| `post.md` | with `-p` | the text after post-processing |
| `llm/inspection.txt`, `llm/post.txt`, `llm/ocr.txt` | if the stage sent at least one request | the requests and the replies of the model as they are, without images |

The `.debug` folder of an earlier run is replaced together with the result, so
the snapshots of different runs do not mix. Without `-d`, the tool does not
touch the folder. If LLM-OCR ends with an error, `llm/ocr.txt` stays: it holds
the replies that you already paid for.

## Header

Each result starts with a YAML header, unless you set `--no-yaml`:

```yaml
---
raw2md_version: 0.1.0
source: book.pdf
engine: marker
inspection: none
post: none
converted_at: 2026-10-03
source_hash: 9rZ2...
status: ok
issues: [headings]
---
```

| Field | Value |
|---|---|
| `raw2md_version` | the version of raw2md; the tool recognizes its own header by this field |
| `source` | the name of the source, with the extension |
| `engine` | what converted the file: `marker`, `pandoc` (`docx`), `clean` (`md`), or the model key in LLM-OCR mode |
| `inspection` | `none`: the stage was off, or it had nothing to compare with (`docx`, `md`); the model key: the stage succeeded; `failed`: the stage failed |
| `post` | `none`, the model key, or `failed`, as for `inspection`; `partial (N/M)`: N zones of M came back |
| `converted_at` | the date of the conversion |
| `source_hash` | the SHA-256 of the source in base64url; by this field, `resume` finds out that the file is already done |
| `status` | `ok` or `bad`: the verdict of quality evaluation; `in_progress`: the tool still processes the file, or the run was interrupted |
| `issues` | the checks of quality evaluation that fired; the field is present only when the list is not empty |

The tool writes `engine` for each file separately: in a run with
`-e <model>`, a `docx` still shows `pandoc`. A stage that succeeded and changed
nothing still writes the model key. The value `failed` does not change
`status`. If an LLM stage fails, the tool still writes the result without it
and evaluates the result.

If the conversion fails, the tool creates no `md` file. It writes the file name
and the reason to the log.

## Interrupted runs

At the start of a run, the tool makes a queue of files and saves it with the
flags in `~/.raw2md/state/queue.json`. The whole system has one queue.

| Command | What it does |
|---|---|
| `raw2md resume` | continues the queue with the same flags; the tool rejects flags given now |
| `raw2md resume show` | prints the queue |
| `raw2md resume path` | prints the path to `queue.json` |

On resume, the tool skips a file whose result has the status `ok` or `bad` and
the `source_hash` of this source. It converts the other files again, the files
with an `in_progress` stub included. It skips the sources that disappeared. The
tool deletes the queue when all files are done or skipped. If at least one file
ended with an error, the queue stays for `resume`.

A new run with `INPUT` replaces the queue. Two runs cannot go at the same time:
the second one ends with the code `3`. The subcommands `doctor`, `init`,
`settings`, `prompts`, `keywords`, `resume show`, and `resume path` also work
during a run.

`Ctrl+C` stops the run with the code `130`. The tool prints the summary line,
and the queue stays for `resume`.

## Service files

The service files are in the `.raw2md` folder in the home folder of the user:

```text
~/.raw2md/
  settings.json     # models and settings
  prompts.yaml      # prompts of the LLM stages
  keywords.yaml     # words that the cleaning rules look for
  state/            # queue, lock, daily request counter
  logs/raw2md.log   # log of the last run
  tmp/              # temporary conversion files
```

The `raw2md init` command creates the missing files from the shipped templates
and does not touch the existing files. Without a file, the built-in values
apply. The `raw2md init MODEL ...` command keeps only the named models in the
new `settings.json`. If none of them can read images, `init` warns that LLM-OCR
and inspection have no model.

Each file has four actions:

| Action | What it does |
|---|---|
| `path` | prints the path to the file |
| `show` | prints the file; if the file does not exist, says so with the code `0` |
| `edit` | opens the file in `notepad` (Windows) or `nano` (Linux) |
| `check` | validates the syntax and the schema; an error gives the code `2`, and a missing file gives the code `0` |

The `settings check` action does not check the keys, the commands, and the
access to the models. The `raw2md doctor` command does that.

### `settings.json`

A command-line flag has priority over `settings.json`, and `settings.json` has
priority over a built-in value. This is the template that `init` writes:

```json
{
  "models": {
    "gemini_api": {
      "access": "api",
      "key_env": "GOOGLE_API_KEY",
      "model": "gemini-3.5-flash-lite",
      "rpm": 15,
      "tpm": 250000,
      "rpd": 500,
      "rpd_reset_zone": "America/Los_Angeles",
      "pages_per_request": 8,
      "max_request_bytes": 20971520
    },
    "claude_cli": {
      "access": "cli",
      "command": "claude",
      "model": "claude-sonnet-5",
      "cli_timeout_s": 120
    }
  },
  "operations": {
    "ocr": {"allowed": ["gemini_api"]},
    "inspection": {"allowed": ["gemini_api"]},
    "post": {"allowed": ["claude_cli", "gemini_api"]}
  },
  "marker": {"recognition_batch_size": "default"},
  "cleaning": {"witness_min": 20},
  "log_file": true
}
```

The `models` section describes the models. The `operations` section sets which
models each operation permits: `ocr` (LLM-OCR), `inspection`, and `post`. A
model key can be any name except `none`, `failed`, `partial`, `marker`,
`pandoc`, and `djvu`. The header fields and the `-e` flag use these values. A
model with `cli` access does not see images. Therefore it does not fit `ocr`
and `inspection`.

| Model field | Access | What it sets | If not set |
|---|---|---|---|
| `access` | all | `api`: requests through an API; `cli`: a call to a program | required |
| `model` | all | the model name at the provider | required |
| `key_env` | `api` | the environment variable with the API key | required |
| `command` | `cli` | the command that the tool calls | required |
| `rpm` | all | requests per minute; the pause between requests is `60/rpm` seconds at least | no pause |
| `tpm` | all | tokens per minute; inspection uses it to divide the document into chunks and to pause between requests | chunks of up to 100,000 tokens, no pauses |
| `rpd` | all | requests per day; the tool does not send a request over the limit, and the run ends with an LLM error | no limit |
| `rpd_reset_zone` | all | the IANA time zone in which `rpd` resets | `America/Los_Angeles` |
| `pages_per_request` | all | pages of the source in one request | 8 |
| `max_request_bytes` | all | the size of one request | 20 MB |
| `temperature` | `api` | the temperature of the model, from 0.0 to 2.0 | the provider value |
| `cli_timeout_s` | `cli` | how many seconds to wait for the reply of the program | 120 |

The `rpd` counter is in `~/.raw2md/state/rpd.json`, by model name, and it
survives a restart. After a provider error `429` or `5xx`, the tool repeats the
request several times with a growing pause.

| Section | Field | What it sets | Default |
|---|---|---|---|
| `marker` | `recognition_batch_size` | the recognition batch size of `marker`; a smaller number uses less video memory | `"default"`: the `marker` value for the video memory |
| `cleaning` | `witness_min` | how many times a spelling must occur in the document before cleaning repairs a damaged word with it; 2 at least | 20 |
| – | `log_file` | whether to write the detailed log; `--no-log-file` turns the log off, but it cannot turn the log on | `true` |

### `prompts.yaml`

The prompts of the LLM stages: a base prompt for each operation and, as an
option, a separate prompt for one model.

```yaml
ocr:
  default: |
    ...
inspection:
  default: |
    ...
post:
  default: |
    ...
  claude_cli: |     # a prompt for this model only
    ...
```

While the file exists, the tool does not read the prompts of a new raw2md
version, and `init` does not update an existing file. After you update raw2md,
delete the old file and run `raw2md init`, or move your changes into the new
template.

### `keywords.yaml`

The file holds the words by which the cleaning rules find the parts of a
document. Such a part can be the heading of the table of contents, the label of
the page column, or a top-level section. It can also be an image or table
caption, a function word in a heading, or the model note for an image. Each
section of the file lists entries of three kinds: a whole word (`chart`), a
word start (`appendix*`), or an abbreviation with a dot (`рис.`). An entry can
hold several words (`table of contents`). The case does not matter.

The copy in `~/.raw2md` replaces the shipped list completely. A section that
the copy does not have stays empty, and the rule of that section finds nothing.

## Exit codes

| Code | When |
|---|---|
| `0` | all files got an `ok` or `bad` result, or were skipped |
| `1` | in a folder, at least one file ended with an error; the log gives the kind of error |
| `2` | an error in the arguments or in `settings.json` |
| `3` | a dependency is missing: a model is not available (no key, a rejected key, the program is not installed, or no login); another run already goes on; the temporary folder is not suitable |
| `4` | a single file: no result (a conversion error, a damaged or protected source, a foreign `md` at the place of the result) |
| `5` | a single file: an LLM stage failed, or the request limit is spent |
| `130` | `Ctrl+C` stopped the run |

The tool returns the codes `2` and `3` before it processes the first file. The
value `status: bad` is a quality verdict, not an error, and it does not change
the exit code. If an LLM stage fails, the tool still writes the result without
it, and the exit code reports the error.

The subcommands `settings`, `prompts`, `keywords`, `init`, and `resume show`
return `1` if they cannot read or write a file. The `doctor` subcommand returns
`0` if everything is ready, `2` for an error in `settings.json`, and `3` if a
dependency is missing.

### Errors of single files

An error in one file does not stop the run on a folder. The log records the
file, and the processing goes on.

| Situation | What happens |
|---|---|
| An empty or password-protected source; the bytes do not match the extension (a `doc` under a `docx` name) | no result; the old result stays in place |
| A source that the converter cannot open | no result; the tool deleted the old result before the conversion |
| No `pandoc` or `ddjvu` | the tool skips the files of that format with an error and processes the other files |
| A request larger than `max_request_bytes` | the tool skips the LLM stage and writes the result without it; in LLM-OCR mode, no result |
| The quota is spent, or a provider error | the tool writes the result with the edits that the stage made before the error; in LLM-OCR mode, no result |

## Console and log

The console always shows:

- the start line of the run: the folder, the number of files, and the time;
- a warning for each `bad` result, with the checks that fired and, if there is
  one, a [hint](quality.md#hints-in-the-log) from the quality evaluation guide;
- the errors;
- with `-s`, a line about each result that the tool kept;
- the summary line: the number of files, the time, the speed in files per
  minute, the number of errors, and the number of `bad` results.

During a run, two progress bars show: one for the current file, with the name
of the stage, and one for the whole run.

The tool writes the detailed log to `~/.raw2md/logs/raw2md.log` and overwrites
it at the start of each run. The log holds the same lines as the console, plus
the details of each stage. The output of `marker` does not go into the log. To
turn the log off, use the `--no-log-file` flag or the `log_file: false` field.
The console colors the entries by level when the output goes to a terminal and
the `NO_COLOR` variable is not set. The tool writes the result and the log in
UTF-8 without a byte order mark.

## Environment

| Requirement | What you need |
|---|---|
| System | Windows or Linux; macOS is not tested |
| Python | 3.11 to 3.13 |
| GPU | NVIDIA Turing or newer (`sm_75`+), driver 580 or newer; without a GPU, `marker` runs on the CPU, but this mode is not supported |
| `pandoc` | 3.1.9 or newer, only for `docx` |
| `ddjvu` (DjVuLibre) | only for `djvu` |

The raw2md install includes `marker`. You install `pandoc` and `ddjvu`
separately. If one of them is missing, only its format does not work. The
`raw2md doctor` command checks the engines, the torch build, the GPU
visibility, `settings.json`, and the access to each permitted model. If CUDA is
not available, `doctor` gives the reason: a CPU build of torch, or a driver
that does not see the GPU.

| Variable | What it sets |
|---|---|
| the `key_env` of the model, `GOOGLE_API_KEY` in the template | the API key of the model |
| `RAW2MD_TMP` | the temporary folder of the conversion |
| `NO_COLOR` | turns off the colors in the console |

The path of the temporary folder must hold only Latin characters, and the
folder must be writable. Without `RAW2MD_TMP`, the tool uses `~/.raw2md/tmp` if
its path is Latin. Otherwise it uses `C:\raw2md-tmp` on Windows and
`/tmp/raw2md` on Linux. If the path is not suitable, the run ends with the code
`3` before the conversion.
