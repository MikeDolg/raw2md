import re
from typing import Annotated

import regex
from bs4 import BeautifulSoup
from ftfy import fix_text
from PIL import Image

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.document import Document
from raw2md_engine.marker.settings import settings
from raw2md_engine.marker.util import fix_text_keep_width
from raw2md_engine.surya.recognition import OCRResult, RecognitionPredictor

MATH_TAG_PATTERN = re.compile(r"<math[^>]*>(.*?)</math>")
# The model may open or close a formula with a literal `\n`; `\nabla` stays.
MATH_NEWLINE_PATTERN = re.compile(r"^\\n(?![a-zA-Z])|\\n$")
# A word is two letters or more of any script; a lone letter is a variable.
WORD_PATTERN = regex.compile(r"(?:\p{L}\p{M}*){2,}")
BRACKET_PAIRS = {("[", "]"), ("(", ")")}
# A condition such as `[ab \neq 0]` states a relation and holds no word of
# three letters or more once its commands are dropped, so it is not prose.
SQUARE_GROUP_PATTERN = re.compile(r"\[[^\[\]]*\]")
RELATION_PATTERN = re.compile(
    r"[<>=]|\\(?:neq|ne|leqslant|geqslant|leq|le|geq|ge|ll|gg|equiv|approx"
    r"|sim|in|notin|to)(?![A-Za-z])"
)
COMMAND_PATTERN = re.compile(r"\\[A-Za-z]+")
CONDITION_WORD_PATTERN = regex.compile(r"(?:\p{L}\p{M}*){3,}")


class EquationProcessor(BaseProcessor):
    """
    A processor for recognizing equations in the document.
    """

    block_types: Annotated[
        tuple[BlockTypes],
        "The block types to process.",
    ] = (BlockTypes.Equation,)
    model_max_length: Annotated[
        int,
        "The maximum number of tokens to allow for the Recognition model.",
    ] = 1024
    equation_batch_size: Annotated[
        int,
        "The batch size to use for the recognition model while processing equations.",
        "Default is None, which will use the default batch size for the model.",
    ] = None
    disable_tqdm: Annotated[
        bool,
        "Whether to disable the tqdm progress bar.",
    ] = False
    drop_repeated_text: Annotated[bool, "Drop repeated text in OCR results."] = False

    def __init__(self, recognition_model: RecognitionPredictor, config=None):
        super().__init__(config)

        self.recognition_model = recognition_model

    def get_batch_size(self):
        # Set to 1/4th of OCR batch size due to sequence length with tiling
        if self.equation_batch_size is not None:
            return self.equation_batch_size
        if settings.TORCH_DEVICE_MODEL == "cuda":
            return 32
        if settings.TORCH_DEVICE_MODEL == "mps":
            return 6
        return 6

    def __call__(self, document: Document):
        images = []
        equation_boxes = []
        equation_block_ids = []
        total_equation_blocks = 0

        for page in document.pages:
            page_image = page.get_image(highres=True)
            page_size = page.polygon.width, page.polygon.height
            image_size = page_image.size

            page_equation_boxes = []
            page_equation_block_ids = []
            equation_blocks = page.contained_blocks(document, self.block_types)
            for block in equation_blocks:
                page_equation_boxes.append(
                    block.polygon.rescale(page_size, image_size).bbox
                )
                page_equation_block_ids.append(block.id)
                total_equation_blocks += 1

            images.append(page_image)
            equation_boxes.append(page_equation_boxes)
            equation_block_ids.append(page_equation_block_ids)

        if total_equation_blocks == 0:
            return

        predictions = self.get_latex_batched(images, equation_boxes)
        for page_predictions, page_equation_block_ids in zip(
            predictions, equation_block_ids
        ):
            assert len(page_predictions) == len(page_equation_block_ids), (
                "Every equation block should have a corresponding prediction"
            )
            for block_prediction, block_id in zip(
                page_predictions, page_equation_block_ids
            ):
                block = document.get_block(block_id)
                block.html = self.block_html(block_prediction, block.raw_text(document))

    def block_html(self, prediction: str, layer_text: str):
        html = self.fix_latex(prediction)
        # Without math the model read plain text, which the text layer of the
        # block holds exactly; an empty html renders that layer.
        if "<math" not in html and layer_text.strip():
            return ""
        return html

    def fix_latex(self, math_html: str):
        """Keep every formula and the text around it.

        Text outside the formulas with a word in it makes a line with inline
        math. Otherwise each formula is a display formula, and the punctuation
        and numbers stay between them in order.
        """
        soup = BeautifulSoup(math_html.strip(), "html.parser")
        for br in soup.find_all("br"):
            br.replace_with(" ")
        math_tags = soup.find_all("math")
        for tag in math_tags:
            tag.string = fix_text(MATH_NEWLINE_PATTERN.sub("", tag.get_text()))
        texts = [t for t in soup.find_all(string=True) if not t.find_parent("math")]
        fixed = [fix_text_keep_width(str(text)) for text in texts]
        is_line = any(
            WORD_PATTERN.search(SQUARE_GROUP_PATTERN.sub(self.drop_condition, text))
            for text in fixed
        )
        for text, new in zip(texts, fixed, strict=True):
            # Each display formula takes a line of its own, so the text between
            # two of them keeps no spaces; a bare space keeps a blank line.
            text.replace_with(
                new.strip() or new if len(math_tags) > 1 and not is_line else new
            )
        for tag in math_tags:
            if is_line or self.is_bracketed(tag):
                tag.attrs.pop("display", None)
            else:
                tag.attrs["display"] = "block"
        return str(soup)

    @staticmethod
    def drop_condition(group: re.Match) -> str:
        body = group.group(0)
        if not RELATION_PATTERN.search(body):
            return body
        if CONDITION_WORD_PATTERN.search(COMMAND_PATTERN.sub(" ", body)):
            return body
        return " "

    @staticmethod
    def is_bracketed(tag) -> bool:
        # A condition such as `[ n != 1 ].` stays inline on the line under its
        # formula, where the brackets can fold it back into that formula.
        content = tag.get_text().strip().rstrip(".,;").rstrip()
        if content.startswith("[") and content.endswith("]"):
            return True
        before, after = tag.previous_sibling, tag.next_sibling
        if not isinstance(before, str) or not isinstance(after, str):
            return False
        opener, closer = before.rstrip()[-1:], after.lstrip()[:1]
        return (opener, closer) in BRACKET_PAIRS

    def get_latex_batched(
        self,
        page_images: list[Image.Image],
        bboxes: list[list[list[float]]],
    ):
        self.recognition_model.disable_tqdm = self.disable_tqdm
        predictions: list[OCRResult] = self.recognition_model(
            images=page_images,
            bboxes=bboxes,
            task_names=["ocr_with_boxes"] * len(page_images),
            recognition_batch_size=self.get_batch_size(),
            sort_lines=False,
            drop_repeated_text=self.drop_repeated_text,
            max_tokens=2048,
            max_sliding_window=2148,
        )

        equation_predictions = [
            [line.text.strip() for line in page_prediction.text_lines]
            for page_prediction in predictions
        ]

        return equation_predictions
