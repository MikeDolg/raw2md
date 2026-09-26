"""Run configuration and argument validation.

`RunConfig` is the immutable result of parsing a processing invocation; the CLI
front-end builds it from parsed arguments and validates it before handing it to
the orchestrator. Validation failures are reported as exit code 2.
"""

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Disabled-operation sentinel for the --llm-* flags; absence means the same.
_NONE = "none"

# The --engine value that keeps LLM OCR off.
_MARKER_ENGINE = "marker"


class CliArgumentError(Exception):
    """Invalid argument combination; the CLI maps this to exit code 2."""


@dataclass(frozen=True)
class RunConfig:
    """Resolved parameters of a single processing run.

    The three `llm_*` model fields hold a model key from settings.json or None
    when the operation is disabled. `llm_ocr` reflects `--engine`: None for the
    built-in `marker` route, a model key when `--engine` names one instead.
    `cuda` is True for `--cuda on` (the default). `llm_latex_fix` opens math
    spans to an inspection edit and means nothing without `llm_inspection`
    (`validate_latex_fix`).
    """

    input_path: Path
    output_dir: Path | None
    skip_existing: bool
    yaml_header: bool
    extract_images: bool
    llm_ocr: str | None
    llm_inspection: str | None
    llm_post: str | None
    llm_latex_fix: bool
    cuda: bool
    log_file: bool
    debug: bool


def _model_or_none(value: str) -> str | None:
    return None if value == _NONE else value


def _engine_to_model(value: str) -> str | None:
    """Map --engine to RunConfig.llm_ocr: None for marker, else the model key."""
    return None if value == _MARKER_ENGINE else value


def requests_llm(config: RunConfig) -> bool:
    """True when OCR (via --engine), inspection, or post is enabled."""
    return any(
        model is not None
        for model in (config.llm_ocr, config.llm_inspection, config.llm_post)
    )


def build_config(namespace: argparse.Namespace) -> RunConfig:
    """Map a parsed namespace to a RunConfig without validating it."""
    return RunConfig(
        input_path=namespace.input_path,
        output_dir=namespace.output_dir,
        skip_existing=namespace.skip_existing,
        yaml_header=namespace.yaml_header,
        extract_images=namespace.extract_images,
        llm_ocr=_engine_to_model(namespace.engine),
        llm_inspection=_model_or_none(namespace.llm_inspection),
        llm_post=_model_or_none(namespace.llm_post),
        llm_latex_fix=namespace.llm_latex_fix,
        cuda=namespace.cuda == "on",
        log_file=namespace.log_file,
        debug=namespace.debug,
    )


def validate_latex_fix(config: RunConfig) -> None:
    """Refuse `--llm-latex-fix` without the step it changes.

    The flag only lifts a rule of the inspection edit guard, so without
    inspection it would silently change nothing.
    """
    if config.llm_latex_fix and config.llm_inspection is None:
        raise CliArgumentError("--llm-latex-fix needs --llm-inspection")


def validate_models_allowed(
    config: RunConfig, allowed: Mapping[str, frozenset[str]]
) -> None:
    """Check each requested model against its operation's allowed set.

    `allowed` comes from settings.json; the set of valid model names is not
    hard-coded.
    """
    for operation, model in (
        ("ocr", config.llm_ocr),
        ("inspection", config.llm_inspection),
        ("post", config.llm_post),
    ):
        if model is None:
            continue
        if model not in allowed.get(operation, frozenset()):
            raise CliArgumentError(
                f"model '{model}' is not allowed for operation '{operation}'"
            )
