# Document conversion procedure

This document sets the order in which incoming material is processed and how
responsibility is split between the stages. Each section matches one stage of
processing and, where needed, is refined by subsections without skipped levels.

## Intake of material

At this stage the received files are registered and checked for fitness for
further processing. Rejected material goes back to the sender with the reason
stated.

### Format check

The accepted formats are listed in the appendix. A file of an unknown format
waits for a manual decision by the operator.

### Integrity check

A damaged or password-protected file is flagged and is not passed on until the
cause is removed.

## Recognition

The stage turns the source file into marked-up text. The recognition method is
chosen automatically from the file type and the presence of a text layer.

### Text layer

When a text layer is present, it is used directly, without a call to image
recognition.

### Image recognition

When there is no text layer, the page is rendered to an image and passed to the
recognition module.

#### Page preparation

The page is brought to the working resolution, the margins are cropped, and the
skew is corrected.

#### Quality control

The result is graded by text density and the share of unreadable characters; at
low quality the material is sent for processing again.

## Result export

The finished text is saved next to the source, carries a service header, and is
proofread by hand when needed.

### Storage

Results are filed in a folder by processing date and are kept for the agreed
period.

### Reporting

When a batch ends, a summary is produced: the number of processed files, the
share of successes, and the list of rejected material.

<!-- markdownlint-disable-next-line MD003 -- fixture: setext H2 is the point -->
Final reconciliation
--------------------

This second-level heading uses the alternative notation: the text on top, a
line of hyphens below, and no `#` sign. Both heading forms are equivalent, and
the converter must keep both.
