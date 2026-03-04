from decimal import Decimal


def dec_fixed_3(value: Decimal | str | int | float) -> str:
    return f"{Decimal(str(value)):.3f}"


def dec_trimmed(value: Decimal | str | int | float) -> str:
    text = format(Decimal(str(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
