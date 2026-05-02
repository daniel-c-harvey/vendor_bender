from invoice_importer.domain.models import Invoice
from invoice_importer.extraction.types import ContentType, ExtractedDocument, SourceContent, Page


class FakeExtractor:
    name: str
    supported_content_types: frozenset[ContentType]

    def __init__(self, *, name: str, supported_content_types: frozenset[ContentType]) -> None:
        self.name = name
        self.supported_content_types = frozenset(supported_content_types)

    def extract(self, source: SourceContent) -> ExtractedDocument:
        return ExtractedDocument(
            pages=(Page(page_number=1, blocks=()),),
            extractor=self.name,
        )

class FakeInterpreter:
    """Satisfies the LLMInterpreter Protocol structurally.

        Returns a canned Invoice regardless of the ExtractedText input.
        Tests set the invoice they want the orchestrator to persist, then
        assert on the hydrated Invoice that comes back from the pipeline.
        """
    name: str
    _invoice: Invoice

    def __init__(self, *, name: str, invoice: Invoice) -> None:
        self.name = name
        self._invoice = invoice

    async def interpret(self, text: ExtractedDocument) -> Invoice:
        return self._invoice