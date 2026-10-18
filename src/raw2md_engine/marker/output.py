from pydantic import BaseModel

from raw2md_engine.marker.renderers.markdown import MarkdownOutput


def text_from_rendered(rendered: BaseModel):
    if isinstance(rendered, MarkdownOutput):
        return rendered.markdown, "md", rendered.images
    else:
        raise ValueError("Invalid output type")
