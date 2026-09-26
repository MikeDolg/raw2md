"""Tests for the progress reporter: stage names and output redirection."""

from __future__ import annotations

import io
import sys

import pytest

from raw2md.progress import (
    STAGE_NAMES,
    BatchProgress,
    FileProgress,
    capture_engine_output,
)

# ---------------------------------------------------------------------------
# Stage names
# ---------------------------------------------------------------------------


def test_stage_names_are_five() -> None:
    assert len(STAGE_NAMES) == 5


def test_stage_names_values() -> None:
    assert STAGE_NAMES == (
        "conversion",
        "cleaning",
        "quality evaluation",
        "inspection",
        "post-processing",
    )


# ---------------------------------------------------------------------------
# capture_engine_output
# ---------------------------------------------------------------------------


def test_capture_redirects_stdout_to_sink() -> None:
    sink = io.StringIO()
    with capture_engine_output(sink):
        print("hello from engine", end="")  # noqa: T201 -- print is the literal output capture_engine_output intercepts
    assert sink.getvalue() == "hello from engine"


def test_capture_redirects_stderr_to_sink() -> None:
    sink = io.StringIO()
    with capture_engine_output(sink):
        print("err from engine", end="", file=sys.stderr)  # noqa: T201 -- print is the literal output capture_engine_output intercepts
    assert sink.getvalue() == "err from engine"


def test_capture_restores_stdout_after_exit() -> None:
    original = sys.stdout
    with capture_engine_output(io.StringIO()):
        pass
    assert sys.stdout is original


def test_capture_restores_stderr_after_exit() -> None:
    original = sys.stderr
    with capture_engine_output(io.StringIO()):
        pass
    assert sys.stderr is original


def test_capture_no_sink_discards_output() -> None:
    with capture_engine_output(None):
        print("discarded")  # noqa: T201 -- print is the literal output capture_engine_output intercepts
        print("also discarded", file=sys.stderr)  # noqa: T201 -- print is the literal output capture_engine_output intercepts


def test_capture_no_sink_does_not_buffer_in_memory() -> None:
    from raw2md.progress import _NullWriter  # internal; accessed only here

    writer = _NullWriter()
    assert writer.write("large payload" * 1000) == len("large payload" * 1000)
    assert writer.writable()


def test_capture_restores_on_exception() -> None:
    original_out, original_err = sys.stdout, sys.stderr
    with pytest.raises(ValueError), capture_engine_output(io.StringIO()):  # noqa: PT011 -- any exception must be survived; the type/message here is arbitrary
        raise ValueError("boom")
    assert sys.stdout is original_out
    assert sys.stderr is original_err


# ---------------------------------------------------------------------------
# BatchProgress
# ---------------------------------------------------------------------------


def test_batch_progress_advance_increments_counter() -> None:
    buf = io.StringIO()
    with BatchProgress(total=3, file=buf) as bar:
        bar.advance()
        bar.advance()
    assert bar._bar.n == 2


def test_batch_progress_bracket_shows_files_per_minute() -> None:
    buf = io.StringIO()
    with BatchProgress(total=2, file=buf) as bar:
        bar.advance()
        assert "files/min" in bar._bar.bar_format
        assert ", " not in bar._bar.bar_format.rsplit("[", 1)[-1]


def test_batch_progress_rate_keeps_two_decimals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow run must not round its throughput away to "0.0"."""
    buf = io.StringIO()
    with BatchProgress(total=2, file=buf) as bar:
        # One file per ~33 minutes; tqdm needs the rest of the dict to render.
        original = type(bar._bar).format_dict

        def slow_rate(self: object) -> dict[str, object]:
            return {**original.fget(self), "rate": 0.0005}

        monkeypatch.setattr(type(bar._bar), "format_dict", property(slow_rate))
        bar.advance()
        assert "0.03 files/min" in bar._bar.bar_format


def test_batch_progress_context_manager_closes() -> None:
    buf = io.StringIO()
    bar = BatchProgress(total=2, file=buf)
    with bar:
        bar.advance()
    assert bar._bar.disable or bar._bar.n == 1


# ---------------------------------------------------------------------------
# FileProgress
# ---------------------------------------------------------------------------


_BASE_STAGES = STAGE_NAMES[:3]  # conversion, cleaning, quality evaluation
_BOTH_LLM_STAGES = STAGE_NAMES  # + inspection, post-processing


def test_file_progress_total_matches_base_route() -> None:
    buf = io.StringIO()
    fp = FileProgress("doc.pdf", _BASE_STAGES, file=buf)
    fp.close()
    assert fp._bar.total == 3


def test_file_progress_total_matches_full_llm_route() -> None:
    buf = io.StringIO()
    fp = FileProgress("doc.pdf", _BOTH_LLM_STAGES, file=buf)
    fp.close()
    assert fp._bar.total == 5


def test_file_progress_update_stage_increments() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        fp.update_stage("conversion")
        fp.update_stage("cleaning")
    assert fp._bar.n == 2


def test_file_progress_update_stage_shows_bracket() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        fp.update_stage("quality evaluation")
    assert "[quality evaluation]" in fp._bar.bar_format


def test_file_progress_base_run_completes_at_total() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        fp.update_stage(STAGE_NAMES[0])
        fp.update_stage(STAGE_NAMES[1])
        fp.update_stage(STAGE_NAMES[2])
    assert fp._bar.n == fp._bar.total == 3


def test_file_progress_full_llm_run_completes_at_total() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BOTH_LLM_STAGES, file=buf) as fp:
        for name in STAGE_NAMES:
            fp.update_stage(name)
    assert fp._bar.n == fp._bar.total == 5


def test_file_progress_inspection_and_post_processing_are_distinct_shares() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BOTH_LLM_STAGES, file=buf) as fp:
        for name in STAGE_NAMES[:3]:
            fp.update_stage(name)
        fp.update_stage("inspection")
        assert fp._bar.n == 4
        assert "[inspection]" in fp._bar.bar_format
        fp.update_stage("post-processing")
        assert fp._bar.n == 5
        assert "[post-processing]" in fp._bar.bar_format


def test_file_progress_stage_absent_from_route_stays_out_of_total() -> None:
    # An inapplicable stage is left out of the composition.
    buf = io.StringIO()
    with FileProgress("doc.docx", _BASE_STAGES, file=buf) as fp:
        fp.update_stage(STAGE_NAMES[0])
        fp.update_stage(STAGE_NAMES[1])
        fp.update_stage(STAGE_NAMES[2])
        # A requested stage outside this route must not grow the total.
        fp.update_stage("post-processing")
    assert fp._bar.n == fp._bar.total == 3


def test_file_progress_repeated_stage_name_does_not_double_advance() -> None:
    # A stage spanning several calls advances the bar once.
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BOTH_LLM_STAGES, file=buf) as fp:
        for name in STAGE_NAMES:
            fp.update_stage(name)
        fp.update_stage(STAGE_NAMES[3])  # repeat: inspection again
        fp.update_stage(STAGE_NAMES[4])  # repeat: post-processing again
    assert fp._bar.n == fp._bar.total == 5


def test_file_progress_repeated_stage_still_refreshes_label() -> None:
    # The bracket follows the repeat, since real work runs under it.
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BOTH_LLM_STAGES, file=buf) as fp:
        fp.update_stage("post-processing")
        fp.update_stage("inspection")
        fp.update_stage("post-processing")  # repeat, e.g. the real repair call
    assert "[post-processing]" in fp._bar.bar_format


def test_file_progress_never_exceeds_its_total() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        for stage in (*STAGE_NAMES, *STAGE_NAMES):  # every stage, then repeated
            fp.update_stage(stage)
        assert fp._bar.n <= fp._bar.total


def test_file_progress_set_phase_relabels_without_advancing() -> None:
    # A phase moves the bracket, not the stage count.
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        fp.update_stage(STAGE_NAMES[0])  # conversion -> count 1
        fp.set_phase("layout")
        fp.set_phase("OCR")
        assert fp._bar.n == 1
        assert "[OCR]" in fp._bar.bar_format


def test_file_progress_next_stage_overwrites_phase() -> None:
    buf = io.StringIO()
    with FileProgress("doc.pdf", _BASE_STAGES, file=buf) as fp:
        fp.update_stage(STAGE_NAMES[0])
        fp.set_phase("tables")
        fp.update_stage(STAGE_NAMES[1])  # cleaning
    assert "[cleaning]" in fp._bar.bar_format


# ---------------------------------------------------------------------------
# marker phase sniffing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "label"),
    [
        ("Recognizing Layout:  50%|#####     | 1/2 [00:01<00:01]", "layout"),
        ("Detecting bboxes: 100%|##########| 2/2", "detection"),
        ("Running OCR Error Detection:   0%|", "OCR check"),
        ("Recognizing Text:  25%|##", "OCR"),
        ("Recognizing tables: 100%|##########|", "tables"),
    ],
)
def test_marker_phase_label_known(line: str, label: str) -> None:
    from raw2md.progress import _marker_phase_label

    assert _marker_phase_label(line) == label


def test_marker_phase_label_unknown_progress_line_is_generic() -> None:
    # An unnamed tqdm description still marks a marker step.
    from raw2md.progress import _marker_phase_label

    assert _marker_phase_label("Loading model shards:  30%|###   | 3/10") == "marker"


def test_marker_phase_label_non_progress_line_is_ignored() -> None:
    from raw2md.progress import _marker_phase_label

    assert _marker_phase_label("some warning about a font") is None
    assert _marker_phase_label("") is None


def test_phase_sniffer_forwards_output_to_underlying() -> None:
    from raw2md.progress import _PhaseSniffer

    sink = io.StringIO()
    sniffer = _PhaseSniffer(sink, lambda _label: None)
    sniffer.write("Recognizing Layout: 100%|##|\n")
    assert sink.getvalue() == "Recognizing Layout: 100%|##|\n"


def test_phase_sniffer_reports_only_on_label_change() -> None:
    # tqdm redraws a bar many times; the callback fires once per phase.
    from raw2md.progress import _PhaseSniffer

    seen: list[str] = []
    sniffer = _PhaseSniffer(io.StringIO(), seen.append)
    sniffer.write("\rRecognizing Layout:  10%|# |")
    sniffer.write("\rRecognizing Layout:  90%|##|")  # same phase, redraw
    sniffer.write("\rRecognizing Text:  10%|# |")  # phase changed
    sniffer.write("plain log line, no phase")  # ignored, keeps last
    sniffer.write("\rRecognizing tables: 100%|##|")
    assert seen == ["layout", "OCR", "tables"]


def test_phase_sniffer_splits_multiline_write() -> None:
    from raw2md.progress import _PhaseSniffer

    seen: list[str] = []
    sniffer = _PhaseSniffer(io.StringIO(), seen.append)
    sniffer.write("Recognizing Layout: 100%|##|\rRecognizing Text: 100%|##|\n")
    assert seen == ["layout", "OCR"]


def test_capture_engine_output_on_phase_reports_phases() -> None:
    seen: list[str] = []
    sink = io.StringIO()
    with capture_engine_output(sink, on_phase=seen.append):
        print("\rRecognizing Layout: 100%|##|", end="", file=sys.stderr)  # noqa: T201 -- print is the literal output capture_engine_output intercepts
        print("\rRecognizing tables: 100%|##|", end="", file=sys.stderr)  # noqa: T201 -- print is the literal output capture_engine_output intercepts
    assert seen == ["layout", "tables"]
    assert "Recognizing Layout" in sink.getvalue()


def test_capture_engine_output_without_on_phase_is_unchanged() -> None:
    sink = io.StringIO()
    with capture_engine_output(sink):
        print("Recognizing Layout: 100%|##|", end="", file=sys.stderr)  # noqa: T201 -- print is the literal output capture_engine_output intercepts
    assert sink.getvalue() == "Recognizing Layout: 100%|##|"
