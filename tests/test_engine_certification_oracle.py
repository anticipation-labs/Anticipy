from proof.engine_certification.brain_runner import _contains


def test_number_words_and_browser_native_digits_are_equivalent():
    assert _contains("Renew the license for one year", "1 year")
    assert _contains("Book a table for six", "6")


def test_semantic_comparator_does_not_accept_a_different_number():
    assert not _contains("Renew the license for two years", "1 year")
