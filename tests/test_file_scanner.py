import sys
import types
from pathlib import Path

import pytest

from SwiftProPDF.security.file_scanner import FileScanError, scan_file


class FakeCleanClient:
    def __init__(self, host: str, port: int, timeout: float):
        self.host = host
        self.port = port
        self.timeout = timeout

    def ping(self):
        return True

    def scan(self, path: str):
        return {path: ("OK", None)}


class FakeInfectedClient(FakeCleanClient):
    def scan(self, path: str):
        return {path: ("FOUND", "Eicar-Test-Signature")}


def install_fake_clamd(monkeypatch, client_class) -> None:
    fake_module = types.SimpleNamespace(ClamdNetworkSocket=client_class)
    monkeypatch.setitem(sys.modules, "clamd", fake_module)


def test_scan_file_noops_when_antivirus_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAMAV_ENABLED", "0")
    monkeypatch.delitem(sys.modules, "clamd", raising=False)
    upload_path = tmp_path / "upload.pdf"
    upload_path.write_bytes(b"not really a pdf")

    scan_file(upload_path)


def test_scan_file_accepts_clean_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAMAV_ENABLED", "1")
    install_fake_clamd(monkeypatch, FakeCleanClient)
    upload_path = tmp_path / "upload.pdf"
    upload_path.write_bytes(b"not really a pdf")

    scan_file(upload_path)


def test_scan_file_rejects_infected_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAMAV_ENABLED", "1")
    install_fake_clamd(monkeypatch, FakeInfectedClient)
    upload_path = tmp_path / "upload.pdf"
    upload_path.write_bytes(b"not really a pdf")

    with pytest.raises(FileScanError, match="Eicar-Test-Signature"):
        scan_file(upload_path)
