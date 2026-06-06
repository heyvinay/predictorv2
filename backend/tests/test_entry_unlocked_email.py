"""The entry-unlocked email tells the user their entry is back in draft
and points them at the resubmit deep link. Deadline reminder is included
when present and omitted gracefully when the competition hasn't set one."""

from app.services.email import (
    _build_entry_unlocked_html,
    _build_entry_unlocked_text,
)

_KWARGS = {
    "player_name": "Jane Doe",
    "entry_name": "Betting odds",
    "entry_ref": "REF-1",
    "deadline_display": "11 Jun 2026, 17:00 UTC",
    "deep_link_url": "https://wc26.heyvinay.com/entries/abc-123",
}

_BRAND = "Atlas World Cup 2026 Pools"


def test_html_contains_brand_back_in_draft_and_deadline():
    html = _build_entry_unlocked_html(**_KWARGS)
    assert _BRAND in html
    assert "REF-1" in html
    assert "Betting odds" in html
    assert "back in draft" in html.lower()
    assert "won't count toward scoring" in html
    assert "11 Jun 2026, 17:00 UTC" in html
    assert "https://wc26.heyvinay.com/entries/abc-123" in html
    assert "Go to my entry" in html


def test_text_contains_brand_back_in_draft_and_deadline():
    text = _build_entry_unlocked_text(**_KWARGS)
    assert _BRAND in text
    assert "REF-1" in text
    assert "Betting odds" in text
    assert "back in draft" in text.lower()
    assert "won't count toward scoring" in text
    assert "11 Jun 2026, 17:00 UTC" in text
    assert "https://wc26.heyvinay.com/entries/abc-123" in text


def test_html_without_deadline_omits_deadline_line():
    kwargs = {**_KWARGS, "deadline_display": None}
    html = _build_entry_unlocked_html(**kwargs)
    # No deadline string, no "Don't forget" reminder.
    assert "11 Jun 2026" not in html
    assert "Don't forget" not in html
    # The rest of the body still renders.
    assert "back in draft" in html.lower()
    assert "Go to my entry" in html


def test_text_without_deadline_omits_deadline_line():
    kwargs = {**_KWARGS, "deadline_display": None}
    text = _build_entry_unlocked_text(**kwargs)
    assert "11 Jun 2026" not in text
    assert "Don't forget" not in text
    assert "back in draft" in text.lower()
