from discovery.format_report import format_validated_report
from discovery.pipeline import _merge_reports, _rerank_validated, _set_status
from discovery.report_schema import (
    AccessMethod,
    DataCompleteness,
    ReportStatus,
    ValidatedSourceItem,
    ValidatedSourceReport,
)
from inspector.browser import _score_link


def test_score_link_prefers_csv():
    assert _score_link("https://example.com/data.csv") > _score_link("https://example.com/about")


def test_format_validated_report_fixed_sections():
    report = ValidatedSourceReport(
        goal_summary="Track EV sales",
        status=ReportStatus.PARTIAL,
        min_sources_target=3,
        validated_count=1,
        validated_sources=[
            ValidatedSourceItem(
                rank=1,
                url="https://data.example.gov/ev",
                title="EV stats",
                access_method=AccessMethod.HTTP_STATIC,
                data_completeness=DataCompleteness.PARTIAL,
                quality_score=8,
                authority_score=9,
                relevance_score=8,
                format="html_table",
                likely_fields=["month", "units"],
                pages_inspected=3,
                extraction_notes="Table on landing page.",
            )
        ],
        dork_queries_used=['site:example.gov "electric vehicle"'],
    )
    text = format_validated_report(report)
    assert "=== AWDAX SOURCE DISCOVERY ===" in text
    assert "VALIDATED SOURCES (1)" in text
    assert "REJECTED (0)" in text
    assert "Access: http_static" in text


def test_merge_reports_dedupes_by_url():
    base = ValidatedSourceReport(
        goal_summary="g",
        status=ReportStatus.PARTIAL,
        min_sources_target=3,
        validated_count=1,
        validated_sources=[
            ValidatedSourceItem(
                rank=1,
                url="https://a.com",
                title="A",
                access_method=AccessMethod.HTTP_STATIC,
                data_completeness=DataCompleteness.FULL,
                quality_score=7,
                authority_score=7,
                relevance_score=7,
                format="html_table",
                pages_inspected=1,
                extraction_notes="",
            )
        ],
    )
    batch = ValidatedSourceReport(
        goal_summary="g",
        status=ReportStatus.PARTIAL,
        min_sources_target=3,
        validated_count=2,
        validated_sources=[
            ValidatedSourceItem(
                rank=1,
                url="https://a.com",
                title="A dup",
                access_method=AccessMethod.HTTP_STATIC,
                data_completeness=DataCompleteness.FULL,
                quality_score=7,
                authority_score=7,
                relevance_score=7,
                format="html_table",
                pages_inspected=1,
                extraction_notes="",
            ),
            ValidatedSourceItem(
                rank=2,
                url="https://b.com",
                title="B",
                access_method=AccessMethod.FILE_DOWNLOAD,
                data_completeness=DataCompleteness.FULL,
                quality_score=9,
                authority_score=9,
                relevance_score=9,
                format="csv",
                pages_inspected=2,
                extraction_notes="",
            ),
        ],
    )
    _merge_reports(base, batch)
    _rerank_validated(base)
    _set_status(base)
    assert len(base.validated_sources) == 2
    assert base.validated_sources[0].url == "https://b.com"
