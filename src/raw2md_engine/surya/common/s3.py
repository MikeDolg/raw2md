import os

from raw2md_engine.surya.settings import settings


class S3DownloaderMixin:
    # The caller downloads the weights before the models load. A checkpoint
    # `<task>/<date>` lives in `<task>/surya-<date>` under settings.MODEL_DIR.
    s3_prefix = "s3://"

    @classmethod
    def get_local_path(cls, pretrained_model_name_or_path) -> str:
        if not pretrained_model_name_or_path.startswith(cls.s3_prefix):
            return ""
        if settings.MODEL_DIR is None:
            raise RuntimeError("the folder of the engine weights is not set")
        task, date = pretrained_model_name_or_path[len(cls.s3_prefix) :].split("/")
        return os.path.join(settings.MODEL_DIR, task, f"surya-{date}")

    @classmethod
    def from_pretrained(cls, pretrained_model_name_or_path, *args, **kwargs):
        if pretrained_model_name_or_path.startswith(cls.s3_prefix):
            pretrained_model_name_or_path = cls.get_local_path(
                pretrained_model_name_or_path
            )
        return super().from_pretrained(pretrained_model_name_or_path, *args, **kwargs)
