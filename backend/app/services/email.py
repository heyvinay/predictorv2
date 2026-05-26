"""Email delivery via Resend API.

Used by the magic-link auth flow to send sign-in links. In dev mode
without `RESEND_API_KEY` set, the link is logged to stdout instead so
local testing doesn't require an email account.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

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
                "subject": "Welcome — your Predictor sign-in link",
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
        '  <title>Welcome — your Predictor sign-in link</title>\n'
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
        f'              <div style="font-family:{_DISPLAY_FONT};font-size:26px;'
        'font-weight:700;letter-spacing:0.18em;'
        f'color:{_GOLD};text-transform:uppercase;line-height:1;">PREDICTOR</div>\n'
        '              <div style="margin-top:8px;font-size:11px;letter-spacing:0.18em;'
        'text-transform:uppercase;color:rgba(248,250,252,0.65);">'
        'World Cup 2026</div>\n'
        '            </td>\n'
        '          </tr>\n'
        # ---- Body ----
        '          <tr>\n'
        '            <td style="padding:36px 32px 8px 32px;">\n'
        f'              <h1 style="margin:0 0 12px 0;font-family:{_DISPLAY_FONT};'
        f'font-size:24px;font-weight:700;color:{_NAVY};letter-spacing:-0.01em;">'
        'Welcome to The Predictor.</h1>\n'
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
        '              <p style="margin:14px 0 0 0;font-size:12px;'
        f'color:{_MUTED_INK};">— The Predictor</p>\n'
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
        "Welcome to The Predictor.\n"
        "\n"
        "Your sign-in link is ready. Open it in your browser to sign in:\n"
        f"{magic_link_url}\n"
        "\n"
        "This link expires in 15 minutes and can only be used once.\n"
        "If you didn't request it, you can safely ignore this email.\n"
        "\n"
        "— The Predictor\n"
    )
