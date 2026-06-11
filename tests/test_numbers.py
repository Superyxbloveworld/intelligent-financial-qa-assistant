from docqa.numbers import amounts_close, format_financial_number, parse_financial_number


def test_parse_positive_and_negative_financial_numbers():
    assert parse_financial_number("1,234.56") == (1234.56, [])
    assert parse_financial_number("(1,234.56)") == (-1234.56, [])
    assert parse_financial_number("-") == (None, [])


def test_invalid_ocr_number_is_not_silently_repaired():
    value, warnings = parse_financial_number("26,075,352.，739.73")
    assert value is None
    assert warnings == ["invalid_numeric_format"]


def test_format_and_tolerance():
    assert format_financial_number(-1234.5) == "(1,234.50)"
    assert amounts_close(100.0, 100.01)
    assert not amounts_close(100.0, 100.1)
