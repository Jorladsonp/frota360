from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def attr(obj, name):
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except (AttributeError, TypeError):
        return "—"


@register.filter
def br_currency(value):
    try:
        value = Decimal(value or 0)
        text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {text}"
    except (TypeError, ValueError):
        return "R$ 0,00"


@register.filter
def br_number(value, decimals=1):
    try:
        text = f"{Decimal(value or 0):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return text
    except (TypeError, ValueError):
        return "0"


@register.filter
def br_date(value):
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else value or "—"


@register.filter
def br_datetime(value):
    return value.strftime("%d/%m/%Y %H:%M") if hasattr(value, "strftime") else value or "—"


@register.filter
def status_class(value):
    value = str(value or "").upper()
    if value in ("FINISHED", "DONE", "APPROVED", "PAID", "ACTIVE", "OPERATING", "CONFERRED"):
        return "success"
    if value in ("IN_PROGRESS", "OPEN", "REVIEW", "PLANNED", "REOPENED", "MAINTENANCE"):
        return "warning"
    if value in ("CANCELLED", "INACTIVE", "CLOSED"):
        return "secondary"
    return "info"
