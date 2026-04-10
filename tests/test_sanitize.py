from clawed.sanitize import sanitize_text


def test_strips_cjk_mid_sentence():
    result = sanitize_text("Black men after the Civil War?\u77ed\u6682\u83b7\u5f97\u6743\u5229 but then taken away")
    assert "\u77ed" not in result
    assert "Civil War" in result
    assert "taken away" in result


def test_preserves_clean_english():
    text = "The 19th Amendment was ratified in 1920."
    assert sanitize_text(text) == text


def test_no_double_spaces():
    result = sanitize_text("Hello \u4f60\u597d world")
    assert "  " not in result
