"""The magic-link email is branded 'Atlas World Cup 2026 Pools' and carries
the unmonitored-mailbox notice in both HTML and plain-text bodies."""

from app.services.email import _build_email_html, _build_email_text

_LINK = "https://example.com/api/auth/verify-magic-link?token=abc"
_BRAND = "Atlas World Cup 2026 Pools"
_NOTICE = "This mailbox is not monitored"


def test_html_body_branding_and_notice():
    html = _build_email_html(_LINK)
    assert _BRAND in html
    assert _NOTICE in html
    assert "Predictor" not in html


def test_text_body_branding_and_notice():
    text = _build_email_text(_LINK)
    assert _BRAND in text
    assert _NOTICE in text
    assert "Predictor" not in text
