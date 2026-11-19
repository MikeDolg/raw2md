"""The pattern that matches the records of a vocabulary section as words."""

from raw2md.mdtext.words import word_pattern


def test_a_word_matches_only_the_whole_word() -> None:
    pattern = word_pattern(("chart",))
    assert pattern.search("Chart 4") is not None
    assert pattern.search("a charter party") is None


def test_a_stem_matches_the_endings_of_its_own_word() -> None:
    pattern = word_pattern(("таблиц*",))
    assert pattern.search("Таблица 5") is not None
    assert pattern.search("в таблицах выше") is not None
    assert pattern.search("сводная") is None
    # The stem is open at its end only.
    assert pattern.search("подтаблица") is None


def test_a_shortened_form_keeps_its_dot() -> None:
    pattern = word_pattern(("рис.",))
    assert pattern.search("Рис. 12") is not None
    assert pattern.search("риск") is None


def test_a_record_of_several_words_matches_whatever_space_wraps_them() -> None:
    pattern = word_pattern(("table of contents",))
    assert pattern.fullmatch("Table of Contents") is not None
    assert pattern.fullmatch("table  of\tcontents") is not None


def test_a_stem_guard_states_what_must_not_follow_the_stem() -> None:
    # A stem running into a lowercase word is an ordinary title; a capital
    # after it is a section designator.
    pattern = word_pattern(("appendix*",), stem_guard=r"(?![ \t]*[a-z])")
    assert pattern.match("Appendix B") is not None
    assert pattern.match("Appendixes") is not None
    assert pattern.match("Appendix materials") is None


def test_a_guard_leaves_a_word_required_in_full_alone() -> None:
    pattern = word_pattern(("references",), stem_guard=r"(?![ \t]*[a-z])")
    assert pattern.match("References and Notes") is not None


def test_an_emptied_section_matches_nothing() -> None:
    pattern = word_pattern(())
    assert pattern.search("contents") is None
    assert pattern.search("") is None


def test_a_record_is_matched_literally() -> None:
    # A record is a word, so regex metacharacters stand for themselves.
    pattern = word_pattern(("c++",))
    assert pattern.search("C++ manual") is not None
    assert pattern.search("cxx manual") is None
