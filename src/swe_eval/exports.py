"""Spreadsheet-safe CSV cells; numbers/nulls retain CSV numeric semantics."""
import unicodedata


def csv_cell(value):
    if not isinstance(value, str):
        return value
    # Spreadsheet importers may discard leading whitespace, C0/C1 controls,
    # zero-width formatting characters and BOMs before recognizing formulas.
    index = 0
    while index < len(value) and (value[index].isspace() or unicodedata.category(value[index]).startswith('C')):
        index += 1
    if value[index:index+1] in ('=', '+', '-', '@'):
        return "'" + value
    return value
