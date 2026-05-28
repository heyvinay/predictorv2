
# Project Context: The Predictor

## 1. Product Context

### Overview
**The Predictor** is a self-hosted, private web application for managing international football (soccer) prediction competitions (e.g., World Cup, Euros). It is designed for a closed group of ~30 friends. The goal is to predict match outcomes (1-X-2) and exact scores to earn points. The current competition that we are focusing on is the world cup in 2026.

### Core Philosophy
*   **High Stakes, High Reliability:** While a hobby project, it must have 100% data integrity. A crash during a match or a lost prediction is unacceptable.
*   **Game Theory Optimized:** The scoring system rewards predicting upsets without allowing "lucky guesses" to break the leaderboard.
*   **Mobile Compatible:** Users will interact via both mobile ande desktop devices. 
*   **"Wow" Factor:** The UI should feel premium, fluid, and interactive, using animations to mask data loading.

### Key Features
1.  **Auth:** Secure login, a Hybrid Auth system using fastapi-sso for login via google and standard JWT for email,password based login.
2.  **Prediction Wizard:** A clean interface for inputting all predictions for the group stage games.
    *   *Constraint:* Predictions lock rigidly 5 minutes before kickoff. People will fill in all their predictions prior to the tournament but will have a chance to change things up until 5 minutes before kick off of each game.
3.  **The Bracket:** Once the users have filled in their group stage predictions they next fill in a recursive visual tree for the knockout stages.
4.  **Scoring Engine:** A logarithmic "Shannon-surprisal" rarity-bonus scoring system is in production (default mode). See `docs/scoring-system.md` and `config/worldcup2026.yml` for the configured values; `fixed` and `hybrid` modes are also available for swap-in.
    *   *Blind Pool:* Users cannot see others' specific predictions until the match locks.
    *   *Real-time:* Scores update live as the match is played.
5.  **Analytics:** Interactive charts showing rank progression (User vs. Rival).
6. **Competition Phases**: There are two phases to the competition, Phase I is the initial group stage score + knockout bracket predictions, these are submitted before the competition starts. Phase II are the knockout bracket score predictions which are done once the bracket is known (i.e. in between the end of the group stage and the start of the knockout stage).

---

## 2. Product Guidelines

### Visual Identity
*   **Theme:** `premium-night` is the default — champagne-gold CTAs on midnight-navy canvas. A `light` theme is also registered and persisted via `localStorage['predictor:theme']`. Both are defined in `frontend/tailwind.config.js`.
*   **Palette:** High contrast. Green for win, red for loss, gold (`#D4AF37`) for premium accents / exact-score / rare-pick highlights.
*   **Typography:** Inter (body) + Manrope (display / scores) under `premium-night`; Bebas Neue + DM Sans under `light`. Both font bundles are loaded in `app.html` and gated per theme in `app.css`.

### UX Standards
*   **Saving** If a user clicks "Save," it is important that they receive visual feedback only once the backend confirms that the update has been saved.
*   **Zero Clutter:** On mobile, show one logical group at a time. Do not show a giant Excel grid on a phone screen.
*   **Animations:** Use `svelte-motion` for state changes (e.g., rows swapping on the leaderboard).

### The Scoring Formula (The "Law")
The scoring system is configurable via `config/worldcup2026.yml` and supports multiple modes (`logarithmic` default, `fixed`, `hybrid`). The values below are the historical / proposed values from when this doc was drafted — for the *current* configured values and the full logarithmic rarity-bonus spec, see [`docs/scoring-system.md`](docs/scoring-system.md). Scoring divides into Match Prediction and Advancement Prediction.
### Match Prediction:
The current system uses 5 pts for correct result: 1-X-2 OR 15 pts for correct score

I am exploring the idea of using of a **Base + Capped Bonus** system:
$$Points = Base + \min(Cap, \frac{TotalPlayers}{CorrectPlayers})$$

*   **Base Points:** 5 (for correct Outcome: Home/Draw/Away).
*   **Exact Score Bonus:** +10 Flat points.
*   **Bonus Cap:** Max 10 points.
*   **Example:** If Brazil (Favorite) wins and everyone picks them, points = 5 + 0 = 5. If Saudi (Underdog) wins and only 1 person picks them, points = 5 + 10 (Cap) = 15.

## Advancement Prediction:
### Phase I
- 10 pts for correctly predicting a team to advance from the group stage (i.e. qualify for round of 32)
- 5 pts for each correct groups tage position of qualified teams
- 15 pts for correct round of 16 team
- 20 pts for correct quarter final team
- 40 pts for correc semi final team
- 60 pts for correct finalist
- 100 pts for correct winner
- 15 pts for each correct group stage bonus question
- 20 points for each correct knock out stage bonus question

### Phase II
- 10 pts for correct round of 16 team
- 15 pts for correct quarter final team
- 25 pts for correc semi final team
- 40 pts for correct finalist
- 70 pts for correct winner

---

## 3. Tech Stack

### Infrastructure (Self-Hosted vs Cloud)
I am on the fence between self-hosting the project or running it in a cloud machine. If I do self-host it then here are the specs of my hardware:
*   **Hardware:** Beelink Mini PC (AMD Ryzen).
*   **Orchestration:** Docker Compose (Production).
*   **Network:** Cloudflare Tunnel (Exposes local container to public web via HTTPS).
*   **Reverse Proxy:** Nginx.

### Backend (API)
*   **Framework:** **FastAPI** (Python 3.11+).
*   **ORM:** **SQLModel** (Pydantic + SQLAlchemy).
*   **Database:** **PostgreSQL 16**.
*   **Migrations:** Alembic.
*   **External Data:** Football-Data.org (live in `backend/app/services/external/football_data.py`). API-Football was evaluated and discarded.

### Frontend (Client)
*   **Framework:** **SvelteKit** 
*   **Language:** TypeScript.
*   **Styling:** Tailwind CSS + DaisyUI.
*   **State Management:** Svelte Stores (`writable`, `derived`).
*   **Visuals:** (Lightweight charts), `svelte-motion`.

---

## 4. Workflow & Standards

### File Structure (Monorepo)
This is yet to be confirmed but here is the current proposed structure:
```text
/predictor
├── /backend                 # FastAPI
│   ├── /app
│   │   ├── /models          # SQLModel Tables
│   │   ├── /services        # Scoring Logic
│   │   └── /api             # Routes
├── /frontend                # SvelteKit
│   ├── /src
│   │   ├── /lib/components  # UI Components
│   │   └── /routes          # Pages
├── /nginx                   # Proxy Config
└── docker-compose.yml
```

### Development Rules
1.  **The "Safety" Rule:** No logic changes to the Scoring Engine without a corresponding `pytest` case.
2.  **The "Mobile" Rule:** All UI components must be verified on a 375px width viewport (Chrome DevTools).
3.  **Type Safety:**
    *   Backend: Strict Pydantic models.
    *   Frontend: No `any` types in TypeScript. Define interfaces for `User`, `Match`, `Prediction`.

### Testing Strategy
*   **Unit:** `pytest` for Scoring Logic and Auth.
*   **Integration:** `vitest` for Svelte Component rendering.
*   **Manual:** "The Dry Run" - A pre-tournament test on dummy matches.
