"""Karta raqamini xavfsiz tekshirish."""

from __future__ import annotations

import re

MASK_CHARACTERS = frozenset("*xX•●#")


def normalize_card(value: str) -> str:
    """Karta yozuvidan ruxsat etilgan ajratgichlarni olib tashlaydi."""

    return re.sub(r"[\s.\-]", "", value)


def is_masked_card(value: str) -> bool:
    """Qiymatda karta maskasi belgisi borligini tekshiradi."""

    return any(character in MASK_CHARACTERS for character in value)


def passes_luhn(value: str) -> bool:
    """16 xonali karta raqamini Luhn algoritmi bilan tekshiradi."""

    normalized = normalize_card(value)
    if (
        len(normalized) != 16
        or not normalized.isascii()
        or not normalized.isdigit()
        or is_masked_card(value)
    ):
        return False

    total = 0
    parity = len(normalized) % 2
    for index, character in enumerate(normalized):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
