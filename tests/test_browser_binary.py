from inspector.browser import _is_binary_url, _should_visit_related


def test_pdf_is_binary():
    assert _is_binary_url("https://stimg.cardekho.com/policy/CSR-Policy-GSPL.pdf")


def test_skip_policy_pdf_related():
    assert not _should_visit_related("https://stimg.cardekho.com/policy/CSR-Policy-GSPL.pdf")
