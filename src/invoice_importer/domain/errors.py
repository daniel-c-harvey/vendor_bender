class InvoiceImporterError(Exception):
    """Base class for all domain-level errors"""


class VendorNotFoundError(InvoiceImporterError):
    """Raised when a vendor lookup fails"""

    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(f"Vendor not found: {identifier!r}")


class InvoiceNotFoundError(InvoiceImporterError):
    """Raised when an invoice lookup fails"""

    def __init__(self, identifier: str | int) -> None:
        self.identifier = identifier
        super().__init__(f"Invoice not found: {identifier!r}")


class DuplicateInvoiceError(InvoiceImporterError):
    """Raised when attempting to import an already-known invoice."""
    
    def __init__(self, vendor: str, invoice_number: str) -> None:
        self.vendor = vendor
        self.invoice_number = invoice_number
        super().__init__(
            f"Invoice {invoice_number!r} from {vendor!r} already imported"
        )


class DuplicateContentError(InvoiceImporterError):
    """Raised when the same source content is re-imported."""
    
    def __init__(self, content_hash: str) -> None:
        self.content_hash = content_hash
        super().__init__(
            f"Content with hash {content_hash[:16]}... already imported"
        )