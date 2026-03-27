# Opponent ELO Adaptation, Clock Adaptation & Sound Alerts

## Summary

Read opponent's ELO and remaining clock time from chess.com DOM. Adjust premove depth/candidates by ELO, adjust analysis depth/speed by clock pressure, and play sound alerts for forced mates and brilliant moves.

## Changes

### 1. board_reader.get_state() — new fields

Extend the JS in `get_state()` to also scrape:
- **opponent_elo**: integer rating from the opponent's player info panel. Try selectors in order: `[data-cy="user-tagline"]`, `.user-tagline-rating`, text content near the opponent's name. Parse the first 3-4 digit number found. Return `null` if not found.
- **our_time**: our remaining clock time in seconds. Identify clock elements, determine which is ours based on board orientation (flipped → top clock is ours, not flipped → bottom clock is ours). Parse "MM:SS" or "M:SS.s" format to float seconds. Return `null` if not found.

New return shape:
```python
{
    "fen": str,
    "playing_as": int,
    "is_game_over": bool,
    "result": None,
    "opponent_elo": int or None,
    "our_time": float or None,
}
```

### 2. ELO-based premove adjustment in main.py

When a new game starts and `opponent_elo` is read, compute premove settings:

| ELO range | Premove candidates | Premove depth | Premove time_limit |
|---|---|---|---|
| < 1200 | 1 | 10 | 0.5s |
| 1200–1800 | 2 | 12 | 0.8s |
| > 1800 | 3 | 14 | 1s |

Store as `premove_candidates`, `premove_depth`, `premove_time` variables. Pass them into `analyze_premoves()` as parameters (instead of hardcoded `depth=14, time_limit=1`). If ELO is None, default to the >1800 tier.

`analyze_premoves()` signature changes to accept `candidates`, `depth`, `time_limit` parameters.

### 3. Clock-based analysis adaptation in main.py

Each poll cycle, read `our_time` from state. Compute depth/time overrides:

| our_time | analysis depth | engine time_limit | poll_interval |
|---|---|---|---|
| > 60s | config default (20) | config default (2s) | 0.3s |
| 30–60s | 16 | 1.5s | 0.3s |
| 10–30s | 12 | 0.8s | 0.2s |
| < 10s | 8 | 0.3s | 0.15s |

Pass overrides to `engine.analyze_top_moves(fen, multipv, depth=X, time_limit=Y)`. Adjust `poll` variable dynamically. If `our_time` is None, use config defaults.

### 4. Sound alerts in main.py

Use `winsound.Beep(frequency, duration)` (built-in on Windows).

- **Forced mate detected** (our mate, forced_mate_fens is not None): 500 Hz, 300ms single beep
- **Brilliant move detected**: 1000 Hz, 150ms beep twice (with 50ms gap)

Run beeps in a daemon thread to avoid blocking the main loop. Add `import winsound` at top of main.py.

### 5. What does NOT change

- `engine.py` — already supports depth/time_limit overrides
- `config.py` — no new config fields needed
- `brilliant.py` — untouched
- `board_reader.py` draw methods — untouched
- Forced mate arrow locking logic — untouched

## Files affected

| File | Change |
|---|---|
| `core/board_reader.py` | `get_state()` JS extended to read ELO + clock |
| `core/main.py` | ELO premove tiers, clock adaptation, winsound alerts |
