"""Minimal reader for the EIOPA term-structure workbook inside its ZIP release."""

import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

SPOT_SHEET = "RFR_spot_no_VA"
TERM_STRUCTURE_FILE = re.compile(r"EIOPA_RFR_\d{8}_Term_Structures\.xlsx$")
COLUMN_LETTERS = re.compile(r"[A-Z]+")
SERIES_DATE = re.compile(r"_(\d{2})_(\d{2})_(\d{4})_")

PARAMETER_ROWS = ("LLP", "UFR", "CRA")


class WorkbookError(Exception):
    pass


def _sheet_part(book):
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    targets = {
        rel.get("Id"): rel.get("Target")
        for rel in ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    }
    for sheet in workbook.iter(MAIN + "sheet"):
        if sheet.get("name") == SPOT_SHEET:
            target = targets[sheet.get(RELS + "id")].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise WorkbookError(f"the workbook has no {SPOT_SHEET} sheet")


def _shared_strings(book):
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(MAIN + "t"))
        for item in root.iter(MAIN + "si")
    ]


def _grid(book):
    strings = _shared_strings(book)
    sheet = ET.fromstring(book.read(_sheet_part(book)))
    rows = {}
    for row in sheet.iter(MAIN + "row"):
        cells = {}
        for cell in row.iter(MAIN + "c"):
            value = cell.find(MAIN + "v")
            if value is None:
                continue
            text = strings[int(value.text)] if cell.get("t") == "s" else value.text
            cells[COLUMN_LETTERS.match(cell.get("r")).group()] = text
        if cells:
            rows[int(row.get("r"))] = cells
    return rows


def _rounded(value):
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")).normalize())


def _series_date(code):
    match = SERIES_DATE.search(code)
    if match is None:
        raise WorkbookError(f"series code {code} carries no reference date")
    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def read_term_structure(archive_bytes, country, tenor_years):
    """Rates are returned as percent; the workbook publishes decimal fractions."""
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
        name = next(
            (n for n in bundle.namelist() if TERM_STRUCTURE_FILE.search(n)), None
        )
        if name is None:
            raise WorkbookError("the release holds no term-structure workbook")
        with zipfile.ZipFile(io.BytesIO(bundle.read(name))) as book:
            rows = _grid(book)

    # locate the country's column from the header band, then its parameters and rates
    header_row = next(
        (number for number, cells in rows.items() if country in cells.values()), None
    )
    if header_row is None:
        raise WorkbookError(f"the workbook has no column for {country}")
    column = next(key for key, value in rows[header_row].items() if value == country)
    code = rows[header_row + 1][column]

    parameters = {}
    for cells in rows.values():
        label, value = cells.get("B"), cells.get(column)
        if label in PARAMETER_ROWS and value is not None and label not in parameters:
            parameters[label] = value

    rates = {}
    for cells in rows.values():
        label, value = cells.get("B"), cells.get(column)
        if label is None or value is None:
            continue
        try:
            maturity = int(Decimal(label))
        except (ArithmeticError, ValueError):
            continue
        if maturity in tenor_years:
            rates[maturity] = Decimal(value) * 100

    missing = [tenor for tenor in tenor_years if tenor not in rates]
    if missing:
        raise WorkbookError(f"{country} is missing maturities {missing}")

    return {
        "series_code": code,
        "as_of_date": _series_date(code),
        "last_liquid_point": int(Decimal(parameters["LLP"])) if parameters.get("LLP") else None,
        "ultimate_forward_rate": _rounded(parameters.get("UFR")),
        "credit_risk_adjustment": _rounded(parameters.get("CRA")),
        "rates": rates,
    }
