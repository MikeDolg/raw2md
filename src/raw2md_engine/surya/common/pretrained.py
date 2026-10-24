from torch import Tensor
from transformers import PreTrainedModel
from transformers.utils import is_flash_attn_2_available


class SuryaPreTrainedModel(PreTrainedModel):
    # No-op if we pass attention, so we can set attention however we want in the config
    def _check_and_adjust_attn_implementation(
        self, attn_implementation: str | None, **kwargs
    ):
        if attn_implementation is None:
            try:
                self._sdpa_can_dispatch(True)
                attn_implementation = "sdpa"
            except (ValueError, ImportError):
                attn_implementation = "eager"

            if self._supports_flash_attn and is_flash_attn_2_available():
                attn_implementation = "flash_attention_2"

        return attn_implementation

    # transformers 5 removed these two methods; the encoders still call them.
    def get_head_mask(
        self,
        head_mask: Tensor | None,
        num_hidden_layers: int,
        is_attention_chunked: bool = False,
    ) -> Tensor:
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked is True:
                head_mask = head_mask.unsqueeze(-1)
        else:
            head_mask = [None] * num_hidden_layers

        return head_mask

    def _convert_head_mask_to_5d(self, head_mask, num_hidden_layers):
        """-> [num_hidden_layers x batch x num_heads x seq_length x seq_length]"""
        if head_mask.dim() == 1:
            head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
            head_mask = head_mask.expand(num_hidden_layers, -1, -1, -1, -1)
        elif head_mask.dim() == 2:
            head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
        assert head_mask.dim() == 5, f"head_mask.dim != 5, instead {head_mask.dim()}"
        head_mask = head_mask.to(dtype=self.dtype)
        return head_mask
