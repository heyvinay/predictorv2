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
                "subject": "Your Predictor sign-in link",
                "html": html_body,
            },
            timeout=10.0,
        )

    if response.status_code not in (200, 201):
        logger.error("[magic-link] Resend API error %s: %s", response.status_code, response.text)
        raise RuntimeError("Failed to send magic link email")


def _build_email_html(magic_link_url: str) -> str:
    """Render the sign-in email body.

    Plain inlined-CSS HTML — designed to render the same in Gmail,
    Outlook, Apple Mail, etc. without relying on stylesheets, web
    fonts, or background images.
    """
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        '  <title>Sign in to The Predictor</title>\n'
        '</head>\n'
        '<body style="margin:0;padding:0;background:#f1ebde;'
        "font-family:'IBM Plex Sans',Arial,sans-serif;\">\n"
        '  <table width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f1ebde;padding:40px 0;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '        <table width="480" cellpadding="0" cellspacing="0"\n'
        '               style="background:#f1ebde;border:2px solid #0e1d40;'
        'box-shadow:5px 5px 0 #0e1d40;padding:40px;">\n'
        '          <tr>\n'
        '            <td align="center" style="padding-bottom:24px;">\n'
        '              <div style="width:48px;height:48px;background:#0e1d40;'
        'border-radius:50%;\n'
        '                          display:inline-flex;align-items:center;'
        'justify-content:center;\n'
        '                          font-family:Arial Black,Arial,sans-serif;'
        'font-size:24px;\n'
        '                          color:#f1ebde;line-height:48px;'
        'text-align:center;">P</div>\n'
        '              <div style="font-family:Arial Black,Arial,sans-serif;'
        'font-size:11px;\n'
        '                          letter-spacing:0.14em;text-transform:uppercase;'
        'color:#514a3d;\n'
        '                          margin-top:8px;">The Predictor · Vol. I — WC 2026</div>\n'
        '            </td>\n'
        '          </tr>\n'
        '          <tr>\n'
        '            <td align="center" style="padding-bottom:8px;">\n'
        '              <h1 style="margin:0;font-family:Arial Black,Arial,sans-serif;'
        'font-size:28px;\n'
        '                         color:#0e1d40;letter-spacing:-0.02em;">Your sign-in link</h1>\n'
        '            </td>\n'
        '          </tr>\n'
        '          <tr>\n'
        '            <td align="center" style="padding-bottom:32px;">\n'
        '              <p style="margin:0;font-size:15px;color:#514a3d;line-height:1.5;">\n'
        '                Click the button below to sign in. This link expires in 15&nbsp;minutes\n'
        '                and can only be used once.\n'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        '          <tr>\n'
        '            <td align="center" style="padding-bottom:32px;">\n'
        f'              <a href="{magic_link_url}"\n'
        '                 style="display:inline-block;background:#0e1d40;color:#f1ebde;\n'
        '                        font-family:Arial Black,Arial,sans-serif;font-size:14px;\n'
        '                        letter-spacing:0.08em;text-transform:uppercase;\n'
        '                        padding:14px 32px;text-decoration:none;\n'
        '                        box-shadow:3px 3px 0 #8a1610;">\n'
        '                Sign In to The Predictor\n'
        '              </a>\n'
        '            </td>\n'
        '          </tr>\n'
        '          <tr>\n'
        '            <td align="center">\n'
        '              <p style="margin:0;font-size:11px;color:#8a826f;font-family:monospace;\n'
        '                        letter-spacing:0.06em;">\n'
        "                If you didn&apos;t request this, you can safely ignore this email.\n"
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        '        </table>\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '</body>\n'
        '</html>'
    )
