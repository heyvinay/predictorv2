"""The submission-confirmation email carries the brand, the entry ref,
the deep link, and the disclaimer + unmonitored-mailbox notice — across
both HTML and plain-text bodies."""

from app.services.email import (
    _build_submission_confirmation_html,
    _build_submission_confirmation_text,
)

_KWARGS = {
    "player_name": "Jane Doe",
    "entry_name": "Betting odds",
    "entry_ref": "REF-1",
    "submitted_at_display": "27 May 2026, 14:32",
    "deep_link_url": "https://wc26.heyvinay.com/entries/abc-123",
}

_BRAND = "Atlas World Cup 2026 Pools"


def test_html_contains_brand_ref_link_and_disclaimer():
    html = _build_submission_confirmation_html(**_KWARGS)
    assert _BRAND in html
    assert "REF-1" in html
    assert "Betting odds" in html
    assert "27 May 2026, 14:32" in html
    assert "https://wc26.heyvinay.com/entries/abc-123" in html
    assert "your submission is final" in html
    assert "Organisers are not responsible" in html
    assert "This mailbox is not monitored" in html
    assert "Predictor" not in html


def test_text_contains_brand_ref_link_and_disclaimer():
    text = _build_submission_confirmation_text(**_KWARGS)
    assert _BRAND in text
    assert "REF-1" in text
    assert "Betting odds" in text
    assert "27 May 2026, 14:32" in text
    assert "https://wc26.heyvinay.com/entries/abc-123" in text
    assert "Organisers are not responsible" in text
    assert "This mailbox is not monitored" in text
    assert "Predictor" not in text
