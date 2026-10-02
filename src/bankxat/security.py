"""Shaxsiy va moliyaviy qiymatlarni log uchun maskalash."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

CARD_PATTERN = re.compile(r"(?<!\d)(\d{4})[\s.-]?(\d{4})[\s.-]?(\d{4})[\s.-]?(\d{4})(?!\d)")
PINFL_PATTERN = re.compile(r"(?<!\d)(\d{10})(\d{4})(?!\d)")


def mask_card(value: str) -> str:
    """Karta raqamining faqat bosh va oxirgi to'rtligini qoldiradi."""

    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 16:
        return "[MASKED_CARD]"
    return f"{digits[:4]} **** **** {digits[-4:]}"


def mask_pinfl(value: str) -> str:
    """PINFL qiymatining faqat oxirgi to'rtligini qoldiradi."""

    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 14:
        return "[MASKED_PINFL]"
    return f"**********{digits[-4:]}"


def redact_text(text: str) -> str:
    """Erkin matndagi karta va PINFLga o'xshash qiymatlarni yashiradi."""

    redacted = CARD_PATTERN.sub(lambda match: mask_card(match.group(0)), text)
    return PINFL_PATTERN.sub(lambda match: mask_pinfl(match.group(0)), redacted)


def redact_identity_numbers(text: str) -> str:
    """UI dalilida kartani qoldirib, 14 xonali shaxsiy identifikatorlarni yashiradi."""

    return PINFL_PATTERN.sub(lambda match: mask_pinfl(match.group(0)), text)


def redact_value(value: Any) -> Any:
    """Ichma-ich log obyektlaridagi sezgir qiymatlarni rekursiv maskalaydi."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    return value
