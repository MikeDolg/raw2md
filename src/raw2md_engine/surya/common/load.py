from typing import Optional, Any

import torch

from raw2md_engine.surya.settings import settings


def restore_buffers(model: torch.nn.Module) -> torch.nn.Module:
    """Rebuild on the CPU the buffers that the checkpoint does not hold.

    transformers 5 builds the model on the meta device and leaves such buffers
    uninitialized after the load. Call this before the move to the device.
    """
    for module in model.modules():
        build = getattr(module, "build_buffers", None)
        if build is not None:
            build()
    return model


class ModelLoader:
    def __init__(self, checkpoint: Optional[str] = None):
        self.checkpoint = checkpoint

    def model(
        self,
        device: torch.device | str | None = settings.TORCH_DEVICE_MODEL,
        dtype: Optional[torch.dtype | str] = settings.MODEL_DTYPE,
        attention_implementation: Optional[str] = None,
    ) -> Any:
        raise NotImplementedError()

    def processor(
        self,
        device: torch.device | str | None = settings.TORCH_DEVICE_MODEL,
        dtype: Optional[torch.dtype | str] = settings.MODEL_DTYPE,
    ) -> Any:
        raise NotImplementedError()
