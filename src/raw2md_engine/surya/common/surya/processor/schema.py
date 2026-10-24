from typing import Literal, TypedDict

import torch
from PIL import Image


class TaskDict(TypedDict):
    datasets: list[str]
    img_size: tuple[int, int]


class TasksDict(TypedDict):
    ocr_with_boxes: TaskDict
    ocr_without_boxes: TaskDict
    block_without_boxes: TaskDict


class ProcessorInput(TypedDict):
    type: Literal["image", "ocr", "text", "empty_output"]


class ImageInput(ProcessorInput):
    type: Literal["image"]
    image: Image.Image
    rotated: bool


class TextInput(ProcessorInput):
    type: Literal["text"]
    text: str
    math: bool


class ProcessorOutput(TypedDict):
    input_ids: list[int]
    image_tiles: torch.Tensor | None
    grid_thw: torch.Tensor | None
