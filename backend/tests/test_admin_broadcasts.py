"""Tests for the v2.160.0 admin broadcast emails feature.

Service-level tests pin the segment-query SQL — bug here would either
miss real recipients (failed delivery) or include the wrong ones
(sending the "finish your draft" message to a user who already
submitted, which is embarrassing).

HTTP-level tests pin:
* Admin gate on all three endpoints (403 for non-admin).
* dry_run=True doesn't call Resend.
* Test-send hits the send function exactly once.
* Real broadcast hits the send function N times where N = audience.
* The audit event is written on real sends only (not dry-run, not test).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register every model with metadata
from app.database import get_session
from app.dependencies import get_admin_user, get_current_user
from app.main import app
from app.models.audit import AuditEvent
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.prediction import PredictionPhase
from app.models.user import AuthProvider, User
from app.services.broadcast import (
    BroadcastSegment,
    count_audience,
    count_all_audiences,
    query_audience,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="Test World Cup",
        external_id="WC",
        is_active=True,
        phase1_deadline=datetime(2026, 6, 11, 17, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


async def _make_user(
    session: AsyncSession,
    *,
    email: str,
    name: str | None = "Test",
    is_active: bool = True,
    is_admin: bool = False,
) -> User:
    u = User(
        email=email,
        name=name,
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        is_active=is_active,
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _add_entry_with_phase(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    statuses: list[EntryStatus],
    entry_number: int = 1,
) -> PredictionEntry:
    """Create one entry plus one phase row per status.

    Real entries always have a Phase 1 row; multi-status fixtures mimic
    the (rare) Phase 2 state by adding more rows. For our broadcast
    queries the EXISTS predicate just needs at least one phase row of
    the right status per user — phase value itself is irrelevant.
    """
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC-{user.email[:4]}-{entry_number:03d}",
        display_name=f"Entry {entry_number}",
        entry_number=entry_number,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    # Use distinct phases so the UniqueConstraint(entry_id, phase) holds
    # even when a test wants two rows for one entry.
    phase_values = [PredictionPhase.PHASE_1, PredictionPhase.PHASE_2]
    for idx, status in enumerate(statuses):
        phase_row = PredictionEntryPhase(
            entry_id=entry.id,
            phase=phase_values[idx % len(phase_values)],
            status=status,
        )
        session.add(phase_row)
    await session.commit()
    return entry


@pytest_asyncio.fixture
async def four_segment_archetypes(
    db_session: AsyncSession, competition: Competition
) -> dict[str, User]:
    """Five users covering every relevant audience archetype:

    * ``submitter`` — has a SUBMITTED phase. → SUBMITTERS only.
    * ``no_entry`` — zero entries. → NO_ENTRY only.
    * ``draft_only`` — one DRAFT phase, no SUBMITTED. → DRAFT_HOLDERS only.
    * ``draft_and_submitted`` — has both a DRAFT and a SUBMITTED phase.
      → SUBMITTERS only (excluded from DRAFT_HOLDERS by ~SUBMITTED clause).
    * ``inactive`` — has zero entries BUT ``is_active=False``. Should be
      excluded from EVERY segment.
    * ``onboarding_incomplete`` — has zero entries AND ``name=NULL``.
      Should be excluded from EVERY segment.
    """
    submitter = await _make_user(db_session, email="submitter@example.com")
    await _add_entry_with_phase(
        db_session,
        user=submitter,
        competition=competition,
        statuses=[EntryStatus.SUBMITTED],
    )

    no_entry = await _make_user(db_session, email="noentry@example.com")
    # (no entries added)

    draft_only = await _make_user(db_session, email="draft@example.com")
    await _add_entry_with_phase(
        db_session,
        user=draft_only,
        competition=competition,
        statuses=[EntryStatus.DRAFT],
    )

    draft_and_submitted = await _make_user(
        db_session, email="both@example.com"
    )
    # Single entry with both phases. (Realistic: phase 1 submitted, phase 2 still draft.)
    await _add_entry_with_phase(
        db_session,
        user=draft_and_submitted,
        competition=competition,
        statuses=[EntryStatus.SUBMITTED, EntryStatus.DRAFT],
    )

    inactive = await _make_user(
        db_session, email="inactive@example.com", is_active=False
    )
    onboarding_incomplete = await _make_user(
        db_session, email="incomplete@example.com", name=None
    )

    return {
        "submitter": submitter,
        "no_entry": no_entry,
        "draft_only": draft_only,
        "draft_and_submitted": draft_and_submitted,
        "inactive": inactive,
        "onboarding_incomplete": onboarding_incomplete,
    }


# ===========================================================================
# Service-level tests — segment-query SQL
# ===========================================================================
@pytest.mark.asyncio
class TestAudienceQueries:
    async def test_submitters_includes_both_pure_and_mixed(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        rows = await query_audience(db_session, BroadcastSegment.SUBMITTERS)
        emails = {r.email for r in rows}
        assert emails == {"submitter@example.com", "both@example.com"}

    async def test_group_r1_recap_mirrors_submitters_audience(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        # v2.178.0 — GROUP_R1_RECAP shares the SUBMITTERS predicate so
        # both broadcasts always agree on who counts as a participant.
        # If this assertion ever flips, the round-recap email would
        # silently miss (or duplicate to) the wrong audience — guard it.
        submitters = {
            r.email
            for r in await query_audience(db_session, BroadcastSegment.SUBMITTERS)
        }
        recap = {
            r.email
            for r in await query_audience(
                db_session, BroadcastSegment.GROUP_R1_RECAP
            )
        }
        assert recap == submitters

    async def test_group_r1_recap_content_renders(
        self, db_session: AsyncSession
    ):
        # v2.178.0 — direct render-smoke. Catches any f-string typo or
        # missing constant in the new branch BEFORE it ships to ~167
        # mailboxes. The body must mention the headline copy, both link
        # destinations (with UTM on the standings link), the prize-pot
        # numbers, and the "routes straight to us" support tagline.
        from app.services.email import _broadcast_content_for_segment

        content = _broadcast_content_for_segment(
            BroadcastSegment.GROUP_R1_RECAP,
            player_name="Test User",
            deadline_display="11 Jun 2026, 17:00 UTC",
        )
        assert "Round 1 wraps tomorrow" in content.headline
        assert "Round 1 wraps tomorrow" in content.subject
        for html_must in [
            "Hi Test User",
            "utm_campaign=group_r1_recap",
            "spreadsheets/d/1-UZTOYQh0jIUuMw7VarsXdj8a3gPC3whVwii61ZS75Y",
            "&euro;595",
            "&euro;183",
            "&euro;150",
            "&euro;500",
            "&euro;650",
            "Atlas Insurance",
            "routes straight to us",
        ]:
            assert html_must in content.body_html, f"missing in HTML: {html_must}"
        for text_must in [
            "Hi Test User",
            "utm_campaign=group_r1_recap",
            "€595",
            "€183",
            "€150",
            "€500",
            "€650",
            "routes straight to us",
        ]:
            assert text_must in content.body_text, f"missing in text: {text_must}"
        # Plain text MUST NOT leak the raw spreadsheet URL — recipients
        # are routed to the in-app button instead.
        assert "docs.google.com/spreadsheets" not in content.body_text

    async def test_group_stage_final_template_tokens_interpolate(
        self, db_session: AsyncSession
    ):
        # Regression — v2.183.x bug: ENTRY_NAME placeholder was written
        # inside an f-string with double braces, which Python collapses
        # to a single brace at compile time. The rendered HTML had
        # "{ENTRY_NAME}" (single braces) while _interpolate looks for
        # "{{ENTRY_NAME}}" — so the substitution silently no-op'd.
        # Pin: every advertised token in the GROUP_STAGE_FINAL body
        # must render as the substituted value, never as a literal
        # placeholder fragment.
        from app.services.email import (
            _broadcast_content_for_segment,
            _interpolate,
        )

        content = _broadcast_content_for_segment(
            BroadcastSegment.GROUP_STAGE_FINAL,
            player_name="Test User",
            deadline_display="11 Jun 2026, 17:00 UTC",
        )
        tokens = {
            "WINNER_NAME": "James Vella",
            "WINNER_FIRST_NAME": "James",
            "ENTRY_NAME": "James Vella 3rd Entry",
            "TOTAL_POINTS": "404",
            "OUTCOME_PTS": "225",
            "EXACT_EXTRA": "130",
            "RARITY_EXTRA": "34",
            "BONUS_PTS": "15",
            "STORY_LINE": "James won.",
        }
        rendered = _interpolate(content, tokens)
        # Every token's VALUE must appear in both HTML and text bodies.
        for key, value in tokens.items():
            assert value in rendered.body_html, (
                f"value {value!r} for token {key} missing from HTML"
            )
            assert value in rendered.body_text, (
                f"value {value!r} for token {key} missing from text"
            )
        # And NO double-or-single-brace placeholder fragment may leak.
        # Catches the original f-string single-brace bug AND a future
        # missing-token mistake in one assertion.
        for fragment in ("{{", "}}", "{WINNER_NAME}", "{ENTRY_NAME}",
                         "{TOTAL_POINTS}", "{STORY_LINE}"):
            assert fragment not in rendered.body_html, (
                f"unsubstituted placeholder fragment {fragment!r} in HTML"
            )
            assert fragment not in rendered.body_text, (
                f"unsubstituted placeholder fragment {fragment!r} in text"
            )

    async def test_no_entry_excludes_inactive_and_onboarding_incomplete(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        rows = await query_audience(db_session, BroadcastSegment.NO_ENTRY)
        emails = {r.email for r in rows}
        # Only `noentry@example.com` qualifies. inactive + onboarding-incomplete
        # have zero entries too but are excluded by the base filter.
        assert emails == {"noentry@example.com"}

    async def test_draft_holders_excludes_mixed(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        rows = await query_audience(db_session, BroadcastSegment.DRAFT_HOLDERS)
        emails = {r.email for r in rows}
        # `both@example.com` has a draft phase BUT also has submitted,
        # so they're excluded by the ~submitted clause. Pure draft only.
        assert emails == {"draft@example.com"}

    async def test_segments_are_mutually_exclusive(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        submitters = {
            r.email
            for r in await query_audience(db_session, BroadcastSegment.SUBMITTERS)
        }
        no_entry = {
            r.email
            for r in await query_audience(db_session, BroadcastSegment.NO_ENTRY)
        }
        drafts = {
            r.email
            for r in await query_audience(
                db_session, BroadcastSegment.DRAFT_HOLDERS
            )
        }
        # No user is in more than one segment.
        assert submitters.isdisjoint(no_entry)
        assert submitters.isdisjoint(drafts)
        assert no_entry.isdisjoint(drafts)

    async def test_counts_match_query_lengths(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        for seg in BroadcastSegment:
            count = await count_audience(db_session, seg)
            rows = await query_audience(db_session, seg)
            assert count == len(rows), f"mismatch for {seg.value}"

    async def test_count_all_audiences(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        counts = await count_all_audiences(db_session)
        assert counts[BroadcastSegment.SUBMITTERS] == 2
        assert counts[BroadcastSegment.NO_ENTRY] == 1
        assert counts[BroadcastSegment.DRAFT_HOLDERS] == 1

    async def test_inactive_user_excluded(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        # Inactive user has zero entries — would land in NO_ENTRY without
        # the is_active filter. Verify the filter excludes them.
        rows = await query_audience(db_session, BroadcastSegment.NO_ENTRY)
        assert "inactive@example.com" not in {r.email for r in rows}

    async def test_onboarding_incomplete_excluded(
        self, db_session: AsyncSession, four_segment_archetypes: dict[str, User]
    ):
        rows = await query_audience(db_session, BroadcastSegment.NO_ENTRY)
        assert "incomplete@example.com" not in {r.email for r in rows}


# ===========================================================================
# HTTP-level tests — endpoint surface
# ===========================================================================
@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _make_user(
        db_session, email="admin@example.com", is_admin=True
    )


@pytest_asyncio.fixture
async def non_admin_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="regular@example.com")


@pytest_asyncio.fixture
async def client_as_admin(
    db_session: AsyncSession, admin_user: User
):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_admin_user] = lambda: admin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_as_non_admin(
    db_session: AsyncSession, non_admin_user: User
):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: non_admin_user
    # IMPORTANT: do NOT override get_admin_user — let the real dependency
    # run and reject the non-admin user with 403.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestAudienceEndpoint:
    async def test_returns_counts(
        self,
        client_as_admin: AsyncClient,
        four_segment_archetypes: dict[str, User],
    ):
        # +1 admin user counts as NO_ENTRY (has zero entries). So the
        # fixture sees 2 NO_ENTRY users total: noentry + admin.
        response = await client_as_admin.get("/api/admin/broadcasts/audience")
        assert response.status_code == 200
        body = response.json()
        assert body["submitters"] == 2
        assert body["no_entry"] == 2  # noentry@ + admin@
        assert body["draft_holders"] == 1


@pytest.mark.asyncio
class TestBroadcastSendEndpoint:
    async def test_dry_run_does_not_send(
        self,
        client_as_admin: AsyncClient,
        four_segment_archetypes: dict[str, User],
        monkeypatch,
    ):
        call_count = {"n": 0}

        async def fake_send(**kwargs):
            call_count["n"] += 1

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        response = await client_as_admin.post(
            "/api/admin/broadcasts",
            json={"segment": "submitters", "dry_run": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["audience_count"] == 2
        assert body["sent"] == 0
        assert body["failed"] == 0
        # Sample preview surfaced.
        assert set(body["sample_emails"]) == {
            "submitter@example.com",
            "both@example.com",
        }
        # NO sends happened.
        assert call_count["n"] == 0

    async def test_real_send_calls_send_per_recipient(
        self,
        client_as_admin: AsyncClient,
        four_segment_archetypes: dict[str, User],
        monkeypatch,
    ):
        recipients: list[str] = []

        async def fake_send(**kwargs):
            recipients.append(kwargs["to_email"])

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        response = await client_as_admin.post(
            "/api/admin/broadcasts",
            json={"segment": "submitters", "dry_run": False},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is False
        assert body["audience_count"] == 2
        assert body["sent"] == 2
        assert body["failed"] == 0
        # Each audience member got one send.
        assert set(recipients) == {
            "submitter@example.com",
            "both@example.com",
        }

    async def test_real_send_writes_one_audit_event(
        self,
        db_session: AsyncSession,
        client_as_admin: AsyncClient,
        four_segment_archetypes: dict[str, User],
        admin_user: User,
        monkeypatch,
    ):
        async def fake_send(**kwargs):
            pass  # no-op

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        await client_as_admin.post(
            "/api/admin/broadcasts",
            json={"segment": "draft_holders", "dry_run": False},
        )

        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "admin.broadcast_sent"
                )
            )
        ).scalars().all()
        assert len(events) == 1
        event = events[0]
        assert event.actor_user_id == admin_user.id
        assert event.event_metadata["segment"] == "draft_holders"
        assert event.event_metadata["sent"] == 1
        assert event.event_metadata["audience_count"] == 1

    async def test_dry_run_does_not_write_audit_event(
        self,
        db_session: AsyncSession,
        client_as_admin: AsyncClient,
        four_segment_archetypes: dict[str, User],
        monkeypatch,
    ):
        async def fake_send(**kwargs):
            pass

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        await client_as_admin.post(
            "/api/admin/broadcasts",
            json={"segment": "submitters", "dry_run": True},
        )
        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "admin.broadcast_sent"
                )
            )
        ).scalars().all()
        assert len(events) == 0


@pytest.mark.asyncio
class TestTestSendEndpoint:
    async def test_default_to_admin_email(
        self,
        client_as_admin: AsyncClient,
        admin_user: User,
        monkeypatch,
    ):
        captured = {}

        async def fake_send(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        response = await client_as_admin.post(
            "/api/admin/broadcasts/test",
            json={"segment": "submitters"},  # no to_email override
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sent"] is True
        assert body["to_email"] == admin_user.email
        # The send function was called once.
        assert captured["to_email"] == admin_user.email
        assert captured["segment"] == BroadcastSegment.SUBMITTERS

    async def test_explicit_to_email_override(
        self,
        client_as_admin: AsyncClient,
        monkeypatch,
    ):
        captured = {}

        async def fake_send(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        response = await client_as_admin.post(
            "/api/admin/broadcasts/test",
            json={
                "segment": "draft_holders",
                "to_email": "personal@gmail.example",
            },
        )
        assert response.status_code == 200
        assert response.json()["to_email"] == "personal@gmail.example"
        assert captured["to_email"] == "personal@gmail.example"

    async def test_no_audit_event_on_test_send(
        self,
        db_session: AsyncSession,
        client_as_admin: AsyncClient,
        monkeypatch,
    ):
        async def fake_send(**kwargs):
            pass

        monkeypatch.setattr(
            "app.api.admin.send_broadcast_email", fake_send
        )
        await client_as_admin.post(
            "/api/admin/broadcasts/test",
            json={"segment": "submitters"},
        )
        events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "admin.broadcast_sent"
                )
            )
        ).scalars().all()
        assert len(events) == 0


@pytest.mark.asyncio
class TestAdminGate:
    async def test_audience_endpoint_rejects_non_admin(
        self, client_as_non_admin: AsyncClient
    ):
        response = await client_as_non_admin.get(
            "/api/admin/broadcasts/audience"
        )
        assert response.status_code == 403

    async def test_test_endpoint_rejects_non_admin(
        self, client_as_non_admin: AsyncClient
    ):
        response = await client_as_non_admin.post(
            "/api/admin/broadcasts/test",
            json={"segment": "submitters"},
        )
        assert response.status_code == 403

    async def test_broadcast_endpoint_rejects_non_admin(
        self, client_as_non_admin: AsyncClient
    ):
        response = await client_as_non_admin.post(
            "/api/admin/broadcasts",
            json={"segment": "submitters", "dry_run": True},
        )
        assert response.status_code == 403
