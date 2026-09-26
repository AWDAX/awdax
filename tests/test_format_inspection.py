from discovery.format_report import format_validated_report
from discovery.report_schema import (
    AccessMethod,
    DataCompleteness,
    ReportStatus,
    SourceInspectionBlock,
    ValidatedSourceItem,
    ValidatedSourceReport,
)


def test_format_includes_extraction_query_under_source():
    report = ValidatedSourceReport(
        goal_summary="EV list India",
        status=ReportStatus.SUCCESS,
        min_sources_target=3,
        validated_count=1,
        validated_sources=[
            ValidatedSourceItem(
                rank=1,
                url="https://example.com/ev",
                title="EV prices",
                access_method=AccessMethod.HTTP_STATIC,
                data_completeness=DataCompleteness.FULL,
                quality_score=8,
                authority_score=8,
                relevance_score=9,
                format="html_table",
                pages_inspected=2,
                extraction_notes="ok",
            )
        ],
        source_inspections=[
            SourceInspectionBlock(
                url="https://example.com/ev",
                page_title="EV prices",
                what_we_see="Grid of car cards with ex-showroom prices.",
                page_structure=["~40 card blocks", "Pagination at bottom"],
                best_extraction_method="headless_dom",
                extraction_query="METHOD=headless_dom\nURL=https://example.com/ev\nTARGET=.car-card",
                expected_columns=["model", "price"],
                confidence=8,
            )
        ],
    )
    text = format_validated_report(report)
    assert "Site inspection (headless):" in text
    assert "What we see:" in text
    assert "Extraction query:" in text
    assert "METHOD=headless_dom" in text
