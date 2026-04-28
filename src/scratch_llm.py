# scratch_llm.py
import asyncio
from datetime import date
from decimal import Decimal

from invoice_importer.config import get_settings
from invoice_importer.domain.models import CurrencyCode
from invoice_importer.extraction.interpretation.anthropic_client import AnthropicInterpreter
from invoice_importer.extraction.types import ExtractedText

SAMPLE_INVOICE_TEXT = """\
AMERICANSCRAPMETALLLC
PROFORMAINVOICE
8031 Eastside Rd
Date
02//29/2024
Redding,CA96001
Expiration Date
3/29/2024
Phone: 973-963-7801
Invoice#
204
Email: american.scrap.metal.contact@gmail.com
Customer ID
75546
MERICAA
CUSTOMER
SHIPPINGDETAILS
Saeed Didehvar
SCRAP
METAL
Freight Type
Sea
Banda Abbas, Iran
Est Ship Date
Unknown
(+98) 937 433 2540
Est Gross Weight
267Tons
Est Cubic Weight
Unknown
Total Packages
PART
UNITOF
IN
TOTAL
NUMBER
MEASURE DESCRIPTION
QTY
PRICE
TAX
AMOUNT
N/A
Metric Ton Copper wire
50
2,290.00
0
114,500.00
N/A
MetricTonAluminum 6063
117
710.00
0
83,070.00
Subtotal
197,570.00
TERMSOFSALEANDOTHERCOMMENTS
Taxable
All purchase is irrevocable
Taxrate
0.000%
Tax
Freight
Insurance
Legal/Consular
Inspection/Cert.
Other (specify)
Other (specify)
$197,570.00
Currency
USD
ADDITIONAL DETAILS
Country of Origin
United State
Port of Embarkation
California Port, USA
Port of Discharge
Durban Port, South Africa
Reason for Export:
Metal trade
I certify the above to be true and correct to the best of my knowledge.
2/29/2024
Eric NOUKOU
Date
American Scrap Metal
"""


async def main() -> None:
    settings = get_settings()

    interpreter = AnthropicInterpreter(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
    )

    # Manual ExtractedText with deterministic content
    extracted = ExtractedText(
        text=SAMPLE_INVOICE_TEXT,
        page_count=1,
        extractor="manual",
        is_likely_low_quality=False,
    )

    print(f"=== Sending {len(extracted.text)} chars to {interpreter.name} ===\n")

    invoice = await interpreter.interpret(extracted)

    print("=== Interpreted Invoice ===")
    print(f"Number:    {invoice.invoice_number}")
    print(f"Issue:     {invoice.issue_date}")
    print(f"Due:       {invoice.due_date}")
    print(f"Vendor:    {invoice.vendor.name}")
    print(f"Tax ID:    {invoice.vendor.tax_id}")
    if invoice.vendor.address:
        addr = invoice.vendor.address
        print(f"Address:   {addr.line1}, {addr.city}, {addr.country}")
    print(f"Currency:  {invoice.currency.value}")
    print(f"Subtotal:  {invoice.subtotal}")
    print(f"Tax:       {invoice.tax_total}")
    print(f"Total:     {invoice.grand_total}")
    print(f"Lines:     {len(invoice.line_items)}")
    for li in invoice.line_items:
        print(f"  {li.line_number}. {li.description}")
        print(f"     {li.quantity} × {li.unit_price} = {li.line_total}")

    # Sanity checks against the input
    print("\n=== Sanity Checks ===")
    expected_total = Decimal("197570")
    expected_date = date(2024, 2, 29)
    expected_lines = 2

    checks = [
        ("grand_total matches", invoice.grand_total == expected_total),
        ("issue_date matches", invoice.issue_date == expected_date),
        ("line count matches", len(invoice.line_items) == expected_lines),
        ("currency is USD", invoice.currency == CurrencyCode.USD),
        ("vendor name correct", invoice.vendor.name.casefold() == "American Scrap Metal LLC".casefold()),
    ]
    for label, passed in checks:
        marker = "✓" if passed else "✗"
        print(f"  {marker} {label}")


if __name__ == "__main__":
    asyncio.run(main())