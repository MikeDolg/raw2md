# Document management guide

This guide sets the order in which the organisation receives, registers,
processes, and stores documents. It covers the technical requirements for
formats, the conversion procedures, the quality control of the output, and the
rules of long-term storage. The document is meant for operators and system
administrators who are responsible for the document flow.

The instruction takes effect when it is approved and stays in force until an
updated edition appears. Every change is made by publishing a new version;
earlier editions are kept in the archive as reference material.

## General provisions

The organisation works with documents of different kinds: paper, scanned, and
born digital. Paper documents are scanned before processing; scanned ones are
kept as images until recognition starts; digital ones enter the system
directly, without a preliminary conversion.

Whatever the source format, the end result is a structured text file with
Markdown markup. Such a file is easy to search, edit, and put under version
control; it is much smaller than a raster scan and depends on no proprietary
format.

For each incoming document, an entry is created in the processing log: the
time of arrival, the file type, the chosen engine, the final status, and the
path to the result. The entries are kept without a time limit and are not
deleted when the document is reprocessed or updated. The log is kept in CSV
format and is fit for automatic parsing.

## Intake and registration

A document counts as received when the file is saved in the working folder and
the log entry exists. Until then the file stays in the waiting state and is not
passed to processing. The working folder is checked for free space before each
batch run.

The registration number is assigned automatically by the scheme
"year-month-day-sequence". Documents received within one day get consecutive
sequence numbers, whatever the exact time of arrival. The number does not
change when the document is processed again.

In batch processing, files are registered in the alphabetical order of their
names in the folder. When the folder holds subfolders, their content is added
recursively after the top-level files. This rule gives a reproducible
registration order on repeated runs with the same source data.

## Conversion and recognition

The conversion engine is chosen by the type of the source file. PDF files with
a text layer are processed directly: the engine extracts the text without a
call to the image recognition module. Scanned PDF and DjVu files go to the OCR
module. DOCX files are converted through pandoc, which keeps the structure of
headings and tables. Markdown files pass through the markup cleaning stage only.

Recognition takes most of the processing time. On machines with a graphics card
that supports CUDA, it runs several times faster than in the central processor
mode. Without a GPU, one multi-page PDF can take several minutes. Users are
advised to run heavy batches outside working hours or on a dedicated server.

Temporary files are written to a separate folder whose path is chosen
automatically. The path must be ASCII-compatible, because the recognition
module does not support Unicode in paths. When the automatic path is not
available, the user can set it through an environment variable. When no
acceptable path is found, processing stops with an error code.

## Cleaning and quality grading

After conversion the text goes through deterministic cleaning. Unambiguous
defects are fixed automatically: extra blank lines, the space after a heading
sign, lines made of service characters only. Ambiguous places are marked with
special anchor comments for later review by a language model.

The quality grade uses independent criteria. Text density – the number of
characters per source page – shows a recognition failure: when the engine
returns an almost empty result for a multi-page source, that is a clear signal
of a problem. The share of unreadable characters shows whether the output is
littered with garbage instead of normal text.

Table integrity is checked row by row: every body row must hold the same number
of columns as the header. Formula correctness is checked syntactically:
unclosed or nested formula delimiters are recorded as a defect.

The final status of a document is "success" or "with remarks". "Success" is set
when none of the checks fired. "With remarks" means that there are repairable
format defects or signals of a recognition failure.

## Storage and archiving

The result is saved next to the source file under the same name with the `.md`
extension. When a file with that name already exists, a run flag decides what
happens: by default the existing file is not overwritten, and the operation is
skipped with a matching entry in the log.

The service header at the start of the result file holds the metadata: the
source path, the content hash, the tool version, the conversion method, and the
final status. The hash detects a change of the source on the next run: when
the hash matches, the file is skipped without a new conversion.

For long-term storage, a regular backup of the results folder is advised.
Markdown files are text and compress well with differential compression. To
move results between systems, it is enough to copy the `.md` file and the
folder with the extracted media next to it; all media links are relative, which
keeps them portable.

## Updates and support

The tool is updated through the standard package manager. An update does not
touch existing results: each file carries the tool version in its header, which
tells when it was created and whether it needs processing again. The user
decides whether to regenerate it.

When an error occurs, the log holds the traceback and the exact return code.
The standard codes are documented in the technical specification. Code 3 means
that a dependency is not available: on this code, check that pandoc, marker,
and djvulibre are installed on the system.

Support runs through an issue tracker. A bug report must contain the source
file (or a reproducible minimal equivalent), the full log at DEBUG level, the
tool version, and the operating system. Reports without a reproducing example
are not reviewed.
