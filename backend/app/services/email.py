"""Email delivery via Resend API.

Used by the magic-link auth flow to send sign-in links. In dev mode
without `RESEND_API_KEY` set, the link is logged to stdout instead so
local testing doesn't require an email account.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.services.broadcast import BroadcastSegment
from app.services.team_name import display_team_name

logger = logging.getLogger(__name__)

RESEND_API_URL: str = "https://api.resend.com/emails"

# Where in-app rating/feedback lands. A module constant rather than a
# Settings field for now — it's the pool owner's inbox and unlikely to
# change; promote to `Settings` if a staging env ever needs to redirect it.
FEEDBACK_RECIPIENT_EMAIL: str = "heyvinay@gmail.com"


async def send_magic_link_email(to_email: str, magic_link_url: str) -> None:
    """Send a magic sign-in link via Resend.

    In debug mode with no API key configured, logs the link instead of
    sending — allows local testing without an email account.

    Raises :class:`RuntimeError` if Resend returns a non-2xx status code
    in production mode (so the API endpoint can return 500 to the
    client and the user knows to try again).
    """
    settings = get_settings()

    if not settings.resend_api_key:
        # Dev fallback: print to stdout directly so the link surfaces in
        # docker logs without depending on app-level logger config.
        print(
            "[magic-link] RESEND_API_KEY not set — dev mode, printing link instead of sending:",
            flush=True,
        )
        print(f"[magic-link] {magic_link_url}", flush=True)
        return

    html_body = _build_email_html(magic_link_url)
    text_body = _build_email_text(magic_link_url)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": to_email,
                "subject": "Welcome — your Atlas World Cup 2026 Pools sign-in link",
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error("[magic-link] Resend API error %s: %s", response.status_code, response.text)
        raise RuntimeError("Failed to send magic link email")


async def send_feedback_email(
    *,
    rating: int,
    message: str,
    reply_to: str,
    user_name: str,
    features_line: str = "",
) -> None:
    """Email a user's in-app rating + written feedback to the pool owner.

    Same Resend path as :func:`send_magic_link_email`. In dev without
    ``RESEND_API_KEY`` the feedback is printed to stdout instead of sent, so
    local testing needs no email account. Raises :class:`RuntimeError` on a
    non-2xx Resend response so the API endpoint can surface the failure to
    the client ("couldn't send — try again").

    ``reply_to`` is the submitter's email, set as the message Reply-To so a
    reply straight from the inbox reaches them.

    ``features_line`` (v2.214.x) is an optional comma-separated list of
    feature chips the submitter flagged as favourites — appended to the
    body when non-empty, omitted entirely otherwise.
    """
    settings = get_settings()

    stars = "★" * rating + "☆" * (5 - rating)

    if not settings.resend_api_key:
        # Dev fallback — surface in docker logs without needing Resend.
        print("[feedback] RESEND_API_KEY not set — dev mode, printing instead of sending:", flush=True)
        print(f"[feedback] {stars} ({rating}/5) from {user_name} <{reply_to}>", flush=True)
        print(f"[feedback] {message}", flush=True)
        if features_line:
            print(f"[feedback] Favourite features: {features_line}", flush=True)
        return

    subject = f"New feedback — {stars} from {user_name}"
    html_body = _build_feedback_html(
        stars=stars,
        rating=rating,
        # Escape user-controlled strings before interpolating into HTML.
        safe_name=html.escape(user_name or "A pool member"),
        safe_reply=html.escape(reply_to),
        safe_message=html.escape(message),
        safe_features_line=html.escape(features_line) if features_line else "",
    )
    text_body = f"{stars} ({rating}/5) from {user_name} <{reply_to}>\n\n{message}\n"
    if features_line:
        text_body += f"\nFavourite features: {features_line}\n"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": FEEDBACK_RECIPIENT_EMAIL,
                "reply_to": reply_to,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error("[feedback] Resend API error %s: %s", response.status_code, response.text)
        raise RuntimeError("Failed to send feedback email")


def _build_feedback_html(
    *,
    stars: str,
    rating: int,
    safe_name: str,
    safe_reply: str,
    safe_message: str,
    safe_features_line: str = "",
) -> str:
    """Render the feedback email body (inline CSS, brand palette). All
    interpolated user strings must already be HTML-escaped by the caller."""
    features_html = (
        f'<div style="font-size:12px;color:{_MUTED_INK};margin-top:10px;">'
        f'Favourite features: {safe_features_line}</div>'
        if safe_features_line
        else ""
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8" />'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0" /></head>'
        f'<body style="margin:0;padding:0;background:{_PAGE_BG};'
        f'font-family:{_BODY_FONT};color:{_BODY_INK};">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAGE_BG};padding:32px 12px;"><tr><td align="center">'
        '<table width="520" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:520px;width:100%;background:{_CARD_BG};border-radius:12px;'
        'overflow:hidden;box-shadow:0 6px 24px -12px rgba(11,19,41,0.18);">'
        f'<tr><td style="background:{_NAVY};padding:24px;">'
        f'<div style="font-family:{_DISPLAY_FONT};font-size:15px;color:{_GOLD};'
        'letter-spacing:1px;">ATLAS WORLD CUP POOLS</div>'
        '<div style="color:#ffffff;font-size:18px;margin-top:6px;">New feedback</div></td></tr>'
        '<tr><td style="padding:24px;">'
        f'<div style="font-size:26px;color:{_GOLD};letter-spacing:3px;">{stars}</div>'
        f'<div style="font-size:13px;color:{_MUTED_INK};margin:4px 0 18px;">'
        f'{rating} / 5 · from {safe_name} &lt;{safe_reply}&gt;</div>'
        f'<div style="font-size:15px;line-height:1.6;white-space:pre-wrap;'
        f'border-left:3px solid {_GOLD};padding:4px 0 4px 14px;">{safe_message}</div>'
        f'{features_html}'
        f'<div style="font-size:12px;color:{_MUTED_INK};margin-top:20px;">'
        f'Reply to this email to respond to {safe_name} directly.</div>'
        '</td></tr></table></td></tr></table></body></html>'
    )


# Brand palette — premium-night derived. Resolved as hex (no CSS vars).
_NAVY = "#0B1329"          # Midnight navy
_GOLD = "#D4AF37"          # Champagne gold
_CARD_BG = "#F8FAFC"       # Ice white card surface
_PAGE_BG = "#EEF2F7"       # Neutral page background
_BODY_INK = "#1F2937"      # Slate-800 — body text
_MUTED_INK = "#64748B"     # Slate-500 — secondary
# System-font stack — picks up the native OS font in every client.
_BODY_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
)
# Serif fallback for the wordmark. Bebas Neue isn't loadable in mail
# clients; Georgia gives a confident editorial feel everywhere.
_DISPLAY_FONT = "Georgia,'Times New Roman',serif"
# Monospace stack for the receipt-style recap section.
_MONO_FONT = "'JetBrains Mono','Courier New',monospace"


def _build_email_html(magic_link_url: str) -> str:
    """Render the welcome / sign-in email body.

    Designed for cross-client rendering: inline CSS only, no web fonts,
    no background images, no relative URLs. Width-attribute on the
    outer table so Outlook respects layout.
    """
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1.0" />\n'
        '  <title>Welcome — your Atlas World Cup 2026 Pools sign-in link</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{_PAGE_BG};'
        f'font-family:{_BODY_FONT};color:{_BODY_INK};">\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAGE_BG};padding:32px 12px;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '        <table width="520" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:520px;width:100%;background:{_CARD_BG};'
        'border-radius:12px;overflow:hidden;'
        'box-shadow:0 6px 24px -12px rgba(11,19,41,0.18);">\n'
        # ---- Header band: dark navy, gold wordmark ----
        '          <tr>\n'
        '            <td align="center" '
        f'style="background:{_NAVY};padding:28px 24px;">\n'
        f'              <div style="font-family:{_DISPLAY_FONT};font-size:16px;'
        'font-weight:700;letter-spacing:0.10em;white-space:nowrap;'
        f'color:{_GOLD};text-transform:uppercase;line-height:1.2;">'
        'Atlas World Cup 2026 Pools</div>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Body ----
        '          <tr>\n'
        '            <td style="padding:36px 32px 8px 32px;">\n'
        f'              <h1 style="margin:0 0 12px 0;font-family:{_DISPLAY_FONT};'
        f'font-size:24px;font-weight:700;color:{_NAVY};letter-spacing:-0.01em;">'
        'Welcome to Atlas World Cup 2026 Pools.</h1>\n'
        f'              <p style="margin:0 0 18px 0;font-size:15px;line-height:1.55;'
        f'color:{_BODY_INK};">'
        'Your sign-in link is ready. One click below and you\'re in '
        '— no password to remember.</p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- CTA button ----
        '          <tr>\n'
        '            <td align="center" style="padding:8px 32px 24px 32px;">\n'
        f'              <a href="{magic_link_url}" '
        f'style="display:inline-block;background:{_GOLD};color:{_NAVY};'
        f'font-family:{_BODY_FONT};font-size:14px;font-weight:700;'
        'letter-spacing:0.06em;text-transform:uppercase;text-decoration:none;'
        'padding:14px 28px;border-radius:8px;">'
        'Sign in</a>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Raw URL fallback (for clients that strip buttons) ----
        '          <tr>\n'
        '            <td style="padding:0 32px 24px 32px;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};word-break:break-all;">'
        'If the button doesn\'t work, paste this link into your browser:<br/>\n'
        f'                <a href="{magic_link_url}" '
        f'style="color:{_MUTED_INK};text-decoration:underline;">'
        f'{magic_link_url}</a>'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Footer: expiry + ignore note ----
        '          <tr>\n'
        '            <td '
        f'style="padding:18px 32px 28px 32px;border-top:1px solid #E2E8F0;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This link expires in 15 minutes and can only be used once. '
        'If you didn\'t request it, you can safely ignore this email.</p>\n'
        f'              <p style="margin:10px 0 0 0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This mailbox is not monitored — please don\'t reply to this email.</p>\n'
        '              <p style="margin:14px 0 0 0;font-size:12px;'
        f'color:{_MUTED_INK};">— Atlas World Cup 2026 Pools</p>\n'
        '            </td>\n'
        '          </tr>\n'
        '        </table>\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '</body>\n'
        '</html>'
    )


def _build_email_text(magic_link_url: str) -> str:
    """Plain-text alternative for mail clients that strip HTML."""
    return (
        "Welcome to Atlas World Cup 2026 Pools.\n"
        "\n"
        "Your sign-in link is ready. Open it in your browser to sign in:\n"
        f"{magic_link_url}\n"
        "\n"
        "This link expires in 15 minutes and can only be used once.\n"
        "If you didn't request it, you can safely ignore this email.\n"
        "\n"
        "This mailbox is not monitored — please don't reply to this email.\n"
        "\n"
        "— Atlas World Cup 2026 Pools\n"
    )


# ── Submission confirmation email (R7) ───────────────────────────────────────


async def send_submission_confirmation_email(
    *,
    to_email: str,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    submitted_at_display: str,
    deep_link_url: str,
    recap: dict | None = None,
) -> None:
    """Send a "your submission is locked in" receipt to the player.

    Called from the entries submit flow after the entry transitions to
    SUBMITTED. Best-effort: the caller should wrap this in try/except so a
    Resend failure does NOT roll back the submission (the entry is already
    locked in the DB and audit-logged; the email is a receipt).

    The optional ``recap`` arg (shape from
    :func:`app.services.entry_recap.build_entry_recap`) appends a monospace
    recap of the user's predictions to the email body. If omitted (or the
    recap builder fails upstream), the email sends without it.

    Mirrors :func:`send_magic_link_email`'s dev fallback — when
    ``RESEND_API_KEY`` is unset the body is logged to stdout instead of
    sent, so local testing needs no email account.
    """
    settings = get_settings()
    subject = (
        f'World Cup 2026 Pool — Submission locked in: "{entry_name}" ({entry_ref})'
    )

    if not settings.resend_api_key:
        # Dev fallback — surface the receipt in docker logs.
        print(
            "[submission] RESEND_API_KEY not set — dev mode, printing receipt:",
            flush=True,
        )
        print(f"[submission] to={to_email} subject={subject!r}", flush=True)
        print(f"[submission] link={deep_link_url}", flush=True)
        return

    html_body = _build_submission_confirmation_html(
        player_name=player_name,
        entry_name=entry_name,
        entry_ref=entry_ref,
        submitted_at_display=submitted_at_display,
        deep_link_url=deep_link_url,
        recap=recap,
    )
    text_body = _build_submission_confirmation_text(
        player_name=player_name,
        entry_name=entry_name,
        entry_ref=entry_ref,
        submitted_at_display=submitted_at_display,
        deep_link_url=deep_link_url,
        recap=recap,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": to_email,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error(
            "[submission] Resend API error %s: %s",
            response.status_code,
            response.text,
        )
        raise RuntimeError("Failed to send submission confirmation email")


def _build_submission_confirmation_html(
    *,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    submitted_at_display: str,
    deep_link_url: str,
    recap: dict | None = None,
) -> str:
    """Render the submission receipt email body.

    Reuses the same navy/gold chrome as the magic-link email so the brand
    reads consistently across the two messages. Inline CSS only — no web
    fonts, no remote images, no relative URLs.
    """
    safe_entry = entry_name.replace('"', '&quot;')
    recap_html = _build_recap_html(recap) if recap else ""
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1.0" />\n'
        f'  <title>Submission locked in — {safe_entry} ({entry_ref})</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{_PAGE_BG};'
        f'font-family:{_BODY_FONT};color:{_BODY_INK};">\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAGE_BG};padding:32px 12px;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '        <table width="520" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:520px;width:100%;background:{_CARD_BG};'
        'border-radius:12px;overflow:hidden;'
        'box-shadow:0 6px 24px -12px rgba(11,19,41,0.18);">\n'
        # ---- Header band (matches magic-link email) ----
        '          <tr>\n'
        '            <td align="center" '
        f'style="background:{_NAVY};padding:28px 24px;">\n'
        f'              <div style="font-family:{_DISPLAY_FONT};font-size:16px;'
        'font-weight:700;letter-spacing:0.10em;white-space:nowrap;'
        f'color:{_GOLD};text-transform:uppercase;line-height:1.2;">'
        'Atlas World Cup 2026 Pools</div>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Body ----
        '          <tr>\n'
        '            <td style="padding:36px 32px 8px 32px;">\n'
        f'              <h1 style="margin:0 0 12px 0;font-family:{_DISPLAY_FONT};'
        f'font-size:22px;font-weight:700;color:{_NAVY};letter-spacing:-0.01em;">'
        'Your submission is locked in.</h1>\n'
        f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
        f'color:{_BODY_INK};">'
        f'Thanks {player_name}, your entry <strong>"{safe_entry}"</strong> '
        f'(Ref: {entry_ref}) is in. It was submitted on '
        f'<strong>{submitted_at_display}</strong> and will be scored against '
        'the live results.</p>\n'
        f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
        f'color:{_BODY_INK};">'
        'You can edit your submission any time before the competition starts. '
        'Once it begins, your submission is final — it cannot be edited, '
        'withdrawn, or replaced.</p>\n'
        f'              <p style="margin:0 0 18px 0;font-size:14px;line-height:1.55;'
        f'color:{_MUTED_INK};">'
        'Organisers are not responsible for any incorrect submissions. '
        'Points will be assigned based on your picks as submitted.</p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Recap (group / knockout / bonus) — omitted if recap is None ----
        f'{recap_html}'
        # ---- CTA button ----
        '          <tr>\n'
        '            <td align="center" style="padding:8px 32px 24px 32px;">\n'
        f'              <a href="{deep_link_url}" '
        f'style="display:inline-block;background:{_GOLD};color:{_NAVY};'
        f'font-family:{_BODY_FONT};font-size:14px;font-weight:700;'
        'letter-spacing:0.06em;text-transform:uppercase;text-decoration:none;'
        'padding:14px 28px;border-radius:8px;">'
        'View and edit your submission</a>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Raw URL fallback ----
        '          <tr>\n'
        '            <td style="padding:0 32px 24px 32px;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};word-break:break-all;">'
        'If the button doesn\'t work, paste this link into your browser:<br/>\n'
        f'                <a href="{deep_link_url}" '
        f'style="color:{_MUTED_INK};text-decoration:underline;">'
        f'{deep_link_url}</a>'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Footer ----
        '          <tr>\n'
        '            <td '
        f'style="padding:18px 32px 28px 32px;border-top:1px solid #E2E8F0;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This link will open your entry once you\'re signed in.</p>\n'
        f'              <p style="margin:10px 0 0 0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This mailbox is not monitored — please don\'t reply to this email.</p>\n'
        f'              <p style="margin:14px 0 0 0;font-size:12px;'
        f'color:{_MUTED_INK};">— Atlas World Cup 2026 Pools</p>\n'
        '            </td>\n'
        '          </tr>\n'
        '        </table>\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '</body>\n'
        '</html>'
    )


def _build_submission_confirmation_text(
    *,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    submitted_at_display: str,
    deep_link_url: str,
    recap: dict | None = None,
) -> str:
    """Plain-text alternative for mail clients that strip HTML."""
    recap_text = _build_recap_text(recap) if recap else ""
    return (
        "Your submission is locked in.\n"
        "\n"
        f'Thanks {player_name}, your entry "{entry_name}" (Ref: {entry_ref})\n'
        f'is in. It was submitted on {submitted_at_display} and will be\n'
        "scored against the live results.\n"
        "\n"
        "You can edit your submission any time before the competition\n"
        "starts. Once it begins, your submission is final — it cannot be\n"
        "edited, withdrawn, or replaced.\n"
        "\n"
        "Organisers are not responsible for any incorrect submissions.\n"
        "Points will be assigned based on your picks as submitted.\n"
        f"{recap_text}"
        "\n"
        "View and edit your submission:\n"
        f"{deep_link_url}\n"
        "\n"
        "This link will open your entry once you're signed in.\n"
        "This mailbox is not monitored — please don't reply to this email.\n"
        "\n"
        "— Atlas World Cup 2026 Pools\n"
    )


# ── Entry-unlocked email (sent when a SUBMITTED entry reverts to DRAFT) ──────


async def send_entry_unlocked_email(
    *,
    to_email: str,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    deadline_display: str | None,
    deep_link_url: str,
) -> None:
    """Send a "your entry is back in draft — submit again" email.

    Fired after the /entries/{id}/edit endpoint flips SUBMITTED → DRAFT.
    Safety-net transactional notice: users may unlock to tweak a pick,
    close the tab, and forget to re-submit. Without the email the entry
    silently doesn't count toward scoring.

    Best-effort like the other transactional emails — the caller wraps
    this in try/except so a Resend outage doesn't block the API response.

    ``deadline_display`` is a pre-formatted string ("11 Jun 2026, 17:00")
    or ``None`` if the competition hasn't set a deadline (degrades to
    omitting the deadline sentence).
    """
    settings = get_settings()
    subject = (
        f'World Cup 2026 Pool — Entry back in draft: "{entry_name}" ({entry_ref})'
    )

    if not settings.resend_api_key:
        # Dev fallback — surface the receipt in docker logs.
        print(
            "[unlock] RESEND_API_KEY not set — dev mode, printing receipt:",
            flush=True,
        )
        print(f"[unlock] to={to_email} subject={subject!r}", flush=True)
        print(f"[unlock] link={deep_link_url}", flush=True)
        return

    html_body = _build_entry_unlocked_html(
        player_name=player_name,
        entry_name=entry_name,
        entry_ref=entry_ref,
        deadline_display=deadline_display,
        deep_link_url=deep_link_url,
    )
    text_body = _build_entry_unlocked_text(
        player_name=player_name,
        entry_name=entry_name,
        entry_ref=entry_ref,
        deadline_display=deadline_display,
        deep_link_url=deep_link_url,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": to_email,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error(
            "[unlock] Resend API error %s: %s",
            response.status_code,
            response.text,
        )
        raise RuntimeError("Failed to send entry-unlocked email")


def _build_entry_unlocked_html(
    *,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    deadline_display: str | None,
    deep_link_url: str,
) -> str:
    """Render the entry-unlocked email body.

    Uses the same navy/gold chrome as the confirmation email so the two
    transactional emails read as a pair. Inline CSS only.
    """
    safe_entry = entry_name.replace('"', '&quot;')
    deadline_line = (
        f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
        f'color:{_BODY_INK};">'
        'Don\'t forget — all predictions must be submitted before '
        f'<strong>{deadline_display}</strong>.</p>\n'
        if deadline_display
        else ""
    )
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1.0" />\n'
        f'  <title>Entry back in draft — {safe_entry} ({entry_ref})</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{_PAGE_BG};'
        f'font-family:{_BODY_FONT};color:{_BODY_INK};">\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAGE_BG};padding:32px 12px;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '        <table width="520" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:520px;width:100%;background:{_CARD_BG};'
        'border-radius:12px;overflow:hidden;'
        'box-shadow:0 6px 24px -12px rgba(11,19,41,0.18);">\n'
        # ---- Header band ----
        '          <tr>\n'
        '            <td align="center" '
        f'style="background:{_NAVY};padding:28px 24px;">\n'
        f'              <div style="font-family:{_DISPLAY_FONT};font-size:16px;'
        'font-weight:700;letter-spacing:0.10em;white-space:nowrap;'
        f'color:{_GOLD};text-transform:uppercase;line-height:1.2;">'
        'Atlas World Cup 2026 Pools</div>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Body ----
        '          <tr>\n'
        '            <td style="padding:36px 32px 8px 32px;">\n'
        f'              <h1 style="margin:0 0 12px 0;font-family:{_DISPLAY_FONT};'
        f'font-size:22px;font-weight:700;color:{_NAVY};letter-spacing:-0.01em;">'
        'Your entry is back in draft.</h1>\n'
        f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
        f'color:{_BODY_INK};">'
        f"Hi {player_name}, you've unlocked your entry "
        f'<strong>"{safe_entry}"</strong> (Ref: {entry_ref}). It\'s now in draft form '
        '<strong>and won\'t count toward scoring until you submit it again</strong>.</p>\n'
        f'{deadline_line}'
        '            </td>\n'
        '          </tr>\n'
        # ---- CTA button ----
        '          <tr>\n'
        '            <td align="center" style="padding:8px 32px 24px 32px;">\n'
        f'              <a href="{deep_link_url}" '
        f'style="display:inline-block;background:{_GOLD};color:{_NAVY};'
        f'font-family:{_BODY_FONT};font-size:14px;font-weight:700;'
        'letter-spacing:0.06em;text-transform:uppercase;text-decoration:none;'
        'padding:14px 28px;border-radius:8px;">'
        'Go to my entry</a>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Raw URL fallback ----
        '          <tr>\n'
        '            <td style="padding:0 32px 24px 32px;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};word-break:break-all;">'
        'If the button doesn\'t work, paste this link into your browser:<br/>\n'
        f'                <a href="{deep_link_url}" '
        f'style="color:{_MUTED_INK};text-decoration:underline;">'
        f'{deep_link_url}</a>'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Footer ----
        '          <tr>\n'
        '            <td '
        f'style="padding:18px 32px 28px 32px;border-top:1px solid #E2E8F0;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This mailbox is not monitored — please don\'t reply to this email.</p>\n'
        f'              <p style="margin:14px 0 0 0;font-size:12px;'
        f'color:{_MUTED_INK};">— Atlas World Cup 2026 Pools</p>\n'
        '            </td>\n'
        '          </tr>\n'
        '        </table>\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '</body>\n'
        '</html>'
    )


def _build_entry_unlocked_text(
    *,
    player_name: str,
    entry_name: str,
    entry_ref: str,
    deadline_display: str | None,
    deep_link_url: str,
) -> str:
    """Plain-text alternative."""
    deadline_line = (
        f"Don't forget — all predictions must be submitted before\n"
        f"{deadline_display}.\n"
        "\n"
        if deadline_display
        else ""
    )
    return (
        "Your entry is back in draft.\n"
        "\n"
        f"Hi {player_name}, you've unlocked your entry\n"
        f'"{entry_name}" (Ref: {entry_ref}). It is now in draft form\n'
        "and won't count toward scoring until you submit it again.\n"
        "\n"
        f"{deadline_line}"
        "Go to your entry:\n"
        f"{deep_link_url}\n"
        "\n"
        "This mailbox is not monitored — please don't reply to this email.\n"
        "\n"
        "— Atlas World Cup 2026 Pools\n"
    )


# ── Recap rendering (monospace receipt-style group/knockout/bonus block) ─────


def _build_recap_html(recap: dict) -> str:
    """Render the recap block as a single <tr><td> of receipt-style HTML.

    Monospace, no shading, no colours beyond muted secondary text. Slots
    in between the disclaimer paragraph and the CTA button of the
    submission confirmation email.
    """
    inner = (
        _render_group_stage_html(recap.get("groups") or [])
        + _render_knockout_html(recap.get("knockout") or [], recap.get("champion"))
        + _render_bonus_html(recap.get("bonus") or [])
    )
    if not inner:
        return ""
    return (
        '          <tr>\n'
        f'            <td style="padding:8px 32px 24px 32px;border-top:1px solid #E2E8F0;">\n'
        f'{inner}'
        '            </td>\n'
        '          </tr>\n'
    )


def _section_header_html(title: str, tag: str | None = None) -> str:
    """Section header — uppercase label-left, optional right-tag."""
    right = (
        f'<td align="right" style="font-family:{_BODY_FONT};font-size:11px;'
        f'color:{_MUTED_INK};">{tag}</td>'
        if tag
        else "<td></td>"
    )
    return (
        '              <table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin-top:18px;margin-bottom:6px;">\n'
        '                <tr>\n'
        f'                  <td style="font-family:{_BODY_FONT};font-size:11px;'
        f'font-weight:700;letter-spacing:0.10em;text-transform:uppercase;color:{_NAVY};">'
        f'{title}</td>\n'
        f'                  {right}\n'
        '                </tr>\n'
        '              </table>\n'
    )


def _render_group_stage_html(groups: list[dict]) -> str:
    if not groups:
        return ""
    n_matches = sum(len(g.get("fixtures") or []) for g in groups)
    parts = [_section_header_html("Group stage", f"{n_matches} matches")]
    for group in groups:
        parts.append(_render_group_block_html(group))
    return "".join(parts)


def _render_group_block_html(group: dict) -> str:
    letter = group.get("letter", "")
    fixtures = list(group.get("fixtures") or [])
    half = (len(fixtures) + 1) // 2
    col1 = fixtures[:half]
    col2 = fixtures[half:]
    return (
        f'              <div style="font-family:{_MONO_FONT};font-size:10px;'
        f'font-weight:700;color:{_MUTED_INK};letter-spacing:0.08em;'
        f'padding-top:10px;padding-bottom:2px;">GROUP {letter}</div>\n'
        '              <table width="100%" cellpadding="0" cellspacing="0" border="0">\n'
        '                <tr>\n'
        '                  <td width="50%" valign="top" style="padding-right:6px;">\n'
        + "".join(_render_fixture_row_html(f) for f in col1)
        + '                  </td>\n'
        '                  <td width="50%" valign="top" style="padding-left:6px;">\n'
        + "".join(_render_fixture_row_html(f) for f in col2)
        + '                  </td>\n'
        '                </tr>\n'
        '              </table>\n'
    )


def _render_fixture_row_html(fixture: dict) -> str:
    home = display_team_name(fixture.get("home"))
    away = display_team_name(fixture.get("away"))
    h_score = int(fixture.get("home_score", 0))
    a_score = int(fixture.get("away_score", 0))
    if h_score > a_score:
        home_text, away_text = f"<b><u>{home}</u></b>", away
    elif a_score > h_score:
        home_text, away_text = home, f"<b><u>{away}</u></b>"
    else:
        home_text, away_text = home, away
    return (
        '                    <table width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="font-family:{_MONO_FONT};font-size:11px;color:{_BODY_INK};">\n'
        '                      <tr>\n'
        '                        <td width="42%" align="right" '
        f'style="padding:1px 4px 1px 0;">{home_text}</td>\n'
        '                        <td width="16%" align="center" '
        f'style="padding:1px 0;white-space:nowrap;">{h_score} - {a_score}</td>\n'
        '                        <td width="42%" align="left" '
        f'style="padding:1px 0 1px 4px;">{away_text}</td>\n'
        '                      </tr>\n'
        '                    </table>\n'
    )


def _render_knockout_html(rounds: list[dict], champion: str | None) -> str:
    if not rounds and not champion:
        return ""
    parts = [_section_header_html("Knockout stage")]
    for r in rounds:
        teams = [display_team_name(t) for t in (r.get("teams") or [])]
        parts.append(
            '              <table width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="margin-top:8px;">\n'
            '                <tr>\n'
            f'                  <td style="font-family:{_MONO_FONT};font-size:11px;'
            f'font-weight:700;color:{_NAVY};letter-spacing:0.05em;">'
            f'{r.get("label", "")}</td>\n'
            f'                  <td align="right" style="font-family:{_MONO_FONT};'
            f'font-size:10px;color:{_MUTED_INK};">{len(teams)} teams</td>\n'
            '                </tr>\n'
            '                <tr>\n'
            f'                  <td colspan="2" style="font-family:{_MONO_FONT};'
            f'font-size:11px;color:{_BODY_INK};line-height:1.7;padding-top:2px;">'
            f'{"&nbsp; ".join(teams)}</td>\n'
            '                </tr>\n'
            '              </table>\n'
        )
    if champion:
        parts.append(
            '              <div style="margin-top:14px;">\n'
            f'                <div style="font-family:{_BODY_FONT};font-size:10px;'
            f'letter-spacing:0.10em;color:{_MUTED_INK};text-transform:uppercase;">'
            'Champion</div>\n'
            f'                <div style="font-family:{_MONO_FONT};font-size:16px;'
            f'font-weight:700;color:{_NAVY};padding-top:2px;">'
            f'{display_team_name(champion)}</div>\n'
            '              </div>\n'
        )
    return "".join(parts)


def _render_bonus_html(bonus: list[dict]) -> str:
    if not bonus:
        return ""
    parts = [_section_header_html("Bonus questions")]
    parts.append(
        '              <table width="100%" cellpadding="0" cellspacing="0" border="0">\n'
    )
    for idx, b in enumerate(bonus, start=1):
        parts.append(
            '                <tr>\n'
            f'                  <td style="font-family:{_MONO_FONT};font-size:11px;'
            f'color:{_BODY_INK};padding:3px 8px 3px 0;vertical-align:top;">'
            f'{idx}. {b.get("question_label", "")}</td>\n'
            f'                  <td align="right" style="font-family:{_MONO_FONT};'
            f'font-size:11px;font-weight:700;color:{_NAVY};padding:3px 0;'
            'white-space:nowrap;vertical-align:top;">'
            f'{display_team_name(b.get("answer"))}</td>\n'
            '                </tr>\n'
        )
    parts.append('              </table>\n')
    return "".join(parts)


def _build_recap_text(recap: dict) -> str:
    """Plain-text equivalent of the recap section (no fancy alignment)."""
    parts: list[str] = []
    groups = recap.get("groups") or []
    if groups:
        n_matches = sum(len(g.get("fixtures") or []) for g in groups)
        parts.append(f"\n\nGROUP STAGE   {n_matches} matches\n")
        for group in groups:
            parts.append(f"\nGROUP {group.get('letter', '')}\n")
            for f in group.get("fixtures") or []:
                home = display_team_name(f.get("home"))
                away = display_team_name(f.get("away"))
                parts.append(
                    f"  {home:>12s}  {int(f.get('home_score', 0))} - "
                    f"{int(f.get('away_score', 0))}  {away}\n"
                )

    rounds = recap.get("knockout") or []
    champion = recap.get("champion")
    if rounds or champion:
        parts.append("\n\nKNOCKOUT STAGE\n")
        for r in rounds:
            teams = [display_team_name(t) for t in (r.get("teams") or [])]
            parts.append(
                f"\n{r.get('label', '')}   ({len(teams)} teams)\n"
                f"  {'  '.join(teams)}\n"
            )
        if champion:
            parts.append(f"\nCHAMPION\n  {display_team_name(champion)}\n")

    bonus = recap.get("bonus") or []
    if bonus:
        parts.append("\n\nBONUS QUESTIONS\n")
        for idx, b in enumerate(bonus, start=1):
            parts.append(
                f"  {idx}. {b.get('question_label', '')}\n"
                f"     → {display_team_name(b.get('answer'))}\n"
            )

    return "".join(parts) if parts else ""


# ── Broadcast nudge emails (v2.160.0) ────────────────────────────────────────


@dataclass(frozen=True)
class _BroadcastContent:
    """Per-segment copy bundle. Subject/headline/CTA differ per segment;
    the chrome (navy/gold header, footer) is shared via the builders below."""

    subject: str
    headline: str
    # Pre-rendered HTML paragraphs for the body. Inline only — no
    # external CSS, no relative URLs, no untrusted-user content (the
    # caller does not pass through any user-controlled text into the
    # HTML beyond the salutation name, which we HTML-escape on insert).
    body_html: str
    body_text: str
    cta_label: str


def _format_deadline_malta(dt: datetime | None) -> str | None:
    """Render a deadline as '11 Jun 2026, 7:00 PM Malta Time'.

    Used by broadcast segments that prefer a localised, human-friendly
    timestamp over the bare UTC one. Returns None if no deadline is set.
    """
    if dt is None:
        return None
    local = dt.astimezone(ZoneInfo("Europe/Malta"))
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    # Portable day-of-month (no leading zero) — %-d / %#d differ by platform.
    day = str(local.day)
    return f"{day} {local.strftime('%b %Y')}, {hour12}:{local.minute:02d} {ampm} Malta Time"


def _broadcast_content_for_segment(
    segment: BroadcastSegment,
    *,
    player_name: str,
    deadline_display: str | None,
    deadline_dt: datetime | None = None,
) -> _BroadcastContent:
    """Branch on segment → return per-segment copy.

    All three segments share: salutation name, deadline phrasing,
    "go to entries" CTA. Only the headline, body paragraphs, and
    subject differ.
    """
    safe_name = (player_name or "there").replace("<", "&lt;").replace(">", "&gt;")
    deadline_phrase_html = (
        f"before <strong>{deadline_display}</strong>"
        if deadline_display
        else "before the deadline"
    )
    deadline_phrase_text = (
        f"before {deadline_display}" if deadline_display else "before the deadline"
    )

    if segment == BroadcastSegment.SUBMITTERS:
        return _BroadcastContent(
            subject="Thanks for entering — want to add another?",
            headline="Thanks for entering.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, your World Cup 2026 entry is locked in — "
                "we appreciate you taking part.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "If you fancy adding another set of predictions, you can create "
                f"additional entries {deadline_phrase_html}. Different teams, "
                "different picks, more chances to win.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "If any of your entries are still in draft, remember those "
                "don't count toward scoring until you submit them — give "
                "them a once-over and lock them in.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "One small heads-up: we've tightened the wording on the "
                "<strong>Bottlers</strong> bonus question — it now reads "
                '<em>&ldquo;team inside FIFA top 10 eliminated earliest, '
                'including not making it to the knockout stage.&rdquo;</em> '
                "You can edit any submitted entry right up to the deadline "
                "if you'd like to revisit that pick (or any other).</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, your World Cup 2026 entry is locked in — "
                "we appreciate you taking part.\n"
                "\n"
                "If you fancy adding another set of predictions, you can create\n"
                f"additional entries {deadline_phrase_text}. Different teams,\n"
                "different picks, more chances to win.\n"
                "\n"
                "If any of your entries are still in draft, remember those\n"
                "don't count toward scoring until you submit them — give\n"
                "them a once-over and lock them in.\n"
                "\n"
                "One small heads-up: we've tightened the wording on the\n"
                "Bottlers bonus question — it now reads:\n"
                '"team inside FIFA top 10 eliminated earliest, including\n'
                'not making it to the knockout stage."\n'
                "\n"
                "You can edit any submitted entry right up to the deadline\n"
                "if you'd like to revisit that pick (or any other).\n"
            ),
            cta_label="Add another entry",
        )

    if segment == BroadcastSegment.NO_ENTRY:
        # This is the LAST nudge for sign-ups who haven't started — copy
        # leans on Malta-time phrasing, the live prize pot, and a hard
        # "no more reminders" line so the recipient knows it's their
        # final ping.
        malta_phrase = _format_deadline_malta(deadline_dt) or deadline_display
        no_entry_html = (
            f"before <strong>{malta_phrase}</strong>"
            if malta_phrase
            else "before the deadline"
        )
        no_entry_text = (
            f"before {malta_phrase}" if malta_phrase else "before the deadline"
        )
        return _BroadcastContent(
            subject="Atlas World Cup 2026 Pools | Last few hours to submit an entry",
            headline="Don't miss out on World Cup 2026.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, you signed up for the World Cup 2026 prediction "
                "pool but haven't made your picks yet.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"The deadline to enter is {no_entry_html}. It takes about "
                "ten minutes to fill in your group-stage predictions, bracket, and "
                "bonus answers — and you only need to do it once.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "The prize fund currently stands close to "
                "<strong>&euro;800</strong>.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "This is the last reminder you will receive.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, you signed up for the World Cup 2026 prediction\n"
                "pool but haven't made your picks yet.\n"
                "\n"
                f"The deadline to enter is {no_entry_text}. It takes about\n"
                "ten minutes to fill in your group-stage predictions, bracket, and\n"
                "bonus answers — and you only need to do it once.\n"
                "\n"
                "The prize fund currently stands close to €800.\n"
                "\n"
                "This is the last reminder you will receive.\n"
            ),
            cta_label="Make my picks",
        )

    if segment == BroadcastSegment.DRAFT_HOLDERS:
        # Last nudge for people who started but never hit Submit — same
        # Malta-time / prize-pot / last-reminder treatment as NO_ENTRY,
        # since both segments are essentially "haven't qualified yet,
        # deadline looming".
        malta_phrase = _format_deadline_malta(deadline_dt) or deadline_display
        draft_html = (
            f"before <strong>{malta_phrase}</strong>"
            if malta_phrase
            else "before the deadline"
        )
        draft_text = (
            f"before {malta_phrase}" if malta_phrase else "before the deadline"
        )
        return _BroadcastContent(
            subject="Atlas World Cup 2026 Pools | Submit your entry before the deadline",
            headline="Don't forget to submit.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, you've started a World Cup 2026 entry but "
                "haven't submitted it yet.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Draft entries don't count toward scoring</strong> — "
                f"you need to submit {draft_html} for your picks to qualify. "
                "Hop in, review your predictions, and hit Submit.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "The prize fund currently stands close to "
                "<strong>&euro;800</strong>.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "This is the last reminder you will receive.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, you've started a World Cup 2026 entry but\n"
                "haven't submitted it yet.\n"
                "\n"
                "Draft entries don't count toward scoring — you need to submit\n"
                f"{draft_text} for your picks to qualify. Hop in,\n"
                "review your predictions, and hit Submit.\n"
                "\n"
                "The prize fund currently stands close to €800.\n"
                "\n"
                "This is the last reminder you will receive.\n"
            ),
            cta_label="Submit my picks",
        )

    if segment == BroadcastSegment.POOL_GHOST:
        # v2.176.0 — re-engagement nudge for users who submitted an
        # eligible entry pre-deadline but haven't returned to the site
        # since the tournament kicked off. Friendly, not accusatory:
        # the cohort definition has a small false-positive rate (a
        # holidaying user with persistent session) and the copy keeps
        # that recoverable.
        return _BroadcastContent(
            subject="Atlas World Cup 2026 Pools | Your picks are still alive",
            headline="Your World Cup picks are still alive.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, the tournament kicked off and your entry "
                "is in the pool — but we haven't seen you back on the site "
                "since the deadline.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Group-stage matches are playing out daily and the leaderboard "
                "is already shifting. Come take a look at how your picks are "
                "doing.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "Already been back recently? You can safely ignore this — "
                "this nudge sometimes catches users with browser blockers.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, the tournament kicked off and your entry\n"
                "is in the pool — but we haven't seen you back on the site\n"
                "since the deadline.\n"
                "\n"
                "Group-stage matches are playing out daily and the leaderboard\n"
                "is already shifting. Come take a look at how your picks are\n"
                "doing.\n"
                "\n"
                "Already been back recently? You can safely ignore this —\n"
                "this nudge sometimes catches users with browser blockers.\n"
            ),
            cta_label="See how I'm doing",
        )

    if segment == BroadcastSegment.GROUP_R1_RECAP:
        # v2.178.0 — one-off round-recap nudge sent the morning Round 1
        # concludes. Same audience as SUBMITTERS (everyone with a
        # submitted entry); copy thanks them, points at the live
        # standings + the read-only Google Sheet, and spells out the
        # prize breakdown. Plain-text deliberately omits the raw
        # spreadsheet URL — recipients are routed to the in-app
        # "View All Entries" button instead (which carries the link
        # behind a clickable button).
        return _BroadcastContent(
            subject=(
                "World Cup 2026 | Round 1 wraps tomorrow — your "
                "standings are live"
            ),
            headline="Round 1 wraps tomorrow — standings are live.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, thanks for being part of the Atlas "
                "World Cup 2026 pool &mdash; the first round of "
                "group-stage fixtures wraps up tomorrow morning, and "
                "scoring is live.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Follow your standings &rarr;</strong> "
                '<a href="https://wc26.heyvinay.com/?utm_source=email'
                '&amp;utm_campaign=group_r1_recap" style="color:'
                f'{_GOLD};text-decoration:underline;">wc26.heyvinay.com'
                "</a><br>Scores and standings update immediately after "
                "each match. The leaderboard refreshes live, every "
                "Match Detail page explains its rarity bonus (why some "
                "picks earn extra), and the insights cards surface "
                "trends across the pool.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>See everyone&rsquo;s picks &rarr;</strong> "
                '<a href="https://docs.google.com/spreadsheets/d/'
                '1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y/preview" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "View the full entries sheet</a><br>"
                "A read-only mirror of every entry, every pick, every "
                "score &mdash; updated after each fixture. You can "
                "also reach it from the <em>View All Entries</em> "
                "button at the top of the Leaderboard page.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Prize breakdown</strong><br>"
                "Together we collected over <strong>&euro;900</strong>. "
                "Here&rsquo;s how the pot splits:</p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>&#127942; <strong>Overall "
                "Winner</strong> (after the Finals) &mdash; "
                "&euro;595</li>\n"
                "                <li>&#127941; <strong>Group Stage "
                "Winner</strong> &mdash; &euro;183</li>\n"
                "                <li>&#10084;&#65039; <strong>Soup "
                "Kitchen donation</strong> &mdash; &euro;150</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "A huge thank-you to <strong>Atlas Insurance</strong>, "
                "who have generously <strong>topped up the Soup "
                "Kitchen donation with an additional &euro;500</strong> "
                "&mdash; bringing the total charitable contribution to "
                "<strong>&euro;650</strong>.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "Hit a problem or have a question? Use the "
                "<strong>Help &amp; Support</strong> panel on any page "
                "&mdash; it routes straight to us.</p>\n"
                f'              <p style="margin:0 0 0 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">Good luck for Round 2.</p>\n'
            ),
            body_text=(
                f"Hi {safe_name}, thanks for being part of the Atlas "
                "World Cup 2026 pool —\n"
                "the first round of group-stage fixtures wraps up "
                "tomorrow morning,\n"
                "and scoring is live.\n"
                "\n"
                "FOLLOW YOUR STANDINGS\n"
                "https://wc26.heyvinay.com/"
                "?utm_source=email&utm_campaign=group_r1_recap\n"
                "\n"
                "Scores and standings update immediately after each "
                "match. The\n"
                "leaderboard refreshes live, every Match Detail page "
                "explains its\n"
                "rarity bonus, and the insights cards surface trends "
                "across the pool.\n"
                "\n"
                "SEE EVERYONE'S PICKS\n"
                "Open the Leaderboard page and click the "
                '"View All Entries" button at\n'
                "the top — it opens a read-only sheet that mirrors "
                "every entry, every\n"
                "pick, every score, updated after each fixture.\n"
                "\n"
                "PRIZE BREAKDOWN\n"
                "Together we collected over €900. Here's how the pot "
                "splits:\n"
                "\n"
                "  🥇 Overall Winner (after the Finals) — €595\n"
                "  🏅 Group Stage Winner                — €183\n"
                "  ❤️ Soup Kitchen donation             — €150\n"
                "\n"
                "A huge thank-you to Atlas Insurance, who have "
                "generously topped up\n"
                "the Soup Kitchen donation with an additional €500 — "
                "bringing the\n"
                "total charitable contribution to €650.\n"
                "\n"
                "Hit a problem or have a question? Use the Help & "
                "Support panel on\n"
                "any page — it routes straight to us.\n"
                "\n"
                "Good luck for Round 2.\n"
            ),
            cta_label="Open my standings",
        )

    if segment == BroadcastSegment.GROUP_R2_RECAP:
        # v2.180.0 — Round 2 recap (one-off). Sent the morning Round 2
        # wraps, ahead of Round 3 finale on Sunday 28 June.
        #
        # Spam-filter notes (R1 hit Gmail's promotional bin; R2 tuned to
        # avoid the same fate):
        # * URLs carry NO utm_* query parameters (R1 used them and that
        #   compounded with money/winner phrasing pushed score over the
        #   threshold). Trade-off: PostHog can no longer attribute
        #   click-throughs per round — acceptable because deliverability
        #   matters more than analytics here.
        # * Avoided word pairs that co-trigger SpamAssassin rules:
        #     "winner" + "announced", "prize" + "paid", "prize" +
        #     "awarded", money symbol next to "leader". Replaced with
        #     neutral "standings" language.
        # * Plain-text section dividers use sentence-case ("Leaderboard
        #   highlights") rather than ALL CAPS, which is a multi-word
        #   ALL-CAPS signal.
        return _BroadcastContent(
            subject="Round 2 wrap-up — Sunday closes the group stage",
            headline="Round 2 is done — Sunday closes the group stage.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, all of Round 2 has been settled and "
                "scored. <strong>Round 3 wraps on Sunday 28 June</strong> "
                "&mdash; the final round of group-stage fixtures &mdash; "
                "and we&rsquo;ll <strong>share the final group-stage "
                "standings that same day</strong> once we&rsquo;ve "
                "finished checking every point.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Leaderboard highlights</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>&#127942; <strong>Top of the "
                "pile:</strong> {{TOP_1}}</li>\n"
                "                <li>&#127941; <strong>Hot on their "
                "heels:</strong> {{TOP_2_WITH_GAP}}</li>\n"
                "                <li>&#129351; <strong>Three to "
                "watch:</strong> {{TOP_3_TO_5}}</li>\n"
                "                <li>&#127942; <strong>Round 2 "
                "standout:</strong> {{R2_HERO}}</li>\n"
                "                <li>&#128640; <strong>Biggest "
                "climb this round:</strong> {{CLIMBERS}}</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Follow your standings &rarr;</strong> "
                '<a href="https://wc26.heyvinay.com/leaderboard" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "wc26.heyvinay.com/leaderboard</a><br>"
                "The leaderboard refreshes live, every Match Detail "
                "page explains its scoring, and the Race tab shows "
                "your trajectory against the rest of the pool.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Sunday 28 &mdash; what happens</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>All Round 3 fixtures complete in "
                "the morning</li>\n"
                "                <li>We re-run scoring end-to-end and "
                "verify every match</li>\n"
                "                <li>Final group-stage standings are "
                "confirmed and the top entry is notified</li>\n"
                "                <li>Knockout-stage scoring begins "
                "immediately with the Round of 32</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "Every fixture is scored twice &mdash; once live from "
                "the official feed, once verified by hand before the "
                "standings are confirmed. If anything looks off, the "
                "<strong>Help &amp; Support</strong> panel on any page "
                "routes straight to us.</p>\n"
                f'              <p style="margin:0 0 0 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">Good luck for the final '
                "round.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, all of Round 2 has been settled and "
                "scored.\n"
                "\n"
                "Round 3 wraps on Sunday 28 June — the final round of "
                "group-stage\n"
                "fixtures — and we'll share the final group-stage "
                "standings that same\n"
                "day, once we've finished checking every point.\n"
                "\n"
                "Leaderboard highlights\n"
                "  🥇 Top of the pile:        {{TOP_1}}\n"
                "  🥈 Hot on their heels:     {{TOP_2_WITH_GAP}}\n"
                "  🥉 Three to watch:         {{TOP_3_TO_5}}\n"
                "  🏆 Round 2 standout:       {{R2_HERO}}\n"
                "  🚀 Biggest climb:          {{CLIMBERS}}\n"
                "\n"
                "Follow your standings\n"
                "https://wc26.heyvinay.com/leaderboard\n"
                "\n"
                "Sunday 28 — what happens\n"
                "  • All Round 3 fixtures complete in the morning\n"
                "  • We re-run scoring end-to-end and verify every "
                "match\n"
                "  • Final group-stage standings are confirmed and "
                "the top\n"
                "    entry is notified\n"
                "  • Knockout-stage scoring begins immediately with "
                "the Round of 32\n"
                "\n"
                "Every fixture is scored twice — once live from the "
                "official feed,\n"
                "once verified by hand before the standings are "
                "confirmed. If anything\n"
                "looks off, the Help & Support panel on any page "
                "routes straight to us.\n"
                "\n"
                "Good luck for the final round.\n"
            ),
            cta_label="Open my standings",
        )

    if segment == BroadcastSegment.GROUP_STAGE_FINAL:
        # v2.181.0 — Group stage champion announcement. Released
        # Sunday 28 June 2026 ~7pm Malta time, after R3 settles and
        # the admin flips Competition.group_stage_winner_released.
        # The body has token placeholders ({{WINNER_NAME}}, {{TOTAL_POINTS}},
        # {{OUTCOME_PTS}}, {{EXACT_EXTRA}}, {{RARITY_EXTRA}}, {{BONUS_PTS}},
        # {{STORY_LINE}}, {{WINNER_FIRST_NAME}}) that the
        # _compute_group_stage_winner_email_tokens helper fills in at
        # send time from the same service that backs the dashboard card —
        # card and email agree to the point.
        #
        # Spam-filter rules (same as R2):
        #   * no UTM tags on the CTA URL
        #   * no "winner+announced", "prize+paid", "prize+awarded" pairs
        #   * sentence-case headers in plaintext body
        return _BroadcastContent(
            subject="Group stage closes — final standings inside",
            headline="Group stage closes — final standings are in.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, the group stage of the Atlas World Cup "
                "2026 pool has wrapped. Final standings have been "
                "verified and the pool&rsquo;s group-stage champion is "
                "locked in.</p>\n"
                f'              <div style="margin:0 0 18px 0;padding:18px;'
                f'background:#1C2541;border:1px solid #D4AF37;'
                f'border-radius:14px;text-align:center;">'
                f'<div style="font-size:11px;font-weight:700;'
                f'letter-spacing:0.14em;text-transform:uppercase;'
                f'color:{_GOLD};margin-bottom:6px;">'
                "&#127942; Group stage champion</div>"
                f'<div style="font-size:24px;font-weight:800;'
                f'color:#FFFFFF;line-height:1.2;">'
                "{{WINNER_NAME}}</div>"
                f'<div style="font-size:14px;color:#94A3B8;'
                f'margin-top:2px;">'
                "{{ENTRY_NAME}}</div>"
                f'<div style="font-size:20px;font-weight:700;'
                f'color:{_GOLD};margin-top:10px;">'
                "{{TOTAL_POINTS}} points</div>"
                "</div>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Points breakdown</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>Points from correct match outcomes: "
                "<strong>{{OUTCOME_PTS}}</strong></li>\n"
                "                <li>Extra points from exact scores: "
                "<strong>{{EXACT_EXTRA}}</strong></li>\n"
                "                <li>Extra points from rarity: "
                "<strong>{{RARITY_EXTRA}}</strong></li>\n"
                "                <li>Points from bonus questions: "
                "<strong>{{BONUS_PTS}}</strong></li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>How they got there</strong><br>"
                "{{STORY_LINE}}</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "{{WINNER_FIRST_NAME}} takes home <strong>&euro;183</strong> "
                "from the pool.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>What&rsquo;s next?</strong><br>"
                "The knockout stage begins shortly. Brackets compete "
                "for the Overall Winner prize of <strong>&euro;595</strong>. "
                "The leaderboard restarts the drama from the Round of "
                "32 onward &mdash; an entry can win the group stage and "
                "still be overtaken in the bracket.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Follow your standings &rarr;</strong> "
                '<a href="https://wc26.heyvinay.com/leaderboard" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "wc26.heyvinay.com/leaderboard</a></p>\n"
                f'              <p style="margin:0 0 0 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "Final standings independently audited against four "
                "immutable sources. Thanks for being part of the pool.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, the group stage of the Atlas World "
                "Cup 2026 pool has wrapped.\n"
                "Final standings have been verified and the pool's "
                "group-stage champion\n"
                "is locked in.\n"
                "\n"
                "🏆 GROUP STAGE CHAMPION\n"
                "\n"
                "{{WINNER_NAME}}\n"
                "{{ENTRY_NAME}}\n"
                "{{TOTAL_POINTS}} points\n"
                "\n"
                "Points breakdown\n"
                "  • Points from correct match outcomes: {{OUTCOME_PTS}}\n"
                "  • Extra points from exact scores:  {{EXACT_EXTRA}}\n"
                "  • Extra points from rarity:        {{RARITY_EXTRA}}\n"
                "  • Points from bonus questions:     {{BONUS_PTS}}\n"
                "\n"
                "How they got there\n"
                "{{STORY_LINE}}\n"
                "\n"
                "{{WINNER_FIRST_NAME}} takes home €183 from the pool.\n"
                "\n"
                "What's next?\n"
                "The knockout stage begins shortly. Brackets compete "
                "for the Overall\n"
                "Winner prize of €595. The leaderboard restarts the "
                "drama from the\n"
                "Round of 32 onward — an entry can win the group stage "
                "and still be\n"
                "overtaken in the bracket.\n"
                "\n"
                "Follow your standings\n"
                "https://wc26.heyvinay.com/leaderboard\n"
                "\n"
                "Final standings independently audited against four "
                "immutable sources. Thanks for being part of the pool.\n"
            ),
            cta_label="Open my standings",
        )

    if segment == BroadcastSegment.GROUP_R32_RECAP:
        # v2.195.0 — Round of 32 knockout recap (one-off). Sent the
        # morning after the R32 wrapped, ahead of the Round of 16.
        #
        # Unlike R2/GSF this body has NO dynamic {{tokens}} — the results
        # and the standings are an admin-approved point-in-time snapshot,
        # baked straight into the copy, so there's no send-time compute
        # and nothing to interpolate. The only variable is the salutation
        # name (f-string, HTML-escaped above).
        #
        # Spam-filter rules (same as R2/GSF): the CTA carries NO utm_*
        # params (see _deep_link_for_segment), and the copy avoids the
        # "winner+announced" / "prize+awarded" word pairs. National-flag
        # emoji are deliberately omitted — they degrade to two-letter
        # country codes in Outlook/Windows mail; only broadly-supported
        # pictographs (&#128680; siren, &#128302; crystal ball, etc.)
        # are used, matching the R2 body's convention.
        return _BroadcastContent(
            subject="The Round of 32 is done — and Germany aren't the only ones going home",
            headline="The Round of 32 is done — and the table has moved.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, what a week. Thirty-two matches, sixteen "
                "teams sent home, penalty shootouts, extra-time swings and "
                "stoppage-time winners &mdash; the Round of 32 had the lot. "
                "We&rsquo;ve also just launched a <strong>What-if Bracket "
                "Simulator</strong> so you can play out the rest of the "
                "knockouts yourself (more on that below). First, here&rsquo;s "
                "how it played out.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>The games everyone was talking about</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>&#128680; <strong>Germany are "
                "out</strong> &mdash; beaten by <strong>Paraguay on "
                "penalties</strong>, the first true heavyweight to fall.</li>\n"
                "                <li><strong>Netherlands out too</strong> "
                "&mdash; held <strong>1-1 by Morocco</strong>, then knocked "
                "out <strong>3-2 on penalties</strong>.</li>\n"
                "                <li><strong>The fairytale that nearly "
                "happened</strong> &mdash; <strong>Cape Verde</strong> twice "
                "clawed back before losing <strong>3-2 to Argentina in extra "
                "time</strong>.</li>\n"
                "                <li><strong>Brazil got a scare</strong> "
                "&mdash; <strong>Japan</strong> led 1-0 before a Martinelli "
                "stoppage-time winner, <strong>2-1</strong>.</li>\n"
                "                <li><strong>Portugal 2-1 Croatia</strong> "
                "&mdash; a Euro 2016 final rematch settled by a Ramos goal "
                "deep in stoppage time.</li>\n"
                "                <li><strong>Belgium 3-2 Senegal</strong> "
                "after extra time &mdash; a controversial late penalty ended "
                "Senegal&rsquo;s run.</li>\n"
                "                <li><strong>Egypt</strong> knocked out "
                "<strong>Australia</strong> on penalties (4-2).</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "A couple of history-makers, too: <strong>Canada</strong> "
                "claimed the first knockout win in their history, and the "
                "<strong>USA</strong> saw off Bosnia. Elsewhere, "
                "<strong>France put three past Sweden</strong> (Mbapp&eacute; "
                "with a brace), <strong>Spain</strong> eased past Austria, "
                "<strong>Norway</strong> edged Ivory Coast with Haaland on "
                "the scoresheet, and <strong>Colombia</strong> saw off "
                "Ghana.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>The table has a new name on top</strong></p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Lionel Zammit</strong> has climbed into first on "
                "<strong>1,301 points</strong>. <strong>Glenn "
                "Debattista</strong> and <strong>Jacques Ellul Soler</strong> "
                "are locked together on <strong>1,283</strong>, with "
                "<strong>Kurt Dylan Buttigieg</strong> (1,281) and "
                "<strong>Jeffrey Formosa</strong> (1,278) right behind. Just "
                "<strong>34 points separate 1st from 10th</strong> &mdash; "
                "this is anyone&rsquo;s to take. Special mention to "
                "<strong>Rhoda Maughan</strong>, up 17 places into the top "
                "six on the back of the knockouts.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>See where you stand &rarr;</strong> "
                '<a href="https://wc26.heyvinay.com/leaderboard" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "wc26.heyvinay.com/leaderboard</a></p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>New this week &mdash; play out the rest "
                "yourself</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>&#128302; <strong>The What-if Bracket "
                "Simulator.</strong> Head to the Results page, pick the "
                "winners of the remaining knockout matches, and watch the "
                "whole pool re-rank under <em>your</em> scenario. You unlock "
                "it by beating a short football-trivia challenge, then get "
                "two runs a day &mdash; so choose your scenarios wisely.</li>\n"
                "                <li>&#128202; <strong>Group Standings "
                "reality-check.</strong> The Standings tab now shows your "
                "picked qualifiers against the live tables at a glance "
                "&mdash; which are locked in, which slipped, and how your "
                "predicted bracket has shifted. Your Dark Horse and Bottlers "
                "picks get live status cards too.</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>The last 16 is here</strong></p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Sixteen teams left, no more second chances, and every "
                "remaining knockout point on the line &mdash; and with the "
                "table this tight, one good round could vault you up it. "
                "Paraguay&ndash;France, Canada&ndash;Morocco, "
                "Brazil&ndash;Norway and Mexico&ndash;England are already on "
                "the schedule. Give your predictions one more look, fire up "
                "the simulator to see what you&rsquo;re playing for &mdash; "
                "and good luck. It gets serious from here.</p>\n"
                f'              <p style="margin:0 0 0 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">See you at the top of the '
                "table.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, what a week. Thirty-two matches, sixteen "
                "teams sent\n"
                "home, penalty shootouts, extra-time swings and "
                "stoppage-time winners\n"
                "— the Round of 32 had the lot. We've also just launched a "
                "What-if\n"
                "Bracket Simulator so you can play out the rest of the "
                "knockouts\n"
                "yourself (more on that below). First, here's how it played "
                "out.\n"
                "\n"
                "The games everyone was talking about\n"
                "  🚨 Germany are out — beaten by Paraguay on penalties, the "
                "first\n"
                "     true heavyweight to fall.\n"
                "  • Netherlands out too — 1-1 with Morocco, knocked out 3-2 "
                "on penalties.\n"
                "  • The fairytale that nearly happened — Cape Verde twice "
                "clawed back\n"
                "     before losing 3-2 to Argentina in extra time.\n"
                "  • Brazil got a scare — Japan led 1-0 before a Martinelli "
                "stoppage-time\n"
                "     winner, 2-1.\n"
                "  • Portugal 2-1 Croatia — a Euro 2016 final rematch settled "
                "by a Ramos\n"
                "     goal deep in stoppage time.\n"
                "  • Belgium 3-2 Senegal after extra time — a controversial "
                "late penalty\n"
                "     ended Senegal's run.\n"
                "  • Egypt knocked out Australia on penalties (4-2).\n"
                "\n"
                "History-makers, too: Canada claimed the first knockout win "
                "in their\n"
                "history, and the USA saw off Bosnia. Elsewhere, France put "
                "three past\n"
                "Sweden (Mbappé with a brace), Spain eased past Austria, "
                "Norway edged\n"
                "Ivory Coast with Haaland on the scoresheet, and Colombia "
                "saw off Ghana.\n"
                "\n"
                "The table has a new name on top\n"
                "Lionel Zammit has climbed into first on 1,301 points. Glenn "
                "Debattista\n"
                "and Jacques Ellul Soler are locked together on 1,283, with "
                "Kurt Dylan\n"
                "Buttigieg (1,281) and Jeffrey Formosa (1,278) right behind. "
                "Just 34\n"
                "points separate 1st from 10th — this is anyone's to take. "
                "Special\n"
                "mention to Rhoda Maughan, up 17 places into the top six.\n"
                "\n"
                "See where you stand\n"
                "https://wc26.heyvinay.com/leaderboard\n"
                "\n"
                "New this week — play out the rest yourself\n"
                "  🔮 The What-if Bracket Simulator. On the Results page, "
                "pick the\n"
                "     winners of the remaining knockout matches and watch the "
                "whole\n"
                "     pool re-rank under your scenario. Unlock it by beating "
                "a short\n"
                "     football-trivia challenge, then two runs a day.\n"
                "  📊 Group Standings reality-check. The Standings tab now "
                "shows your\n"
                "     picked qualifiers against the live tables; Dark Horse "
                "and Bottlers\n"
                "     picks get live status cards too.\n"
                "\n"
                "The last 16 is here\n"
                "Sixteen teams left, no more second chances, and every "
                "remaining\n"
                "knockout point on the line — and with the table this tight, "
                "one good\n"
                "round could vault you up it. Paraguay–France, "
                "Canada–Morocco,\n"
                "Brazil–Norway and Mexico–England are already on the "
                "schedule. Give\n"
                "your predictions one more look, fire up the simulator, and "
                "good luck.\n"
                "\n"
                "See you at the top of the table.\n"
            ),
            cta_label="See the full table",
        )

    if segment == BroadcastSegment.GROUP_R16_RECAP:
        # v2.209.0 — Round of 16 knockout recap (one-off). Sent the
        # morning after the R16 wrapped, ahead of the quarter-finals.
        #
        # Unlike R32 this body is TOKEN-DRIVEN: standings + round hero
        # + biggest-climb + Bottlers-payout tokens fill in at send time
        # from `_compute_r16_highlights` (see below in this module).
        # Editorial through-line: three co-hosts eliminated (USA,
        # Mexico, Canada); a second wave of heavyweights fell (Brazil,
        # Portugal); Argentina survived a Messi comeback; Norway's run
        # rolls on.
        #
        # Spam-filter rules (same as R2/GSF/R32): the CTA carries NO
        # utm_* params (see _deep_link_for_segment), and the copy
        # avoids the "winner+announced" / "prize+awarded" word pairs.
        # National-flag emoji are deliberately omitted — they degrade
        # in Outlook/Windows mail; only broadly-supported pictographs
        # (&#128680; siren, &#128293; fire, &#128302; crystal ball,
        # &#128202; bar chart, &#127942; trophy) are used.
        #
        # ★ f-string double-brace trap: `{{TOKEN}}` inside an
        # f-string collapses to `{TOKEN}` and `_interpolate` no
        # longer matches. All token placeholders below live inside
        # NON-f string literals. The regression test
        # (test_group_r16_recap_template_tokens_interpolate) catches
        # any regression.
        return _BroadcastContent(
            subject="The Round of 16 is done — the final eight are set",
            headline="Eight down, four to go — and the table has moved.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, the Round of 16 delivered. Three "
                "co-hosts eliminated on home soil. A second wave of "
                "heavyweights sent home. Argentina needed everything "
                "Messi had left to survive. And Norway lit the "
                "internet on fire.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "&#128680; <strong>The games everyone was talking "
                "about</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li><strong>Norway 2&ndash;1 "
                "Brazil.</strong> The shock of the round. Haaland&rsquo;s "
                "Norway dump out a heavyweight &mdash; the second "
                "favourite to fall after Germany went in R32. And the "
                "drum moment is everywhere: Haaland in front of the "
                "away end, striking the bass drum on the beat, the "
                "entire Norwegian section roaring back in unison. "
                "Goosebumps stuff.</li>\n"
                "                <li><strong>Morocco 3&ndash;0 "
                "Canada.</strong> Co-hosts routed. Canada&rsquo;s "
                "historic tournament run ends in the second knockout "
                "round.</li>\n"
                "                <li><strong>Belgium 4&ndash;1 "
                "USA.</strong> Co-hosts blown away. The scoreline "
                "flattered nobody.</li>\n"
                "                <li><strong>England 3&ndash;2 "
                "Mexico.</strong> A thriller. England edge the third "
                "and final co-host in a game that swung three "
                "times.</li>\n"
                "                <li><strong>France 1&ndash;0 "
                "Paraguay.</strong> France grind past the side that "
                "had knocked Germany out. Not pretty. "
                "Effective.</li>\n"
                "                <li><strong>Spain 1&ndash;0 "
                "Portugal.</strong> The Iberian derby to Spain. One "
                "goal decided a game everyone expected to go the "
                "distance.</li>\n"
                "                <li>&#128293; <strong>Argentina "
                "3&ndash;2 Egypt.</strong> The tie of the round. Down "
                "2&ndash;0 with 20 minutes left, Messi turned it on "
                "&mdash; three Argentina goals in fifteen minutes, "
                "Enzo Fern&aacute;ndez the stoppage-time winner.</li>\n"
                "                <li><strong>Switzerland 0&ndash;0 "
                "Colombia</strong> (Switzerland win 4&ndash;3 on "
                "penalties). 120 goalless minutes. The Swiss keep "
                "their nerve from the spot.</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Three of the four North American co-hosts, gone. "
                "Portugal, gone. The bracket has never looked more "
                "open.</p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "&#128202; <strong>Where you stand</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li>&#127942; <strong>Top of the "
                "table:</strong> "
                # Non-f-string literal so `{{TOP_1}}` survives to _interpolate:
                "{{TOP_1}}</li>\n"
                "                <li><strong>Hot on their heels:</strong> "
                "{{TOP_2_WITH_GAP}}</li>\n"
                "                <li><strong>Three to watch:</strong> "
                "{{TOP_3_TO_5}}</li>\n"
                "                <li><strong>Best haul of the "
                "round:</strong> {{R16_HERO}}</li>\n"
                "                <li>&#128640; <strong>Biggest "
                "climb:</strong> {{CLIMBERS}}</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>Bottlers watch:</strong> "
                "{{BOTTLERS_PAID_OUT}}. {{BOTTLERS_SURPRISE}}</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>See where you stand &rarr;</strong> "
                '<a href="https://wc26.heyvinay.com/leaderboard" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "wc26.heyvinay.com/leaderboard</a></p>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "<strong>New this week</strong></p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li><strong>The leaderboard now "
                "moves live during knockout matches.</strong> Standings "
                "re-sort in real time based on who&rsquo;s currently "
                "winning on the pitch, then lock to the real numbers "
                "at full time. Open it during a QF and watch positions "
                "shuffle as goals go in. &rarr; "
                '<a href="https://wc26.heyvinay.com/leaderboard" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "Open the leaderboard</a></li>\n"
                "                <li><strong>Bracket Simulator "
                "upgrade.</strong> The trivia unlock quiz and the "
                "one-run-a-day cap are gone &mdash; run as many "
                "what-if QF/SF/Final scenarios as you like. Projected "
                "pool standings now correctly include your "
                "knockout-stage bonus points too. &rarr; "
                '<a href="https://wc26.heyvinay.com/results?round=bracket" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "Open the Simulator</a></li>\n"
                "                <li><strong>Tap the &#10022; icon in "
                "the nav</strong> for a &ldquo;What&rsquo;s New&rdquo; "
                "panel with everything that&rsquo;s shipped recently "
                "&mdash; and a one-tap way to rate the app and send a "
                "quick note. We read every one.</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 8px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "&#128302; <strong>The final eight</strong> "
                "(all times Malta)</p>\n"
                f'              <ul style="margin:0 0 14px 18px;padding:0;'
                f'font-size:15px;line-height:1.7;color:{_BODY_INK};">'
                "\n                <li><strong>France vs Morocco</strong> "
                "&mdash; Thu 9 Jul, 22:00. Boston. A 2022 semi-final "
                "rematch.</li>\n"
                "                <li><strong>Spain vs Belgium</strong> "
                "&mdash; Fri 10 Jul, 21:00. Los Angeles.</li>\n"
                "                <li><strong>Norway vs England</strong> "
                "&mdash; Sat 11 Jul, 23:00. Miami. Haaland vs "
                "Kane.</li>\n"
                "                <li><strong>Argentina vs "
                "Switzerland</strong> &mdash; Sun 12 Jul, 03:00. "
                "Kansas City.</li>\n"
                "              </ul>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Points-per-match doubles from here on. One correct "
                "QF outcome is worth more than a whole group-stage "
                "matchday. Every scoreline, every bracket pick, every "
                "bonus answer starts to matter twice as much. If "
                "you&rsquo;ve been coasting mid-table, this is where "
                "the table breaks open.</p>\n"
                f'              <p style="margin:0 0 0 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">See you at the top of the '
                "table.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, the Round of 16 delivered. Three "
                "co-hosts\n"
                "eliminated on home soil. A second wave of "
                "heavyweights sent\n"
                "home. Argentina needed everything Messi had left to "
                "survive.\n"
                "And Norway lit the internet on fire.\n"
                "\n"
                "The games everyone was talking about\n"
                "  🚨 Norway 2-1 Brazil — the shock of the round. "
                "Haaland's\n"
                "     Norway dump out a heavyweight — the second "
                "favourite to\n"
                "     fall after Germany went in R32. And the drum "
                "moment is\n"
                "     everywhere: Haaland in front of the away end, "
                "striking\n"
                "     the bass drum on the beat, the entire Norwegian "
                "section\n"
                "     roaring back in unison. Goosebumps stuff.\n"
                "  • Morocco 3-0 Canada — co-hosts routed. Canada's "
                "historic\n"
                "     tournament run ends in the second knockout "
                "round.\n"
                "  • Belgium 4-1 USA — co-hosts blown away. The "
                "scoreline\n"
                "     flattered nobody.\n"
                "  • England 3-2 Mexico — a thriller. England edge "
                "the third\n"
                "     and final co-host in a game that swung three "
                "times.\n"
                "  • France 1-0 Paraguay — France grind past the side "
                "that\n"
                "     had knocked Germany out. Not pretty. Effective.\n"
                "  • Spain 1-0 Portugal — the Iberian derby to Spain. "
                "One\n"
                "     goal decided a game everyone expected to go the "
                "distance.\n"
                "  🔥 Argentina 3-2 Egypt — the tie of the round. Down "
                "2-0\n"
                "     with 20 minutes left, Messi turned it on — three\n"
                "     Argentina goals in fifteen minutes, Enzo "
                "Fernández the\n"
                "     stoppage-time winner.\n"
                "  • Switzerland 0-0 Colombia (Switzerland win 4-3 on "
                "penalties).\n"
                "     120 goalless minutes. The Swiss keep their "
                "nerve from\n"
                "     the spot.\n"
                "\n"
                "Three of the four North American co-hosts, gone. "
                "Portugal,\n"
                "gone. The bracket has never looked more open.\n"
                "\n"
                "Where you stand\n"
                "  🏆 Top of the table:       {{TOP_1}}\n"
                "     Hot on their heels:    {{TOP_2_WITH_GAP}}\n"
                "     Three to watch:        {{TOP_3_TO_5}}\n"
                "     Best haul of the round: {{R16_HERO}}\n"
                "  🚀 Biggest climb:          {{CLIMBERS}}\n"
                "\n"
                "Bottlers watch: {{BOTTLERS_PAID_OUT}}. "
                "{{BOTTLERS_SURPRISE}}\n"
                "\n"
                "See where you stand\n"
                "https://wc26.heyvinay.com/leaderboard\n"
                "\n"
                "New this week\n"
                "  • The leaderboard now moves live during knockout "
                "matches.\n"
                "    Standings re-sort in real time based on who's "
                "currently\n"
                "    winning on the pitch, then lock to the real "
                "numbers at\n"
                "    full time.\n"
                "    → https://wc26.heyvinay.com/leaderboard\n"
                "  • Bracket Simulator upgrade. The trivia unlock quiz "
                "and\n"
                "    the one-run-a-day cap are gone — run as many "
                "what-if\n"
                "    QF/SF/Final scenarios as you like. Projected "
                "pool\n"
                "    standings now correctly include your "
                "knockout-stage\n"
                "    bonus points too.\n"
                "    → https://wc26.heyvinay.com/results?round=bracket\n"
                "  • Tap the ✦ icon in the nav for a What's New "
                "panel with\n"
                "    everything that's shipped recently — and a "
                "one-tap way\n"
                "    to rate the app and send a quick note. We read "
                "every one.\n"
                "\n"
                "The final eight (all times Malta)\n"
                "  • France vs Morocco     — Thu 9 Jul, 22:00. "
                "Boston.\n"
                "                            A 2022 semi-final "
                "rematch.\n"
                "  • Spain vs Belgium      — Fri 10 Jul, 21:00. "
                "Los Angeles.\n"
                "  • Norway vs England     — Sat 11 Jul, 23:00. "
                "Miami. Haaland vs Kane.\n"
                "  • Argentina vs Switzerland — Sun 12 Jul, 03:00. "
                "Kansas City.\n"
                "\n"
                "Points-per-match doubles from here on. One correct "
                "QF outcome\n"
                "is worth more than a whole group-stage matchday. "
                "Every scoreline,\n"
                "every bracket pick, every bonus answer starts to "
                "matter twice as\n"
                "much. If you've been coasting mid-table, this is "
                "where the table\n"
                "breaks open.\n"
                "\n"
                "See you at the top of the table.\n"
            ),
            cta_label="See the full table",
        )

    if segment == BroadcastSegment.LAPSING:
        # v2.176.0 — soft mid-tournament nudge for users who were
        # engaged early but haven't visited in 3-7 days. The copy
        # doesn't personalise the rank (the broadcast loop fires one
        # email per recipient with the same body) — leaderboard
        # personalisation is a future enhancement.
        return _BroadcastContent(
            subject="Atlas World Cup 2026 Pools | Don't lose your edge",
            headline="Don't lose your edge — matchday is coming up.",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name}, you haven't been around for a few days "
                "and the tournament is heating up.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "The leaderboard has been moving — come check where you "
                "stand and see how your picks are playing out.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:14px;line-height:1.55;'
                f'color:{_MUTED_INK};">'
                "Stay sharp.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name}, you haven't been around for a few days\n"
                "and the tournament is heating up.\n"
                "\n"
                "The leaderboard has been moving — come check where you\n"
                "stand and see how your picks are playing out.\n"
                "\n"
                "Stay sharp.\n"
            ),
            cta_label="See the latest results",
        )

    if segment == BroadcastSegment.TOURNAMENT_FINAL:
        # v2.214.x — conclusion announcement. Rewritten 2026-07-20 (three
        # passes) to: open by thanking the recipient for taking part, lead
        # with the actual match result, note a couple of REAL FIFA World
        # Cup highlights (hardcoded prose — historical fact about the
        # tournament itself, not the pool; same for every recipient, no
        # token needed), fold in the pool's own story/highlights via
        # {{STORY_LINE}} (the same narrative the wrap-up page's
        # TitleMatrix shows — one resolver, not a re-derived summary), add
        # a dedicated compare-entry link, thank Atlas Insurance for the
        # Soup Kitchen top-up + Trionda ball, ask for feedback, and close
        # with a callback to Euro 2028. Same audience as the recap family
        # (every submitter). Deliberately SHORT for a "last email of the
        # season" — no UTM tag (same deliverability lesson as
        # R2/GSF/R32/R16: no campaign params, no "winner+announced" word
        # pair). {{FINAL_RESULT}} and {{STORY_LINE}} are filled at send
        # time by ``_compute_tournament_final_email_tokens`` from the same
        # final-podium service (+ the Final fixture's score) backing the
        # wrap-up page, so the email and the app agree on the numbers —
        # deliberately NOT a separate {{CHAMPION_NAME}}/{{CHAMPION_TOTAL}}
        # pair, since STORY_LINE already names the champion and margin in
        # prose. The compare link is a hardcoded absolute URL, matching
        # every other inline (non-CTA-button) link in this file — not a
        # token, since the destination never varies per recipient.
        return _BroadcastContent(
            subject="WC26 — that's a wrap",
            headline="We have a champion",
            body_html=(
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                f"Hi {safe_name},</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Thank you for being part of this year&rsquo;s pool "
                "&mdash; five weeks of picks, bragging rights, and more "
                "than a few nerve-wracking finishes.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "{{FINAL_RESULT}}</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "It was a wild ride to get there &mdash; Cape Verde held "
                "Spain to a scoreless draw, and Paraguay and Morocco both "
                "knocked out major favourites (Germany and the "
                "Netherlands) on penalties in the Round of 32.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "{{STORY_LINE}}</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "The full final standings are up now.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "&#129300; Not the result you wanted? "
                '<a href="https://wc26.heyvinay.com/compare" '
                f'style="color:{_GOLD};text-decoration:underline;">'
                "Compare your entry against the champion&rsquo;s, pick by "
                "pick</a>.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "A big thank you to <strong>Atlas Insurance</strong>, who "
                "topped up our Soup Kitchen contribution by &euro;500 and "
                "provided the Adidas Trionda match ball (&euro;150) as "
                "our runner-up prize.</p>\n"
                f'              <p style="margin:0 0 14px 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "Got 30 seconds? We&rsquo;d love to know what you "
                "thought &mdash; there&rsquo;s a quick feedback link in "
                "the app&rsquo;s footer. It shapes the next one.</p>\n"
                f'              <p style="margin:0 0 0 0;font-size:15px;line-height:1.55;'
                f'color:{_BODY_INK};">'
                "See you in June 2028 for Euro 2028 &mdash; thanks for "
                "playing.</p>\n"
            ),
            body_text=(
                f"Hi {safe_name},\n"
                "\n"
                "Thank you for being part of this year's pool — five "
                "weeks of picks, bragging rights, and more than a few "
                "nerve-wracking finishes.\n"
                "\n"
                "{{FINAL_RESULT}}\n"
                "\n"
                "It was a wild ride to get there — Cape Verde held Spain "
                "to a scoreless draw, and Paraguay and Morocco both "
                "knocked out major favourites (Germany and the "
                "Netherlands) on penalties in the Round of 32.\n"
                "\n"
                "{{STORY_LINE}}\n"
                "\n"
                "The full final standings are up now.\n"
                "\n"
                "Not the result you wanted? Compare your entry against "
                "the champion's, pick by pick:\n"
                "https://wc26.heyvinay.com/compare\n"
                "\n"
                "A big thank you to Atlas Insurance, who topped up our "
                "Soup Kitchen contribution by €500 and provided the "
                "Adidas Trionda match ball (€150) as our runner-up "
                "prize.\n"
                "\n"
                "Got 30 seconds? We'd love to know what you thought — "
                "there's a quick feedback link in the app's footer. It "
                "shapes the next one.\n"
                "\n"
                "See you in June 2028 for Euro 2028 — thanks for "
                "playing.\n"
            ),
            cta_label="See the final standings",
        )

    raise ValueError(f"Unknown segment: {segment!r}")


# ---------------------------------------------------------------------------
# R2 recap dynamic interpolation (v2.180.1)
# ---------------------------------------------------------------------------
# v2.180.0 shipped the R2 template with literal {{TOP_1}}, {{R2_HERO}},
# {{CLIMBERS}} placeholders that admins were expected to hand-fill in
# email.py before pressing Send. That UX was broken — the first test
# send surfaced the raw tokens in the rendered email. v2.180.1 closes
# the loop by computing these values from live data at send time and
# string-replacing the placeholders.
#
# The compute runs ONCE per broadcast (not per recipient) — the API
# layer pre-computes the token dict and passes it through every
# per-recipient send_broadcast_email call.


async def _compute_round_hero_str(
    session, *, before_date, round_label: str
) -> str:
    """Top entry by points scored between two snapshots.

    `match_predictions` has no stored points column (scoring is
    computed on read, then cached in the leaderboard). Stored
    per-fixture points don't exist anywhere. The practical signal is
    the diff between two `leaderboard_snapshots` rows:

      points_gained_during_round =
        latest_snapshot.total_points − latest_snapshot_on_or_before_R2_start.total_points

    `before_date` is a `datetime.date` boundary (date(2026, 6, 18) for
    R2 — the day before any R2 fixture). asyncpg requires a date
    object, not an ISO string — strings raise DataError. The SQL takes the latest snapshot with
    `captured_date <= before_date` as the baseline, and diffs against
    the latest snapshot overall. `round_label` only affects the
    returned string ("across Round 2").

    Returns "Person Name — N points across {round_label}" or "—" if
    no data is available (e.g. one of the snapshots is missing).
    """
    from sqlalchemy import text
    sql = text("""
        WITH before AS (
          SELECT entry_id, total_points
          FROM leaderboard_snapshots
          WHERE captured_date = (
            SELECT MAX(captured_date) FROM leaderboard_snapshots
            WHERE captured_date <= :before_date
          )
        ),
        latest AS (
          SELECT entry_id, total_points
          FROM leaderboard_snapshots
          WHERE captured_date = (SELECT MAX(captured_date) FROM leaderboard_snapshots)
        )
        SELECT pe.display_name AS entry_name,
               COALESCE(u.name, '?') AS user_name,
               (n.total_points - b.total_points) AS round_points
        FROM latest n
        JOIN before b              USING (entry_id)
        JOIN prediction_entries pe ON pe.id = n.entry_id
        JOIN users u               ON u.id = pe.user_id
        WHERE pe.is_disabled = false
          AND pe.withdrawn_at IS NULL
        ORDER BY round_points DESC NULLS LAST
        LIMIT 1
    """)
    try:
        row = (await session.execute(sql, {"before_date": before_date})).first()
    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("R2 hero query failed: %s", exc)
        return "—"
    if not row or row.round_points is None:
        return "—"
    return (
        f"{row.user_name} — {int(row.round_points)} points "
        f"across {round_label}"
    )


async def _compute_climbers_str(session) -> str:
    """Render the biggest-climb race story as a human string.

    Falls back to a Race-tab pointer when no entry qualifies (e.g.
    pre-deadline pool, all entries flat, or every climb under the
    threshold). The story's ``title`` is already "{user_name} — up N"
    and ``caption`` is "From #X to #Y in 3 days." — we concatenate.
    """
    try:
        from app.services.race_stories import select_race_stories
        stories = await select_race_stories(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("R2 climbers query failed: %s", exc)
        return "see the Race tab on /leaderboard"
    climb = next((s for s in stories if s.kind == "biggest_climb"), None)
    if not climb:
        return "see the Race tab on /leaderboard"
    return f"{climb.title} ({climb.caption.rstrip('.')})"


async def _compute_r2_highlights(session) -> dict[str, str]:
    """Build the token dict for R2 broadcast interpolation.

    Pulls top-5 leaderboard rows + R2 points hero + biggest climber.
    Empty dict means "no eligible data" — placeholders remain literal
    in the email body, which surfaces the failure to the admin via the
    test-send rather than silently sending a broken email.
    """
    from app.services.leaderboard import calculate_leaderboard
    try:
        lb = await calculate_leaderboard(session, phase=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("R2 leaderboard fetch failed: %s", exc)
        return {}

    entries = lb.entries[:5]
    if not entries:
        return {}

    # Disambiguate same-user-multiple-entries with "Person — Entry name"
    # so the top 5 doesn't print "Vinay" three times. Mirrors the
    # frontend's rowDisplayName() rule in leaderboardV4.ts — count user
    # occurrences within the visible slice, attach entry name only when
    # the owner holds multiple of these top spots.
    user_counts: dict[str, int] = {}
    for e in entries:
        user_counts[e.user_name] = user_counts.get(e.user_name, 0) + 1

    def display_for(e) -> str:
        if user_counts.get(e.user_name, 0) > 1:
            return f"{e.user_name} — {e.entry_name}"
        return e.user_name

    top_1 = entries[0]
    top_1_str = f"{display_for(top_1)} — {top_1.total_points} pts"

    if len(entries) >= 2:
        gap = top_1.total_points - entries[1].total_points
        gap_str = "tied" if gap == 0 else f"{gap} behind"
        top_2_str = (
            f"{display_for(entries[1])} — {entries[1].total_points} pts "
            f"({gap_str})"
        )
    else:
        top_2_str = "—"

    if len(entries) >= 3:
        top_3_5_str = " · ".join(
            f"{display_for(e)} ({e.total_points})" for e in entries[2:5]
        )
    else:
        top_3_5_str = "—"

    return {
        "TOP_1": top_1_str,
        "TOP_2_WITH_GAP": top_2_str,
        "TOP_3_TO_5": top_3_5_str,
        # R2 boundary: 2026-06-18 is the day BEFORE any R2 fixture
        # (R1's last game UZB-COL kicked off morning of 18 Jun; R2's
        # first game CZE-RSA kicked off 18:00 Malta = 16:00 UTC). So
        # `captured_date <= date(2026, 6, 18)` picks the cleanest
        # pre-R2 snapshot. For future round recaps, edit this date.
        "R2_HERO": await _compute_round_hero_str(
            session,
            before_date=date(2026, 6, 18),
            round_label="Round 2",
        ),
        "CLIMBERS": await _compute_climbers_str(session),
    }


async def _compute_bottlers_str(session) -> dict[str, str]:
    """Compose the Bottlers paragraph tokens for the R16 recap.

    Returns two strings:

    - ``BOTTLERS_PAID_OUT`` — a full sentence naming the currently-
      qualifying Q4 Bottler teams and the pool pick-count per team.
      Reads ``BonusAnswer`` for ``question_id='flop'`` as the source
      of truth — the scoring engine (``bonus.calculate_bonus_points``)
      only pays out points for teams present in that table. If the
      admin has not yet set the flop answers, a "pending" fallback is
      returned so the empty state is visibly surfaced in a test-send
      rather than silently rendering a broken sentence.
    - ``BOTTLERS_SURPRISE`` — the pool's most-picked flop team that is
      NOT in the paid-out list (i.e. still in the tournament, or
      progressed further than the earliest-exit min). Formatted as
      ``"{team} ({n} picks)"`` or ``"—"`` on empty.

    Pick counts are filtered to eligible entries via the same
    predicate rarity uses (SUBMITTED + not disabled + not withdrawn),
    so the counts match what the scorer actually paid.

    Fail-open — any exception returns a ``"—"`` pair. Broadcast-email
    build MUST NOT crash on a helper failure.
    """
    try:
        from sqlalchemy import text as _sql_text

        # 1) Currently paid-out flop teams (admin-settled answers).
        paid_rows = (
            await session.execute(
                _sql_text(
                    "SELECT correct_answer FROM bonus_answers "
                    "WHERE question_id='flop'"
                )
            )
        ).all()
        paid_teams: list[str] = [r.correct_answer for r in paid_rows]

        # 2) Pool pick counts per flop team, eligible entries only.
        counts_rows = (
            await session.execute(
                _sql_text(
                    "SELECT bp.answer AS team, COUNT(*) AS n "
                    "FROM bonus_predictions bp "
                    "JOIN prediction_entries pe ON pe.id = bp.entry_id "
                    "JOIN prediction_entry_phases peph "
                    "  ON peph.entry_id = pe.id "
                    "WHERE bp.question_id='flop' "
                    "  AND pe.is_disabled = false "
                    "  AND pe.withdrawn_at IS NULL "
                    "  AND peph.status = 'SUBMITTED' "
                    "GROUP BY bp.answer"
                )
            )
        ).all()
        counts: dict[str, int] = {r.team: int(r.n) for r in counts_rows}

    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("R16 bottlers query failed: %s", exc)
        return {"BOTTLERS_PAID_OUT": "—", "BOTTLERS_SURPRISE": "—"}

    # Empty-state: admin hasn't finalised the flop answer yet.
    # Note: BOTTLERS_SURPRISE returns EMPTY STRING (not "—") so the
    # footnote sentence self-elides in both bodies — the template is
    # "{{BOTTLERS_PAID_OUT}}. {{BOTTLERS_SURPRISE}}" and an empty
    # surprise means "no trailing sentence." A "—" here would render
    # as "— was the pool's most-picked Bottler and hasn't obliged"
    # which is nonsensical.
    if not paid_teams:
        return {
            "BOTTLERS_PAID_OUT": (
                "the Q4 payout list is still being finalised"
            ),
            "BOTTLERS_SURPRISE": "",
        }

    # Compose the paid-out sentence. Rendering rule:
    #   * one team: "Team is the Q4 payout so far — N of you picked
    #     Team, banking those points."
    #   * multiple: "Team A and Team B are the two Q4 payouts so
    #     far — N of you picked A, M picked B, banking those points."
    #   * zero-pick clauses use "nobody picked X" phrasing (more
    #     natural than "0 of you picked X") — surfaces the "we all
    #     missed it" moment editorially.
    def _pick_clause(team: str) -> str:
        n = counts.get(team, 0)
        if n == 0:
            return f"nobody picked {team}"
        if n == 1:
            return f"1 of you picked {team}"
        return f"{n} of you picked {team}"

    n_teams = len(paid_teams)
    if n_teams == 1:
        team = paid_teams[0]
        paid_line = (
            f"{team} is the sole Q4 payout on the board so far — "
            f"{_pick_clause(team)}"
        )
    else:
        # Oxford-serial join for the team list.
        if n_teams == 2:
            teams_joined = " and ".join(paid_teams)
            article = "the two"
        else:
            teams_joined = (
                ", ".join(paid_teams[:-1]) + f", and {paid_teams[-1]}"
            )
            article = f"the {n_teams}"
        clauses = [_pick_clause(t) for t in paid_teams]
        if len(clauses) == 2:
            picks_joined = " and ".join(clauses)
        else:
            picks_joined = (
                ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
            )
        paid_line = (
            f"{teams_joined} are {article} Q4 payouts on the board so "
            f"far — {picks_joined}"
        )

    # Surprise: top-picked flop team NOT in the paid-out list.
    paid_set = set(paid_teams)
    surprise_candidates = sorted(
        ((t, n) for t, n in counts.items() if t not in paid_set),
        key=lambda tn: (-tn[1], tn[0]),
    )
    if not surprise_candidates:
        # No non-paying pick to name — omit the footnote entirely
        # (empty string, so the template's trailing sentence elides).
        surprise_str = ""
    else:
        top_team, top_n = surprise_candidates[0]
        picks_word = "pick" if top_n == 1 else "picks"
        # Full sentence, so the template can render
        # "{{BOTTLERS_PAID_OUT}}. {{BOTTLERS_SURPRISE}}" and self-
        # elide when there's no surprise. Trailing period included.
        surprise_str = (
            f"As a footnote: {top_team} ({top_n} {picks_word}) was the "
            f"pool's most-picked Bottler and hasn't obliged."
        )

    return {
        "BOTTLERS_PAID_OUT": paid_line,
        "BOTTLERS_SURPRISE": surprise_str,
    }


async def _compute_r16_highlights(session) -> dict[str, str]:
    """Build the token dict for the GROUP_R16_RECAP broadcast email.

    Mirrors ``_compute_r2_highlights`` shape (top-5 standings + round
    hero + climber) with the R16 boundary date (2026-07-03 — the day
    before any R16 fixture kicked off) and merges in the two Bottlers
    tokens.

    Empty dict means "no eligible data" — placeholders remain literal
    in the email body, which surfaces the failure to the admin via a
    test-send rather than silently sending a broken email.
    """
    from app.services.leaderboard import calculate_leaderboard
    try:
        lb = await calculate_leaderboard(session, phase=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("R16 leaderboard fetch failed: %s", exc)
        return {}

    entries = lb.entries[:5]
    if not entries:
        return {}

    # Multi-entry disambiguation — same rule as _compute_r2_highlights.
    user_counts: dict[str, int] = {}
    for e in entries:
        user_counts[e.user_name] = user_counts.get(e.user_name, 0) + 1

    def display_for(e) -> str:
        if user_counts.get(e.user_name, 0) > 1:
            return f"{e.user_name} — {e.entry_name}"
        return e.user_name

    top_1 = entries[0]
    top_1_str = f"{display_for(top_1)} — {top_1.total_points} pts"

    if len(entries) >= 2:
        gap = top_1.total_points - entries[1].total_points
        gap_str = "tied" if gap == 0 else f"{gap} behind"
        top_2_str = (
            f"{display_for(entries[1])} — {entries[1].total_points} pts "
            f"({gap_str})"
        )
    else:
        top_2_str = "—"

    if len(entries) >= 3:
        top_3_5_str = " · ".join(
            f"{display_for(e)} ({e.total_points})" for e in entries[2:5]
        )
    else:
        top_3_5_str = "—"

    # R16 boundary: 2026-07-03 is the day BEFORE any R16 fixture
    # (first R16 KO: 2026-07-04 17:00 UTC = 19:00 Malta). Verified
    # via `SELECT MIN(kickoff) FROM fixtures WHERE stage='round_of_16'`
    # against the live DB 2026-07-09. For future round recaps, edit
    # this date to (first-KO-date − 1).
    hero_str = await _compute_round_hero_str(
        session,
        before_date=date(2026, 7, 3),
        round_label="the Round of 16",
    )
    climbers_str = await _compute_climbers_str(session)
    bottlers = await _compute_bottlers_str(session)

    return {
        "TOP_1": top_1_str,
        "TOP_2_WITH_GAP": top_2_str,
        "TOP_3_TO_5": top_3_5_str,
        "R16_HERO": hero_str,
        "CLIMBERS": climbers_str,
        **bottlers,
    }


async def _compute_group_stage_winner_email_tokens(session) -> dict[str, str]:
    """Build the token dict for the GROUP_STAGE_FINAL broadcast email.

    Pulls from the same service that backs the dashboard's
    GroupStageWinnerCard, so card and email agree on every number.
    Returns an empty dict if no winner can be determined (defensive —
    surfaces visibly as literal {{WINNER_NAME}} in the test send so
    admins notice rather than sending a broken email).

    Tokens:
      WINNER_NAME        — "Brandon Bonello" (multi-entry disambig if owner has >1 top entry — n/a here, single winner)
      WINNER_FIRST_NAME  — "Brandon"
      ENTRY_NAME         — "Brandon 1"
      TOTAL_POINTS       — "282"
      OUTCOME_PTS        — "168"
      EXACT_EXTRA        — "45"
      RARITY_EXTRA       — "52"
      BONUS_PTS          — "17"
      STORY_LINE         — pre-composed sentence; champion-pick + finalists + days-at-top with graceful omission of unfavourable bits
    """
    from sqlalchemy import select
    from app.models.competition import Competition
    from app.services.group_stage_winner import get_group_stage_podium

    # Gate token compute on the released flag — same rule as the
    # dashboard card. Sunday workflow: admin flips release first
    # (card appears on dashboards), then test-sends the broadcast
    # email to verify wording, then fires the real send. If the
    # release flag is OFF, the email tokens come back empty and the
    # rendered email shows literal {{WINNER_NAME}} placeholders —
    # this is the visible signal that "you tested too early."
    try:
        comp = (
            await session.execute(
                select(Competition).where(Competition.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if comp is None or not comp.group_stage_winner_released:
            return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("GSW release-flag check failed: %s", exc)
        return {}

    try:
        podium = await get_group_stage_podium(session)
    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("GSW token compute failed: %s", exc)
        return {}
    if podium is None or not podium.entries:
        return {}

    w = podium.entries[0]
    first_name = (w.user_name or "").split(" ", 1)[0] or w.user_name or "—"

    # The story line is pre-composed by the podium service so the card
    # and the email render identical prose. To tweak wording, edit
    # `_compose_story_line` in services/group_stage_winner.py — both
    # surfaces will reflect the change on next request.
    return {
        "WINNER_NAME": w.user_name,
        "WINNER_FIRST_NAME": first_name,
        "ENTRY_NAME": w.entry_name,
        "TOTAL_POINTS": str(w.total_points),
        "OUTCOME_PTS": str(w.outcome_points),
        "EXACT_EXTRA": str(w.exact_score_extra),
        "RARITY_EXTRA": str(w.rarity_extra),
        "BONUS_PTS": str(w.bonus_question_points),
        "STORY_LINE": podium.story_line,
    }


def _format_final_result(fixture, score) -> str:
    """One-liner match result for the TOURNAMENT_FINAL email.

    Derived directly from the Final fixture's Score (outcome +
    final_home_score/final_away_score, which already fall back to
    regulation when extra time wasn't played — same properties
    ``api/leaderboard.py``'s champion endpoint uses), not the
    admin-editable ``Competition.final_match_narrative`` — so this line
    is always present and factually pinned the moment the match is
    FINISHED, with no dependency on whether a narrative was saved.
    """
    if score is None:
        return "The Final has been played."
    went_to_et = score.home_score_et is not None or score.away_score_et is not None
    home_score = score.final_home_score
    away_score = score.final_away_score

    if score.outcome == "1":
        winner, loser = fixture.home_team, fixture.away_team
        w_score, l_score = home_score, away_score
        w_pens, l_pens = score.home_penalties, score.away_penalties
    elif score.outcome == "2":
        winner, loser = fixture.away_team, fixture.home_team
        w_score, l_score = away_score, home_score
        w_pens, l_pens = score.away_penalties, score.home_penalties
    else:
        # Defensive — a truly FINISHED final always resolves a winner.
        return f"{fixture.home_team} {home_score}–{away_score} {fixture.away_team} in the Final."

    if w_pens is not None and l_pens is not None:
        return f"{winner} beat {loser} {w_score}–{l_score}, {w_pens}–{l_pens} on penalties."
    if went_to_et:
        return f"{winner} beat {loser} {w_score}–{l_score} after extra time."
    return f"{winner} beat {loser} {w_score}–{l_score}."


async def _compute_tournament_final_email_tokens(session) -> dict[str, str]:
    """Build the token dict for the TOURNAMENT_FINAL broadcast email.

    Mirrors :func:`_compute_group_stage_winner_email_tokens`'s
    gate-then-fetch shape. Returns an empty dict (→ literal
    ``{{FINAL_RESULT}}``/``{{STORY_LINE}}`` placeholders survive) if the
    tournament isn't marked concluded yet or the podium can't be
    computed — the visible signal that "you tested too early", same as
    the GSW pattern.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.competition import Competition
    from app.models.fixture import Fixture
    from app.services.tournament_champion import get_final_podium

    try:
        comp = (
            await session.execute(
                select(Competition).where(Competition.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if comp is None or not comp.tournament_concluded:
            return {}  # literal {{TOKENS}} = "sent before conclusion" signal
    except Exception as exc:  # noqa: BLE001
        logger.warning("TOURNAMENT_FINAL release-flag check failed: %s", exc)
        return {}

    try:
        podium = await get_final_podium(session)
    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("TOURNAMENT_FINAL token compute failed: %s", exc)
        return {}
    if not podium or not podium["entries"]:
        return {}

    try:
        final_fx = (
            (
                await session.execute(
                    select(Fixture)
                    .options(selectinload(Fixture.score))
                    .where(Fixture.stage == "final")
                )
            )
            .scalars()
            .first()
        )
        final_result = _format_final_result(final_fx, final_fx.score if final_fx else None)
    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("TOURNAMENT_FINAL result compute failed: %s", exc)
        final_result = "The Final has been played."

    return {
        "FINAL_RESULT": final_result,
        # Same story_line the wrap-up page's TitleMatrix renders (e.g.
        # "Matthew Ellul takes the title by 10 points — 8 exact scores
        # and a bracket that held..."). Already names the champion,
        # margin and a highlight stat in one line — no separate
        # CHAMPION_NAME/CHAMPION_TOTAL token needed.
        "STORY_LINE": podium["story_line"],
    }


def _interpolate(
    content: _BroadcastContent, tokens: dict[str, str]
) -> _BroadcastContent:
    """Replace ``{{KEY}}`` placeholders across all string fields.

    Returns a NEW frozen ``_BroadcastContent`` rather than mutating —
    the dataclass is frozen so mutation would error anyway. Empty token
    dict returns content unchanged (no allocations).
    """
    if not tokens:
        return content

    def sub(s: str) -> str:
        for k, v in tokens.items():
            s = s.replace("{{" + k + "}}", v)
        return s

    return _BroadcastContent(
        subject=sub(content.subject),
        headline=sub(content.headline),
        body_html=sub(content.body_html),
        body_text=sub(content.body_text),
        cta_label=content.cta_label,
    )


async def send_broadcast_email(
    *,
    to_email: str,
    player_name: str,
    segment: BroadcastSegment,
    deep_link_url: str,
    deadline_display: str | None,
    deadline_dt: datetime | None = None,
    tokens: dict[str, str] | None = None,
) -> None:
    """Send ONE broadcast email to ONE recipient.

    Used both by the single-recipient test-send endpoint and by the
    real broadcast loop (one call per audience row, paced from the
    endpoint with ``asyncio.sleep(0.05)`` between sends to stay under
    Resend's free-tier rate limit).

    Mirrors the magic-link dev fallback — with ``RESEND_API_KEY`` unset
    the message is logged to stdout instead, so local testing of the
    flow needs no email account.

    Raises ``RuntimeError`` on a non-2xx Resend response so the caller
    can count failures + surface a sample to the admin.
    """
    settings = get_settings()
    content = _broadcast_content_for_segment(
        segment,
        player_name=player_name,
        deadline_display=deadline_display,
        deadline_dt=deadline_dt,
    )
    # Token-driven placeholder substitution (currently only R2 recap
    # uses it). Tokens are pre-computed at the API layer ONCE per
    # broadcast and passed through every per-recipient call so we
    # don't re-query the leaderboard 183 times.
    if tokens:
        content = _interpolate(content, tokens)

    if not settings.resend_api_key:
        # Dev fallback — print the full message body too so we can
        # eyeball-check the per-segment copy without a real send.
        print(
            f"[broadcast] RESEND_API_KEY not set — dev mode, printing instead. "
            f"to={to_email} segment={segment.value} subject={content.subject!r}",
            flush=True,
        )
        print(f"[broadcast] link={deep_link_url}", flush=True)
        print(f"[broadcast] body={content.body_text}", flush=True)
        return

    html_body = _build_broadcast_html(content, deep_link_url)
    text_body = _build_broadcast_text(content, deep_link_url)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": to_email,
                "subject": content.subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error(
            "[broadcast] Resend API error %s: %s",
            response.status_code,
            response.text,
        )
        raise RuntimeError("Failed to send broadcast email")


def _build_broadcast_html(
    content: _BroadcastContent, deep_link_url: str
) -> str:
    """Wrap segment-specific content in the shared navy/gold chrome.

    Closely mirrors ``_build_entry_unlocked_html`` — same header band,
    same body padding, same CTA button styling, same footer. Keeps
    the transactional + nudge emails reading as one consistent brand.
    """
    safe_headline = content.headline.replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1.0" />\n'
        f'  <title>{safe_headline}</title>\n'
        '</head>\n'
        f'<body style="margin:0;padding:0;background:{_PAGE_BG};'
        f'font-family:{_BODY_FONT};color:{_BODY_INK};">\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAGE_BG};padding:32px 12px;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '        <table width="520" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:520px;width:100%;background:{_CARD_BG};'
        'border-radius:12px;overflow:hidden;'
        'box-shadow:0 6px 24px -12px rgba(11,19,41,0.18);">\n'
        # ---- Header band ----
        '          <tr>\n'
        '            <td align="center" '
        f'style="background:{_NAVY};padding:28px 24px;">\n'
        f'              <div style="font-family:{_DISPLAY_FONT};font-size:16px;'
        'font-weight:700;letter-spacing:0.10em;white-space:nowrap;'
        f'color:{_GOLD};text-transform:uppercase;line-height:1.2;">'
        'Atlas World Cup 2026 Pools</div>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Body ----
        '          <tr>\n'
        '            <td style="padding:36px 32px 8px 32px;">\n'
        f'              <h1 style="margin:0 0 14px 0;font-family:{_DISPLAY_FONT};'
        f'font-size:22px;font-weight:700;color:{_NAVY};letter-spacing:-0.01em;">'
        f'{safe_headline}</h1>\n'
        f'{content.body_html}'
        '            </td>\n'
        '          </tr>\n'
        # ---- CTA button ----
        '          <tr>\n'
        '            <td align="center" style="padding:8px 32px 24px 32px;">\n'
        f'              <a href="{deep_link_url}" '
        f'style="display:inline-block;background:{_GOLD};color:{_NAVY};'
        f'font-family:{_BODY_FONT};font-size:14px;font-weight:700;'
        'letter-spacing:0.06em;text-transform:uppercase;text-decoration:none;'
        f'padding:14px 28px;border-radius:8px;">{content.cta_label}</a>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Raw URL fallback ----
        '          <tr>\n'
        '            <td style="padding:0 32px 24px 32px;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};word-break:break-all;">'
        'If the button doesn\'t work, paste this link into your browser:<br/>\n'
        f'                <a href="{deep_link_url}" '
        f'style="color:{_MUTED_INK};text-decoration:underline;">'
        f'{deep_link_url}</a>'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Footer ----
        '          <tr>\n'
        '            <td '
        f'style="padding:18px 32px 28px 32px;border-top:1px solid #E2E8F0;">\n'
        f'              <p style="margin:0;font-size:12px;line-height:1.5;'
        f'color:{_MUTED_INK};">'
        'This mailbox is not monitored — please don\'t reply to this email.</p>\n'
        f'              <p style="margin:14px 0 0 0;font-size:12px;'
        f'color:{_MUTED_INK};">— Atlas World Cup 2026 Pools</p>\n'
        '            </td>\n'
        '          </tr>\n'
        '        </table>\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '</body>\n'
        '</html>'
    )


def _build_broadcast_text(
    content: _BroadcastContent, deep_link_url: str
) -> str:
    """Plain-text alternative."""
    return (
        f"{content.headline}\n"
        "\n"
        f"{content.body_text}"
        "\n"
        f"{content.cta_label}:\n"
        f"{deep_link_url}\n"
        "\n"
        "This mailbox is not monitored — please don't reply to this email.\n"
        "\n"
        "— Atlas World Cup 2026 Pools\n"
    )
