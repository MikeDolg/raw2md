from typing import Tuple, List

from raw2md_engine.marker.builders.document import DocumentBuilder
from raw2md_engine.marker.builders.line import LineBuilder
from raw2md_engine.marker.builders.ocr import OcrBuilder
from raw2md_engine.marker.converters.pdf import PdfConverter
from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.processors.table import TableProcessor
from raw2md_engine.marker.providers.registry import provider_from_filepath
from raw2md_engine.marker.schema import BlockTypes


class TableConverter(PdfConverter):
    default_processors: Tuple[BaseProcessor, ...] = (
        TableProcessor,
    )
    converter_block_types: List[BlockTypes] = (
        BlockTypes.Table,
        BlockTypes.Form,
        BlockTypes.TableOfContents,
    )

    def build_document(self, filepath: str):
        provider_cls = provider_from_filepath(filepath)
        layout_builder = self.resolve_dependencies(self.layout_builder_class)
        line_builder = self.resolve_dependencies(LineBuilder)
        ocr_builder = self.resolve_dependencies(OcrBuilder)
        document_builder = DocumentBuilder(self.config)
        document_builder.disable_ocr = True

        provider = provider_cls(filepath, self.config)
        document = document_builder(provider, layout_builder, line_builder, ocr_builder)

        for page in document.pages:
            page.structure = [
                p for p in page.structure if p.block_type in self.converter_block_types
            ]

        for processor in self.processor_list:
            processor(document)

        return document

    def __call__(self, filepath: str):
        document = self.build_document(filepath)
        self.page_count = len(document.pages)

        renderer = self.resolve_dependencies(self.renderer)
        return renderer(document)
