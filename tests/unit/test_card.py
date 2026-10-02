from bankxat.security import mask_card, redact_text
from bankxat.validate.card import is_masked_card, passes_luhn


def test_valid_luhn_card() -> None:
    assert passes_luhn("4111 1111 1111 1111") is True


def test_invalid_luhn_card() -> None:
    assert passes_luhn("4111 1111 1111 1112") is False


def test_masked_card_is_never_valid() -> None:
    assert is_masked_card("8600 12** **** 3456") is True
    assert passes_luhn("8600 12** **** 3456") is False


def test_non_ascii_digits_are_not_accepted_as_card_number() -> None:
    assert passes_luhn("٤١١١ ١١١١ ١١١١ ١١١١") is False


def test_log_redaction_masks_card() -> None:
    assert mask_card("4111111111111111") == "4111 **** **** 1111"
    assert "4111111111111111" not in redact_text("karta 4111111111111111")
