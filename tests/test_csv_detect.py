"""CSV detection: encoding and delimiter."""
from __future__ import annotations

from app.services import csv_detect


def test_utf8_no_bom() -> None:
    raw = "a,b,c\n1,2,3\n".encode("utf-8")
    det = csv_detect.detect(raw)
    assert det.encoding.startswith("utf-8")
    assert det.delimiter == ","
    assert det.text.startswith("a,b,c")


def test_utf8_bom() -> None:
    raw = "\ufeffa,b,c\n1,2,3\n".encode("utf-8")
    det = csv_detect.detect(raw)
    assert not det.text.startswith("\ufeff")
    assert det.delimiter == ","


def test_semicolon_delimiter() -> None:
    raw = "a;b;c\n1;2;3\n".encode("utf-8")
    det = csv_detect.detect(raw)
    assert det.delimiter == ";"
    rows = csv_detect.all_rows(det.text, det.delimiter)
    assert rows[1] == ["1", "2", "3"]


def test_tab_delimiter() -> None:
    raw = "a\tb\tc\n1\t2\t3\n".encode("utf-8")
    det = csv_detect.detect(raw)
    assert det.delimiter == "\t"


def test_quoted_commas() -> None:
    raw = 'a,b\n"1, 2",3\n'.encode("utf-8")
    det = csv_detect.detect(raw)
    rows = csv_detect.all_rows(det.text, det.delimiter)
    assert rows[1] == ["1, 2", "3"]
