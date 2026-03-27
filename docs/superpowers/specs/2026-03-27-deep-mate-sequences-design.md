# Deep Mate Sequences & Enhanced Premoves

## Summary

Improve analysis depth, visualize full mate sequences as numbered arrow chains, and show premoves for multiple likely opponent responses.

## Changes

### 1. Engine depth & time

- Default depth: 16 → 22
- Time limit: 10s → 5s (blitz-friendly cutoff)
- Config changes in `config.py` DEFAULT_CONFIG

### 2. Engine returns PV in UCI format

`engine.py` `analyze_top_moves` currently returns `pv_san` (list of SAN strings). Add `pv_uci` (list of UCI strings) to the return tuple so arrow drawing has coordinates.

New return shape per move:
```python
(move_uci, move_san, eval_cp, mate_in, pv_san, pv_uci)
```

All callers (`main.py`, `brilliant.py`) updated to unpack the new tuple.

### 3. New method: `board_reader.draw_move_sequence(moves, player_color)`

Draws an entire PV as a chain of arrows in a single JS injection.

**Parameters:**
- `moves`: list of UCI strings (the full PV line)
- `player_color`: `"w"` or `"b"` — determines which moves are "ours"

**Visual rules:**
- Player's moves (moves where it's their turn): red `#ff3333`, width 12, numbered labels `"1"`, `"2"`, `"3"`...
- Opponent's responses: gray `#888888`, width 6, opacity 0.4, no label
- All arrows drawn in one JS call to avoid flicker

**Numbering:** Only player moves get numbered. Move index 0 in PV is always the side-to-move, so:
- If player is side-to-move: indices 0, 2, 4... are player moves → labels 1, 2, 3...
- If player is NOT side-to-move: indices 1, 3, 5... are player moves (shouldn't happen in practice since we analyze on our turn)

### 4. Mate sequence visualization in `main.py`

When `best_mate is not None` and it's a favorable mate:
- Call `draw_move_sequence(pv_uci, player_turn)` instead of single `draw_arrow`
- Console output unchanged (already prints the sequence)

When mate is unfavorable (opponent has mate):
- Same treatment but with dark red `#cc0000` for the first move
- Show opponent's mating sequence so user can see what's coming

### 5. Enhanced premoves in `analyze_premoves()`

Current behavior: analyze top 3 opponent moves, draw 1 premove arrow for the most likely.

New behavior:
- Still analyze top 3 opponent moves
- Draw premove arrow for **all 3** responses:
  - Response to most likely: blue `#3399ff`, width 10 (same as now)
  - Response to 2nd most likely: blue `#3399ff`, width 7, opacity 0.5
  - Response to 3rd most likely: blue `#3399ff`, width 5, opacity 0.3
- Console output already shows all 3, no change needed there

### 6. What does NOT change

- Brilliant move detection logic (`brilliant.py` criteria)
- Style tracking and style-based move suggestions
- Normal (non-mate) best move display — still a single green arrow
- Game state detection, color detection, turn detection
- Arrow clearing behavior (clear before drawing new set)

## Files affected

| File | Change |
|------|--------|
| `core/config.py` | depth 16→22, time limit field |
| `core/engine.py` | Add `pv_uci` to return tuple |
| `core/board_reader.py` | New `draw_move_sequence()` method |
| `core/main.py` | Use `draw_move_sequence` for mates, enhanced premoves, unpack new tuple |
| `core/brilliant.py` | Unpack new tuple shape (add `_` for pv_uci) |
