from bankxat.validate.pinfl import is_valid_pinfl_format


def test_valid_pinfl_format() -> None:
    assert is_valid_pinfl_format("30101901234567") is True


def test_invalid_pinfl_date() -> None:
    assert is_valid_pinfl_format("33139901234567") is False


def test_invalid_pinfl_prefix() -> None:
    assert is_valid_pinfl_format("70101901234567") is False
