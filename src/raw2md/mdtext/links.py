"""Image links, local link targets, and address masking.

An address (a link target, a URL, an e-mail) is not prose, so a detector
that reads prose masks it first, with blanks of the same width.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from raw2md.mdtext.zones import blank_match, mask_inline_code

# Addresses, not prose: link targets, `src`/`href`, bare URLs and e-mails,
# reference definitions, and a full reference's use-site label, which must
# stay identical to its definition. Collapsed and shortcut references are not
# reached; no raw2md converter emits reference links.
_LINK_TARGET_RE = re.compile(
    r"(?<=\]\()[^)\s]+"
    r'|(?<=src=")[^"]*'
    r'|(?<=href=")[^"]*'
    r"|[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s)\]]+"
    r"|[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
    r"|^ {0,3}\[[^\]]+\]:\s*\S+"
    r"|(?<=\])\[[^\]]*\]",
    re.MULTILINE,
)


# Group 2 is the target.
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')

# pandoc writes `<img>` for a docx image with a size. Group 2 is `src`, as in
# `IMAGE_RE`, so a rewrite leaves other attributes alone.
HTML_IMG_RE = re.compile(r'(<img\b[^>]*?\ssrc=")([^"]*)(")', re.IGNORECASE)

# A scheme (`http:`, `data:`, a Windows drive) marks a non-local target.
_URL_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*:")


def mask_addresses(text: str) -> str:
    """`text` with inline code and every address blanked; offsets are preserved."""
    return _LINK_TARGET_RE.sub(blank_match, mask_inline_code(text))


def is_local_target(target: str) -> bool:
    """True when `target` is a local path, not a URL or a bare fragment."""
    if not target or target.startswith(("#", "//")):
        return False
    return _URL_SCHEME_RE.match(target) is None


def local_image_path(base_dir: Path, target: str) -> Path | None:
    """Resolve a local link `target` to a filesystem path, or `None` if unsafe.

    The target is percent-decoded first. Decoding can unmask a drive, a root,
    or a `..` traversal (`C%3A%5C...`), so the resolved path must stay under
    `base_dir`. Treat `None` as a non-local target.
    """
    if not is_local_target(unquote(target)):
        return None
    resolved_base = base_dir.resolve()
    candidate = (base_dir / unquote(target)).resolve()
    if not candidate.is_relative_to(resolved_base):
        return None
    return candidate
