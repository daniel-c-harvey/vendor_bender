# Replace your scratch_grammar.py with this:
import json
from invoice_importer.domain.models import Invoice
from llama_cpp.llama_grammar import LlamaGrammar


def main():
    schema = Invoice.model_json_schema()
    schema_json = json.dumps(schema, indent=2)
    print("=== JSON Schema (first 2000 chars) ===")
    print(schema_json[:2000])
    print("...")

    grammar = LlamaGrammar.from_json_schema(schema_json)

    print("\n=== Grammar object ===")
    print(f"type: {type(grammar)}")
    print(f"repr: {grammar!r}")

    # Try the public attributes — the actual grammar text might be on one of these
    print(f"\nattributes: {[a for a in dir(grammar) if not a.startswith('_')]}")


if __name__ == "__main__":
    main()