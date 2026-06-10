# Scoring System

This document describes the configurable scoring system for the Predictor v2 application.

## Overview

The scoring system calculates points for two types of predictions:
1. **Match Predictions** - Predicting the score of individual matches
2. **Advancement Predictions** - Predicting which teams advance through the tournament

All scoring rules are configurable via the YAML configuration file at `config/worldcup2026.yml`.

## Configuration

### File Location

```
config/worldcup2026.yml
```

### Scoring Section

```yaml
scoring:
  # Scoring mode: "fixed" | "hybrid" (legacy) | "logarithmic" (default)
  mode: "logarithmic"

  match:
    correct_outcome: 5      # Points for correct 1-X-2 prediction
    exact_score: 10         # Bonus points for exact score
    rarity_cap: 10          # Max rarity bonus (logarithmic / hybrid modes)
    hybrid_cap: 10          # Legacy alias, read as fallback

  advancement:
    group_advance: 10       # Team advances from group
    group_position: 5       # Correct group position (1st/2nd)
    round_of_32: 20
    round_of_16: 30
    quarter_final: 40
    semi_final: 50
    final: 75
    winner: 100

  phase_multipliers:
    phase_1: 1.0            # Pre-tournament predictions (full points)
    phase_2: 0.7            # Post-group stage predictions (70% points)
```

## Scoring Modes

### Fixed Scoring

In **fixed** mode, players receive flat points for correct predictions regardless of how many other players got it right.

**Example:**
- Correct outcome: 5 points
- Exact score: +10 points
- Total for exact score: 15 points

### Logarithmic Scoring (default)

In **logarithmic** mode, players receive base points plus a rarity bonus
derived from **Shannon surprisal** — bits of information the crowd's prior
was wrong by. Predicting outcomes the room avoided is rewarded; riding
consensus pays nothing extra.

**Formula:**

```
R = min(rarity_cap, round(alpha * log2(1 / (2f))))   for f < 0.5
R = 0                                                for f >= 0.5

where  f     = correct_predictors / total_predictors
       alpha = 10 / log2(15) ≈ 2.5596
```

`total_predictors` is the number of users who submitted a prediction for
*that fixture* ("the room that showed up"), not the global active-user
count. `correct_predictors` is the subset of those who picked the actual
outcome.

**Key properties:**

- **Gated at 50%.** Consensus picks (≥ half the predictors correct) earn
  no rarity premium — base points only.
- **Anchored.** Alpha is chosen so that a uniquely correct pick out of 30
  predictors (f = 1/30 ≈ 3.3%) hits the cap of 10. Rarer picks stay
  capped.
- **Scale-invariant.** The same fraction `f` produces the same bonus
  regardless of pool size — so the published band table below applies
  whether there are 12, 30, or 60 predictors.

**Published bonus by % of predictors who picked the correct outcome:**

| f (correct %) | Rarity bonus R |
|---:|---:|
| > 43.67% | 0 |
| 33.31% – 43.67% | 1 |
| 25.41% – 33.31% | 2 |
| 19.38% – 25.41% | 3 |
| 14.78% – 19.38% | 4 |
| 11.28% – 14.78% | 5 |
| 8.60% – 11.28% | 6 |
| 6.56% – 8.60% | 7 |
| 5.00% – 6.56% | 8 |
| 3.82% – 5.00% | 9 |
| ≤ 3.82% | 10 (cap) |

**Worked examples (30 predictors):**

- Uniquely correct (1 of 30, f ≈ 3.3%): 5 + 10 + (10 if exact) = **15 or 25**
- One-in-ten correct (3 of 30, f = 10%): 5 + 6 = **11** (or **21** with exact)
- Three-way split (10 of 30, f ≈ 33%): 5 + 1 = **6** (or **16** with exact)
- Half-right (15 of 30, f = 50%): 5 + 0 = **5** (or **15** with exact)
- Unanimous correct (30 of 30): 5 + 0 = **5** (or **15** with exact)

**Why logarithmic?** Log scoring is the unique *proper scoring rule* whose
payoff depends only on the probability assigned to the realized outcome
(Good, 1952). It treats "halving the underdog odds" as a fixed-size reward
— going from 20% to 10% adds the same ~2.5 points as going from 10% to 5%
— which matches how forecasters actually think about belief revision.

### Hybrid Scoring (legacy)

In **hybrid** mode, the rarity bonus uses integer division instead of a log:

```
R = min(hybrid_cap, total_predictors // correct_predictors)
```

Kept registered for backward compatibility with any deployment still
configured with `mode: "hybrid"`. The integer-divide formula has visible
plateaus and gaps that the logarithmic curve smooths out; logarithmic
should be preferred for new deployments.

## Match Prediction Points

| Prediction | Fixed Mode | Logarithmic / Hybrid Mode |
|------------|-----------|---------------------------|
| Correct outcome (1-X-2) | 5 pts | 5 pts + rarity bonus (0-10 pts) |
| Exact score bonus | +10 pts | +10 pts |
| **Maximum per match** | 15 pts | 25 pts |

### Outcome Types
- **1** = Home team wins
- **X** = Draw
- **2** = Away team wins

## Advancement Prediction Points

Points are awarded when a team reaches at least the predicted stage.

| Stage | Phase 1 Points | Phase 2 Points (70%) |
|-------|---------------|---------------------|
| Group advance | 10 | 7 |
| Correct group position | 5 | 3.5 |
| Round of 32 | 20 | 14 |
| Round of 16 | 30 | 21 |
| Quarter-final | 40 | 28 |
| Semi-final | 50 | 35 |
| Final | 75 | 52.5 |
| Winner | 100 | 70 |

**Timing (lineup-based, v2.161.0):** "reached stage X" credit fires the
moment a team is seeded into a stage-X fixture — when FIFA publishes the
round's lineup and the fixtures sync — not when that stage's match is
played. Only the `winner` credit waits for the final to be FINISHED and
scored. Group-stage match points still pay on match completion.

**Note:** Phase 2 predictions (made after group stage) receive reduced points because players have more information when making predictions.

## API Endpoint

You can fetch the current scoring configuration via the API:

```
GET /api/leaderboard/scoring-rules
```

**Response:**
```json
{
  "mode": "logarithmic",
  "available_modes": ["fixed", "hybrid", "logarithmic"],
  "match": {
    "correct_outcome": 5,
    "exact_score": 10,
    "rarity_cap": 10,
    "hybrid_cap": 10
  },
  "advancement": {
    "group_advance": 10,
    "group_position": 5,
    "round_of_32": 20,
    "round_of_16": 30,
    "quarter_final": 40,
    "semi_final": 50,
    "final": 75,
    "winner": 100
  },
  "phase_multipliers": {
    "phase_1": 1.0,
    "phase_2": 0.7
  }
}
```

## Extending the Scoring System

To add a new scoring mode:

### 1. Create a Strategy Class

In `backend/app/services/scoring.py`:

```python
class MyCustomScoring:
    """Description of the scoring mode."""

    def calculate(
        self,
        prediction: MatchPrediction,
        score: Score,
        config: dict[str, Any],
        total_predictors: int,
        correct_predictors: int,
    ) -> tuple[int, bool, bool]:
        """
        Calculate match points.

        Args:
            prediction: User's prediction
            score: Actual match result
            config: Match scoring config from YAML
            total_predictors: Number of users who submitted a prediction
                for this fixture
            correct_predictors: Number of those who picked the actual outcome

        Returns:
            Tuple of (points, correct_outcome, exact_score)
        """
        # Your scoring logic here
        outcome_points = config.get("correct_outcome", 5)
        exact_points = config.get("exact_score", 10)

        correct_outcome = prediction.predicted_outcome == score.outcome
        exact_score = (
            prediction.home_score == score.final_home_score
            and prediction.away_score == score.final_away_score
        )

        points = 0
        if correct_outcome:
            points += outcome_points
            # Add custom bonus logic here
        if exact_score:
            points += exact_points

        return points, correct_outcome, exact_score
```

### 2. Register the Strategy

Add to the `SCORING_STRATEGIES` dict:

```python
SCORING_STRATEGIES: dict[str, MatchScoringStrategy] = {
    "fixed": FixedScoring(),
    "hybrid": HybridScoring(),
    "logarithmic": LogarithmicScoring(),
    "my_custom": MyCustomScoring(),  # Add your new mode
}
```

### 3. Update Config

Set the mode in `config/worldcup2026.yml`:

```yaml
scoring:
  mode: "my_custom"
```

### 4. Add Tests

Add test cases in `backend/tests/test_scoring.py` to verify your scoring logic.

## Testing

Run scoring tests:

```bash
# In docker
docker-compose exec backend pytest tests/test_scoring.py -v

# Or copy test file first if tests dir isn't mounted
docker cp backend/tests/test_scoring.py predictor-backend:/app/tests/
docker-compose exec backend pytest tests/test_scoring.py -v
```

## Implementation Details

### Files

| File | Purpose |
|------|---------|
| `config/worldcup2026.yml` | Scoring configuration |
| `backend/app/services/scoring.py` | Scoring logic and strategies |
| `backend/app/api/leaderboard.py` | Scoring rules API endpoint |
| `backend/tests/test_scoring.py` | Scoring tests |

### Key Functions

- `get_scoring_config()` - Load and merge config with defaults
- `get_scoring_strategy(mode)` - Get scoring strategy by name
- `calculate_match_points()` - Calculate points for a match prediction
- `calculate_advancement_points()` - Calculate points for team advancement
- `calculate_user_points()` - Calculate total points for a user

### Default Values

If the config file is missing or incomplete, the system uses these defaults:

```python
DEFAULT_SCORING_CONFIG = {
    "mode": "logarithmic",
    "match": {
        "correct_outcome": 5,
        "exact_score": 10,
        "hybrid_cap": 10,
        "rarity_cap": 10,
    },
    "advancement": {
        "group_advance": 10,
        "group_position": 5,
        "round_of_32": 20,
        "round_of_16": 30,
        "quarter_final": 40,
        "semi_final": 50,
        "final": 75,
        "winner": 100,
    },
    "phase_multipliers": {
        "phase_1": 1.0,
        "phase_2": 0.7,
    },
}
```

Partial configs are merged with defaults, so you only need to specify values you want to change.
