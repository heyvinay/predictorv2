"""Email delivery via Resend API.

Used by the magic-link auth flow to send sign-in links. In dev mode
without `RESEND_API_KEY` set, the link is logged to stdout instead so
local testing doesn't require an email account.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.services.broadcast import BroadcastSegment
from app.services.team_name import display_team_name

logger = logging.getLogger(__name__)

RESEND_API_URL: str = "https://api.resend.com/emails"


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

    raise ValueError(f"Unknown segment: {segment!r}")


async def send_broadcast_email(
    *,
    to_email: str,
    player_name: str,
    segment: BroadcastSegment,
    deep_link_url: str,
    deadline_display: str | None,
    deadline_dt: datetime | None = None,
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
