"""
Tests for Magika-based content-type checking in ftp_server.py.

Covers:
- _is_content_type_allowed with real scanner file bytes (JPEG, PNG, PDF)
- Rejection of disguised non-image content
- Fail-open behaviour when Magika is unavailable
- _get_magika singleton caching
- ScannerFTPHandler.on_file_received integration (extension + Magika + disk guard)
"""

import os
import sys
import struct
import tempfile
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import agent.ftp_server as ftp_module
from agent.ftp_server import (
    _ALLOWED_EXTENSIONS,
    _ALLOWED_MAGIKA_LABELS,
    _is_content_type_allowed,
    ScannerFTPHandler,
)


# ---------------------------------------------------------------------------
# Minimal valid file bytes for common scanner formats
# ---------------------------------------------------------------------------

def _jpeg_bytes() -> bytes:
    """Minimal valid JPEG (SOI + EOI markers only — enough for Magika)."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 12 + b"\xff\xd9"


def _png_bytes() -> bytes:
    """PNG signature + minimal IHDR + IEND — Magika reads the magic bytes."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"\x00\x00\x00\rIHDR" + b"\x00" * 17  # 13-byte IHDR chunk (simplified)
    iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return sig + ihdr + iend


def _pdf_bytes() -> bytes:
    """Minimal PDF header — Magika uses the %PDF- magic."""
    return b"%PDF-1.4\n%%EOF\n"


def _executable_bytes() -> bytes:
    """ELF magic — a Linux executable disguised as an image."""
    return b"\x7fELF" + b"\x00" * 60


def _text_bytes() -> bytes:
    """Plain text — not a scanner output."""
    return b"Hello, this is plain text content.\n" * 20


# ---------------------------------------------------------------------------
# Helper: write bytes to a temp file with the given extension
# ---------------------------------------------------------------------------

def _tmp_file(content: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Unit tests for _is_content_type_allowed
# ---------------------------------------------------------------------------

class TestIsContentTypeAllowed(unittest.TestCase):

    def setUp(self):
        # Reset the module-level singleton before each test so mocks don't bleed
        ftp_module._magika = None

    def _with_mock_magika(self, label: str):
        """Return a context manager that patches _get_magika to return a mock
        whose identify_path returns the given label."""
        mock_result = MagicMock()
        mock_result.output.label = label
        mock_m = MagicMock()
        mock_m.identify_path.return_value = mock_result
        return patch.object(ftp_module, "_get_magika", return_value=mock_m)

    # -- allowed labels --

    def test_jpeg_label_allowed(self):
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with self._with_mock_magika("jpeg"):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_png_label_allowed(self):
        path = _tmp_file(_png_bytes(), ".png")
        try:
            with self._with_mock_magika("png"):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_pdf_label_allowed(self):
        path = _tmp_file(_pdf_bytes(), ".pdf")
        try:
            with self._with_mock_magika("pdf"):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_generic_image_label_allowed(self):
        """Magika may emit 'image' for formats it can't classify more specifically."""
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with self._with_mock_magika("image"):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    # -- rejected labels --

    def test_executable_label_rejected(self):
        path = _tmp_file(_executable_bytes(), ".jpg")
        try:
            with self._with_mock_magika("elf"):
                self.assertFalse(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_text_label_rejected(self):
        path = _tmp_file(_text_bytes(), ".jpg")
        try:
            with self._with_mock_magika("txt"):
                self.assertFalse(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_javascript_label_rejected(self):
        path = _tmp_file(b"function x(){}", ".jpg")
        try:
            with self._with_mock_magika("javascript"):
                self.assertFalse(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    # -- fail-open behaviour --

    def test_fail_open_when_magika_unavailable(self):
        """If Magika cannot be loaded, the file must be allowed through."""
        path = _tmp_file(_executable_bytes(), ".jpg")
        try:
            with patch.object(ftp_module, "_get_magika", return_value=None):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)

    def test_fail_open_when_identify_raises(self):
        """If identify_path raises, the file must be allowed through."""
        mock_m = MagicMock()
        mock_m.identify_path.side_effect = RuntimeError("model crash")
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with patch.object(ftp_module, "_get_magika", return_value=mock_m):
                self.assertTrue(_is_content_type_allowed(path))
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Unit tests for _get_magika singleton caching
# ---------------------------------------------------------------------------

class TestGetMagikaSingleton(unittest.TestCase):

    def setUp(self):
        ftp_module._magika = None

    def test_returns_none_when_import_fails(self):
        """If magika is not installed, _get_magika must return None."""
        with patch.dict("sys.modules", {"magika": None}):
            result = ftp_module._get_magika()
        self.assertIsNone(result)

    def test_caches_instance(self):
        """Second call must not re-instantiate Magika."""
        mock_instance = MagicMock()
        mock_magika_cls = MagicMock(return_value=mock_instance)
        fake_magika_module = MagicMock()
        fake_magika_module.Magika = mock_magika_cls

        ftp_module._magika = None
        with patch.dict("sys.modules", {"magika": fake_magika_module}):
            first = ftp_module._get_magika()
            second = ftp_module._get_magika()

        self.assertIs(first, second)
        mock_magika_cls.assert_called_once()

    def tearDown(self):
        ftp_module._magika = None


# ---------------------------------------------------------------------------
# Integration: ScannerFTPHandler.on_file_received
# ---------------------------------------------------------------------------

class TestScannerFTPHandlerOnFileReceived(unittest.TestCase):
    """Test the full on_file_received pipeline with both extension and Magika checks."""

    def setUp(self):
        ftp_module._magika = None
        self.handler = ScannerFTPHandler.__new__(ScannerFTPHandler)

    def _mock_magika_label(self, label: str):
        mock_result = MagicMock()
        mock_result.output.label = label
        mock_m = MagicMock()
        mock_m.identify_path.return_value = mock_result
        return patch.object(ftp_module, "_get_magika", return_value=mock_m)

    def test_valid_jpeg_accepted(self):
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with self._mock_magika_label("jpeg"):
                # Patch statvfs via the module's own os reference (Linux-only API)
                with patch.object(ftp_module.os, "statvfs", create=True) as mock_stat:
                    mock_stat.return_value = MagicMock(f_bavail=500_000, f_frsize=4096)
                    self.handler.on_file_received(path)
            # File must still exist — it was accepted
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_disallowed_extension_deleted(self):
        path = _tmp_file(b"not-an-image", ".exe")
        try:
            self.handler.on_file_received(path)
            # File must have been deleted by the extension check
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_disguised_executable_deleted(self):
        """A .jpg file whose content Magika identifies as 'elf' must be deleted."""
        path = _tmp_file(_executable_bytes(), ".jpg")
        try:
            with self._mock_magika_label("elf"):
                self.handler.on_file_received(path)
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @unittest.skipUnless(hasattr(os, "statvfs"), "statvfs is Linux-only")
    def test_critically_low_disk_deletes_file(self):
        """If free disk space < _REFUSE_FREE_MB the file must be removed."""
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with self._mock_magika_label("jpeg"):
                with patch.object(ftp_module.os, "statvfs", create=True) as mock_stat:
                    # f_bavail * f_frsize = 10 MB — below 50 MB threshold
                    mock_stat.return_value = MagicMock(f_bavail=2560, f_frsize=4096)
                    self.handler.on_file_received(path)
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_fail_open_magika_unavailable(self):
        """If Magika is not installed the file still passes through."""
        path = _tmp_file(_jpeg_bytes(), ".jpg")
        try:
            with patch.object(ftp_module, "_get_magika", return_value=None):
                with patch.object(ftp_module.os, "statvfs", create=True) as mock_stat:
                    mock_stat.return_value = MagicMock(f_bavail=500_000, f_frsize=4096)
                    self.handler.on_file_received(path)
            self.assertTrue(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def tearDown(self):
        ftp_module._magika = None


# ---------------------------------------------------------------------------
# Sanity checks on module-level constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_allowed_extensions_non_empty(self):
        self.assertTrue(len(_ALLOWED_EXTENSIONS) > 0)

    def test_allowed_magika_labels_non_empty(self):
        self.assertTrue(len(_ALLOWED_MAGIKA_LABELS) > 0)

    def test_jpeg_extension_in_allowed(self):
        self.assertIn(".jpg", _ALLOWED_EXTENSIONS)
        self.assertIn(".jpeg", _ALLOWED_EXTENSIONS)

    def test_pdf_extension_in_allowed(self):
        self.assertIn(".pdf", _ALLOWED_EXTENSIONS)

    def test_jpeg_label_in_allowed_magika(self):
        self.assertIn("jpeg", _ALLOWED_MAGIKA_LABELS)

    def test_pdf_label_in_allowed_magika(self):
        self.assertIn("pdf", _ALLOWED_MAGIKA_LABELS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
