from extraction.format import format_extraction_result
from extraction.merge import merge_tables
from extraction.models import ExtractedTable, ExtractorInfo, ExtractionRunResult
from extraction.parse_plan import parse_extraction_query
from extractors import html_tables


SAMPLE_TABLE = """
<html><body><table>
<tr><th>Model</th><th>Price</th></tr>
<tr><td>Car A</td><td>₹10 lakh</td></tr>
<tr><td>Car B</td><td>₹12 lakh</td></tr>
</table></body></html>
"""


def test_html_tables_extractor():
    rows = html_tables.extract(SAMPLE_TABLE, "https://example.com")
    assert len(rows) == 2
    assert rows[0]["Model"] == "Car A"


def test_parse_extraction_query():
    q = "METHOD=headless_dom\nURL=https://x.com\nTARGET=.card\nCOLUMNS=model,price\n"
    p = parse_extraction_query(q, fallback_url="https://fallback")
    assert p.method == "headless_dom"
    assert p.columns == ["model", "price"]


def test_format_shows_new_code_flag():
    result = ExtractionRunResult(
        user_goal="ev cars",
        columns_chosen=["model", "price"],
        column_rationale="Listing goal",
        cooked_new_code=True,
        extractors_used=[
            ExtractorInfo(
                extractor_id="gen_abc",
                path="extractors/generated/gen_abc.py",
                is_new=True,
                method_used="generated_extractor",
                notes="custom",
            )
        ],
        tables=[
            ExtractedTable(
                name="Test",
                source_url="https://example.com",
                columns=["model", "price"],
                rows=[["A", "1"]],
                row_count=1,
            )
        ],
        master_table=merge_tables(
            [
                ExtractedTable(
                    name="Test",
                    source_url="https://example.com",
                    columns=["model", "price"],
                    rows=[["A", "1"]],
                    row_count=1,
                )
            ]
        ),
        summary="ok",
    )
    text = format_extraction_result(result)
    assert "New code: YES" in text
    assert "=== AWDAX EXTRACTION ===" in text
    assert "| S. No. | source | source_url | model | price |" in text
