import torch

from raw2md_engine.surya.common.load import ModelLoader, restore_buffers
from raw2md_engine.surya.logging import get_logger
from raw2md_engine.surya.settings import settings
from raw2md_engine.surya.table_rec.model.config import (
    DonutSwinTableRecConfig,
    SuryaTableRecConfig,
    SuryaTableRecDecoderConfig,
)
from raw2md_engine.surya.table_rec.model.encoderdecoder import (
    TableRecEncoderDecoderModel,
)
from raw2md_engine.surya.table_rec.processor import SuryaTableRecProcessor

logger = get_logger()


class TableRecModelLoader(ModelLoader):
    def __init__(self, checkpoint: str | None = None):
        super().__init__(checkpoint)

        if self.checkpoint is None:
            self.checkpoint = settings.TABLE_REC_MODEL_CHECKPOINT

    def model(
        self,
        device=settings.TORCH_DEVICE_MODEL,
        dtype=settings.MODEL_DTYPE,
        attention_implementation: str | None = None,
    ) -> TableRecEncoderDecoderModel:
        if device is None:
            device = settings.TORCH_DEVICE_MODEL
        if dtype is None:
            dtype = settings.MODEL_DTYPE

        if device == "mps":
            logger.warning(
                "`TableRecEncoderDecoderModel` is not compatible with mps backend. Defaulting to cpu instead"
            )
            device = "cpu"
            dtype = "float32"

        config = SuryaTableRecConfig.from_pretrained(self.checkpoint)
        decoder_config = config.decoder
        decoder = SuryaTableRecDecoderConfig(**decoder_config)
        config.decoder = decoder

        encoder_config = config.encoder
        encoder = DonutSwinTableRecConfig(**encoder_config)
        config.encoder = encoder

        model = TableRecEncoderDecoderModel.from_pretrained(
            self.checkpoint, config=config, dtype=dtype
        )

        model = restore_buffers(model).to(device)
        model = model.eval()

        if settings.COMPILE_ALL or settings.COMPILE_TABLE_REC:
            torch.set_float32_matmul_precision("high")
            torch._dynamo.config.cache_size_limit = 16
            torch._dynamo.config.suppress_errors = False

            logger.info(
                f"Compiling table recognition model {self.checkpoint} on device {device} with dtype {dtype}"
            )
            compile_args = {"backend": "openxla"} if device == "xla" else {}
            model.encoder = torch.compile(model.encoder, **compile_args)
            model.decoder = torch.compile(model.decoder, **compile_args)

        logger.debug(
            f"Loaded table recognition model {self.checkpoint} from {TableRecEncoderDecoderModel.get_local_path(self.checkpoint)} onto device {device} with dtype {dtype}"
        )
        return model

    def processor(
        self, device=settings.TORCH_DEVICE_MODEL, dtype=settings.MODEL_DTYPE
    ) -> SuryaTableRecProcessor:
        processor = SuryaTableRecProcessor(self.checkpoint)

        processor.token_pad_id = 0
        processor.token_eos_id = 1
        processor.token_bos_id = 1
        processor.token_query_end_id = 4
        return processor
