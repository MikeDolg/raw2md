import os

from raw2md_engine.marker.schema.document import Document

os.environ["TOKENIZERS_PARALLELISM"] = "false"  # disables a tokenizers warning

from collections import defaultdict
from typing import Annotated, Any, Dict, List, Optional, Type, Tuple, Union
import io
from contextlib import contextmanager
import tempfile

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.services import BaseService
from raw2md_engine.marker.processors.llm.llm_table_merge import LLMTableMergeProcessor
from raw2md_engine.marker.providers.registry import provider_from_filepath
from raw2md_engine.marker.builders.document import DocumentBuilder
from raw2md_engine.marker.builders.layout import LayoutBuilder
from raw2md_engine.marker.builders.line import LineBuilder
from raw2md_engine.marker.builders.ocr import OcrBuilder
from raw2md_engine.marker.builders.structure import StructureBuilder
from raw2md_engine.marker.converters import BaseConverter
from raw2md_engine.marker.processors.blockquote import BlockquoteProcessor
from raw2md_engine.marker.processors.code import CodeProcessor
from raw2md_engine.marker.processors.debug import DebugProcessor
from raw2md_engine.marker.processors.document_toc import DocumentTOCProcessor
from raw2md_engine.marker.processors.equation import EquationProcessor
from raw2md_engine.marker.processors.footnote import FootnoteProcessor
from raw2md_engine.marker.processors.ignoretext import IgnoreTextProcessor
from raw2md_engine.marker.processors.line_numbers import LineNumbersProcessor
from raw2md_engine.marker.processors.list import ListProcessor
from raw2md_engine.marker.processors.llm.llm_complex import LLMComplexRegionProcessor
from raw2md_engine.marker.processors.llm.llm_form import LLMFormProcessor
from raw2md_engine.marker.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from raw2md_engine.marker.processors.llm.llm_table import LLMTableProcessor
from raw2md_engine.marker.processors.page_header import PageHeaderProcessor
from raw2md_engine.marker.processors.reference import ReferenceProcessor
from raw2md_engine.marker.processors.sectionheader import SectionHeaderProcessor
from raw2md_engine.marker.processors.table import TableProcessor
from raw2md_engine.marker.processors.text import TextProcessor
from raw2md_engine.marker.processors.block_relabel import BlockRelabelProcessor
from raw2md_engine.marker.processors.blank_page import BlankPageProcessor
from raw2md_engine.marker.processors.llm.llm_equation import LLMEquationProcessor
from raw2md_engine.marker.renderers.markdown import MarkdownRenderer
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block
from raw2md_engine.marker.schema.registry import register_block_class
from raw2md_engine.marker.util import strings_to_classes
from raw2md_engine.marker.processors.llm.llm_handwriting import LLMHandwritingProcessor
from raw2md_engine.marker.processors.order import OrderProcessor
from raw2md_engine.marker.services.gemini import GoogleGeminiService
from raw2md_engine.marker.processors.line_merge import LineMergeProcessor
from raw2md_engine.marker.processors.llm.llm_mathblock import LLMMathBlockProcessor
from raw2md_engine.marker.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from raw2md_engine.marker.processors.llm.llm_sectionheader import LLMSectionHeaderProcessor


class PdfConverter(BaseConverter):
    """
    A converter for processing and rendering PDF files into Markdown, JSON, HTML and other formats.
    """

    override_map: Annotated[
        Dict[BlockTypes, Type[Block]],
        "A mapping to override the default block classes for specific block types.",
        "The keys are `BlockTypes` enum values, representing the types of blocks,",
        "and the values are corresponding `Block` class implementations to use",
        "instead of the defaults.",
    ] = defaultdict()
    use_llm: Annotated[
        bool,
        "Enable higher quality processing with LLMs.",
    ] = False
    default_processors: Tuple[BaseProcessor, ...] = (
        OrderProcessor,
        BlockRelabelProcessor,
        LineMergeProcessor,
        BlockquoteProcessor,
        CodeProcessor,
        DocumentTOCProcessor,
        EquationProcessor,
        FootnoteProcessor,
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        SectionHeaderProcessor,
        TableProcessor,
        LLMTableProcessor,
        LLMTableMergeProcessor,
        LLMFormProcessor,
        TextProcessor,
        LLMComplexRegionProcessor,
        LLMImageDescriptionProcessor,
        LLMEquationProcessor,
        LLMHandwritingProcessor,
        LLMMathBlockProcessor,
        LLMSectionHeaderProcessor,
        LLMPageCorrectionProcessor,
        ReferenceProcessor,
        BlankPageProcessor,
        DebugProcessor,
    )
    default_llm_service: BaseService = GoogleGeminiService

    def __init__(
        self,
        artifact_dict: Dict[str, Any],
        processor_list: Optional[List[str]] = None,
        renderer: str | None = None,
        llm_service: str | None = None,
        config=None,
    ):
        super().__init__(config)

        if config is None:
            config = {}

        for block_type, override_block_type in self.override_map.items():
            register_block_class(block_type, override_block_type)

        if processor_list is not None:
            processor_list = strings_to_classes(processor_list)
        else:
            processor_list = self.default_processors

        if renderer:
            renderer = strings_to_classes([renderer])[0]
        else:
            renderer = MarkdownRenderer

        # Put here so that resolve_dependencies can access it
        self.artifact_dict = artifact_dict

        if llm_service:
            llm_service_cls = strings_to_classes([llm_service])[0]
            llm_service = self.resolve_dependencies(llm_service_cls)
        elif config.get("use_llm", False):
            llm_service = self.resolve_dependencies(self.default_llm_service)

        # Inject llm service into artifact_dict so it can be picked up by processors, etc.
        self.artifact_dict["llm_service"] = llm_service
        self.llm_service = llm_service

        self.renderer = renderer

        processor_list = self.initialize_processors(processor_list)
        self.processor_list = processor_list

        self.layout_builder_class = LayoutBuilder
        self.page_count = None  # Track how many pages were converted

    @contextmanager
    def filepath_to_str(self, file_input: Union[str, io.BytesIO]):
        temp_file = None
        try:
            if isinstance(file_input, str):
                yield file_input
            else:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    if isinstance(file_input, io.BytesIO):
                        file_input.seek(0)
                        temp_file.write(file_input.getvalue())
                    else:
                        raise TypeError(
                            f"Expected str or BytesIO, got {type(file_input)}"
                        )

                yield temp_file.name
        finally:
            if temp_file is not None and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def build_document(self, filepath: str) -> Document:
        provider_cls = provider_from_filepath(filepath)
        layout_builder = self.resolve_dependencies(self.layout_builder_class)
        line_builder = self.resolve_dependencies(LineBuilder)
        ocr_builder = self.resolve_dependencies(OcrBuilder)
        provider = provider_cls(filepath, self.config)
        document = DocumentBuilder(self.config)(
            provider, layout_builder, line_builder, ocr_builder
        )
        structure_builder_cls = self.resolve_dependencies(StructureBuilder)
        structure_builder_cls(document)

        for processor in self.processor_list:
            processor(document)

        return document

    def __call__(self, filepath: str | io.BytesIO):
        with self.filepath_to_str(filepath) as temp_path:
            document = self.build_document(temp_path)
            self.page_count = len(document.pages)
            renderer = self.resolve_dependencies(self.renderer)
            rendered = renderer(document)
        return rendered
