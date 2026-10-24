import html
import re
from typing import Literal

from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block
from raw2md_engine.marker.util import unwrap_math


def cleanup_text(full_text):
    full_text = re.sub(r"(\n\s){3,}", "\n\n", full_text)
    full_text = full_text.replace("\xa0", " ")  # Replace non-breaking spaces
    return full_text


class Span(Block):
    block_type: BlockTypes = BlockTypes.Span
    block_description: str = "A span of text inside a line."

    text: str
    font: str
    font_weight: float
    font_size: float
    minimum_position: int
    maximum_position: int
    formats: list[
        Literal[
            "plain",
            "math",
            "chemical",
            "bold",
            "italic",
            "highlight",
            "subscript",
            "superscript",
            "small",
            "code",
            "underline",
        ]
    ]
    has_superscript: bool = False
    has_subscript: bool = False
    url: str | None = None
    html: str | None = None

    @property
    def bold(self):
        return "bold" in self.formats

    @property
    def italic(self):
        return "italic" in self.formats

    @property
    def math(self):
        return "math" in self.formats

    @property
    def highlight(self):
        return "highlight" in self.formats

    @property
    def superscript(self):
        return "superscript" in self.formats

    @property
    def subscript(self):
        return "subscript" in self.formats

    @property
    def small(self):
        return "small" in self.formats

    @property
    def code(self):
        return "code" in self.formats

    @property
    def underline(self):
        return "underline" in self.formats

    def assemble_html(self, document, child_blocks, parent_structure, block_config):
        if self.ignore_for_output:
            return ""

        if self.html:
            return self.html

        text = self.text

        # Remove trailing newlines
        replaced_newline = False
        while len(text) > 0 and text[-1] in ["\n", "\r"]:
            text = text[:-1]
            replaced_newline = True

        # Remove leading newlines
        while len(text) > 0 and text[0] in ["\n", "\r"]:
            text = text[1:]

        if replaced_newline and not text.endswith("-"):
            text += " "

        text = text.replace(
            "-\n", ""
        )  # Remove hyphenated line breaks from the middle of the span
        text = html.escape(text)
        text = cleanup_text(text)

        if self.has_superscript and not self.math:
            text = re.sub(r"^([0-9\W]+)(.*)", r"<sup>\1</sup>\2", text)

            # Handle full block superscript
            if "<sup>" not in text:
                text = f"<sup>{text}</sup>"

        # Math is innermost, so that unwrap_math and the Markdown math
        # delimiters see the formula alone.
        if self.math:
            block_envs = ["split", "align", "gather", "multline"]
            if any(f"\\begin{{{env}}}" in text for env in block_envs):
                display_mode = "block"
            else:
                display_mode = "inline"
            text = unwrap_math(f"<math display='{display_mode}'>{text}</math>")
        if self.code:
            text = f"<code>{text}</code>"
        if self.subscript:
            text = f"<sub>{text}</sub>"
        if self.superscript:
            text = f"<sup>{text}</sup>"
        if self.small:
            text = f"<small>{text}</small>"
        if self.underline:
            text = f"<u>{text}</u>"
        if self.highlight:
            text = f"<mark>{text}</mark>"
        if self.url:
            text = f"<a href='{self.url}'>{text}</a>"
        if self.italic:
            text = f"<i>{text}</i>"
        if self.bold:
            text = f"<b>{text}</b>"
        return text
