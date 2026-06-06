"""The submission-confirmation email carries the brand, the entry ref,
the deep link, and the disclaimer + unmonitored-mailbox notice — across
both HTML and plain-text bodies. Also verifies that an optional recap
appends a group/knockout/bonus section without breaking the no-recap path."""

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

_SAMPLE_RECAP = {
    "groups": [
        {
            "letter": "A",
            "fixtures": [
                {"home": "Mexico", "away": "South Africa", "home_score": 2, "away_score": 1},
                {"home": "South Korea", "away": "Czechia", "home_score": 1, "away_score": 0},
                {"home": "Czechia", "away": "South Africa", "home_score": 2, "away_score": 0},
            ],
        }
    ],
    "knockout": [
        {"stage": "round_of_32", "label": "ROUND OF 32", "teams": ["Mexico", "Brazil"]},
        {"stage": "final", "label": "FINAL", "teams": ["Spain", "Portugal"]},
    ],
    "champion": "Portugal",
    "bonus": [
        {"question_label": "Goal Machine — top scorer team", "answer": "Argentina"},
    ],
}


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


def test_html_without_recap_omits_recap_section():
    html = _build_submission_confirmation_html(**_KWARGS, recap=None)
    # The recap section uses a distinctive uppercase label that won't appear
    # in the standard confirmation copy.
    assert "GROUP STAGE" not in html
    assert "KNOCKOUT STAGE" not in html
    assert "BONUS QUESTIONS" not in html


def test_html_with_recap_includes_groups_knockout_champion_bonus():
    html = _build_submission_confirmation_html(**_KWARGS, recap=_SAMPLE_RECAP)
    assert "GROUP STAGE" in html.upper()
    assert "GROUP A" in html
    assert "Mexico" in html
    # Score in the table is rendered as "2 - 1" (with spaces around the dash).
    assert "2 - 1" in html
    assert "KNOCKOUT STAGE" in html.upper()
    assert "ROUND OF 32" in html
    assert "Portugal" in html
    assert "CHAMPION" in html.upper()
    assert "BONUS QUESTIONS" in html.upper()
    assert "Goal Machine" in html
    assert "Argentina" in html


def test_text_with_recap_includes_group_knockout_bonus_lines():
    text = _build_submission_confirmation_text(**_KWARGS, recap=_SAMPLE_RECAP)
    assert "GROUP STAGE" in text
    assert "GROUP A" in text
    assert "Mexico" in text
    assert "2 - 1" in text
    assert "KNOCKOUT STAGE" in text
    assert "ROUND OF 32" in text
    assert "CHAMPION" in text
    assert "Portugal" in text
    assert "BONUS QUESTIONS" in text
    assert "Argentina" in text


def test_html_short_name_applied_in_recap():
    """SHORT_NAMES port should render 'S. Africa' not 'South Africa'."""
    html = _build_submission_confirmation_html(**_KWARGS, recap=_SAMPLE_RECAP)
    assert "S. Africa" in html
    # Full name should NOT appear in fixture rows (the short version replaces it).
    # We don't assert "South Africa" not-in-html absolutely, since other copy
    # might mention it later — just confirm the short form rendered.
