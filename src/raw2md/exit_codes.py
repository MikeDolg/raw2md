"""Process exit codes.

The orchestrator aggregates per-file outcomes into one of these codes; the CLI
front-end returns 2 for argument errors before any file is processed.
"""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    PARTIAL_BATCH_ERROR = 1
    ARGUMENT_ERROR = 2
    MISSING_DEPENDENCY = 3
    CONVERSION_ERROR = 4
    LLM_ERROR = 5
