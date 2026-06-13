"""Lector tabular mínimo (.xlsx / .csv).

Mismo precedente que `planilla_export`: el proyecto no agrega librerías para
Office — el .xlsx se lee como lo que es (zip + XML). Cubre lo que exporta un
aparato biométrico: una hoja simple con encabezados y filas.

Limitación deliberada: .xls binario viejo NO se soporta (no es XML); el mensaje
de error pide re-guardarlo como .xlsx o .csv.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime, timedelta

from defusedxml import ElementTree

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Base de fechas seriales de Excel (sistema 1900, con su bug del 1900-02-29)
_EXCEL_EPOCH = datetime(1899, 12, 30)


class TabularReadError(ValueError):
    """Archivo ilegible o formato no soportado (mensaje apto para el usuario)."""


def excel_serial_to_datetime(value: float) -> datetime:
    """Convierte un serial de Excel (días desde 1899-12-30) a datetime naive."""
    return _EXCEL_EPOCH + timedelta(days=float(value))


def _col_index(cell_ref: str) -> int:
    """'B3' -> 1 (índice de columna 0-based)."""
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(data)
    out: list[str] = []
    for si in root.findall("m:si", _NS):
        # un <si> puede tener <t> directo o runs <r><t>
        text = "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
        out.append(text)
    return out


def _read_xlsx(content: bytes) -> list[list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise TabularReadError(
            "El archivo no es un .xlsx válido. Si el aparato exporta .xls viejo, "
            "abrilo y guardalo como .xlsx o .csv."
        ) from exc

    sheet_names = sorted(n for n in zf.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", n))
    if not sheet_names:
        raise TabularReadError("El .xlsx no contiene hojas legibles.")

    shared = _read_shared_strings(zf)
    root = ElementTree.fromstring(zf.read(sheet_names[0]))

    rows: list[list[str]] = []
    for row_el in root.iter(f"{{{_NS['m']}}}row"):
        cells: dict[int, str] = {}
        for c in row_el.findall("m:c", _NS):
            ref = c.get("r") or ""
            idx = _col_index(ref) if ref else len(cells)
            ctype = c.get("t") or "n"
            value = ""
            if ctype == "inlineStr":
                is_el = c.find("m:is", _NS)
                if is_el is not None:
                    value = "".join(t.text or "" for t in is_el.iter(f"{{{_NS['m']}}}t"))
            else:
                v = c.find("m:v", _NS)
                raw = v.text if v is not None and v.text is not None else ""
                if ctype == "s":
                    try:
                        value = shared[int(raw)]
                    except (ValueError, IndexError):
                        value = raw
                else:
                    value = raw
            cells[idx] = value.strip()
        if not cells:
            continue
        width = max(cells.keys()) + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _read_csv(content: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 nunca falla
        raise TabularReadError("No se pudo decodificar el archivo CSV.")

    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[(cell or "").strip() for cell in row] for row in reader if any((c or "").strip() for c in row)]


def read_tabular_file(file_name: str, content: bytes) -> list[list[str]]:
    """Devuelve las filas (lista de listas de str) de un .xlsx o .csv."""
    name = (file_name or "").lower()
    if name.endswith(".xlsx"):
        return _read_xlsx(content)
    if name.endswith(".csv") or name.endswith(".txt"):
        return _read_csv(content)
    if name.endswith(".xls"):
        raise TabularReadError(
            "El formato .xls (Excel viejo) no se soporta: guardá el archivo como .xlsx o .csv."
        )
    # sin extensión clara: probar xlsx (zip) y caer a csv
    if content[:2] == b"PK":
        return _read_xlsx(content)
    return _read_csv(content)
