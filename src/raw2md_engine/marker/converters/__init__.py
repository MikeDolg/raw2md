import inspect
from typing import Optional, List, Type

from pydantic import BaseModel

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.util import assign_config, download_font


class BaseConverter:
    def __init__(self, config: Optional[BaseModel | dict] = None):
        assign_config(self, config)
        self.config = config

        # Download render font, needed for some providers
        download_font()

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    def resolve_dependencies(self, cls):
        init_signature = inspect.signature(cls.__init__)
        parameters = init_signature.parameters

        resolved_kwargs = {}
        for param_name, param in parameters.items():
            if param_name == 'self':
                continue
            elif param_name == 'config':
                resolved_kwargs[param_name] = self.config
            elif param.name in self.artifact_dict:
                resolved_kwargs[param_name] = self.artifact_dict[param_name]
            elif param.default != inspect.Parameter.empty:
                resolved_kwargs[param_name] = param.default
            else:
                raise ValueError(f"Cannot resolve dependency for parameter: {param_name}")

        return cls(**resolved_kwargs)

    def initialize_processors(self, processor_cls_lst: List[Type[BaseProcessor]]) -> List[BaseProcessor]:
        return [self.resolve_dependencies(processor_cls) for processor_cls in processor_cls_lst]
