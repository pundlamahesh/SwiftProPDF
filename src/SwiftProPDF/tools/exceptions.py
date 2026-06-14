class PdfUnlockError(Exception):
    """Raised when a PDF cannot be unlocked."""


class PdfLockError(Exception):
    """Raised when a PDF cannot be locked."""


class PdfSplitError(Exception):
    """Raised when a PDF cannot be split."""


class PdfMergeError(Exception):
    """Raised when PDFs cannot be merged."""


class PdfCompressError(Exception):
    """Raised when a PDF cannot be compressed."""


class PdfConversionError(Exception):
    """Raised when PDF conversion fails."""


class ImageConversionError(Exception):
    """Raised when image conversion fails."""


class OfficeConversionError(Exception):
    """Raised when Office document conversion fails."""


class PdfEditError(Exception):
    """Raised when PDF editing fails."""


class QrCodeError(Exception):
    """Raised when QR code generation fails."""
