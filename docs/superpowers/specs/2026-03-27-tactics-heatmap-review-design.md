# Tactics Detection, Danger Heatmap & Post-Game Review

## Summary

Detect and label tactical patterns (fork, pin, skewer, discovered attack) on both sides. Overlay a danger heatmap on threatened squares. Provide a post-game review comparing player moves vs engine best.

## Feature 1: Tactics Detection

### New file: `core/tactics.py`

Pure python-chess module. No engine calls — analyzes board state only.

#### `classify_tactic(board, move) -> str or None`

Given a board and a move (before being played), determine if the move creates a tactic:

- **Fork**: after pushing the move, the moved piece attacks 2+ enemy pieces worth more than a pawn (or attacks king + any piece).
- **Pin**: after pushing the move, an allied sliding piece (bishop, rook, queen) pins an enemy piece against the enemy king or a higher-value piece. Check along rank/file/diagonal from the allied piece through an enemy piece to the king.
- **Skewer**: after pushing the move, an allied sliding piece attacks a valuable enemy piece which, if moved, exposes a piece behind it along the same line.
- **Discovered attack**: the moved piece leaves a line open for another allied piece to attack an enemy piece that wasn't attacked before the move.

Return the first match in priority order: `"Fork"`, `"Pin"`, `"Skewer"`, `"Disc+"`, or `None`.

#### `find_opponent_threats(board) -> list[dict]`

Analyze the current position for tactics the opponent has available. For each of the opponent's legal moves, call `classify_tactic(board, move)` from their perspective. Return a list of `{"move_san": str, "move_uci": str, "tactic": str}` for moves that have a tactic, limited to the top 3 most dangerous (prioritize by piece value threatened).

### Integration in `main.py`

**Offensive**: After finding the best move, call `classify_tactic(board, best_move)`. If not None, use it as the arrow label instead of no label (e.g., `reader.draw_arrow(..., label="Fork")`). Print in console too.

**Defensive**: Before analysis on our turn, call `find_opponent_threats(board)`. If any found, print warning. With `--heatmap`, the threatened squares get highlighted (see Feature 2).

## Feature 2: Danger Heatmap (`--heatmap` flag)

### New CLI flag

`--heatmap`: Enable danger square highlighting. Off by default.

### New method: `board_reader.draw_heatmap(squares)`

`squares`: list of algebraic square names (e.g., `["e4", "d5"]`).

Draws semi-transparent red rectangles over the specified squares using the same SVG overlay approach as arrows. Uses `<rect>` elements with class `chess-detector-heatmap`.

Visual: `rgba(255, 0, 0, 0.25)` fill, no border. Squares where our pieces are under attack.

### `clear_arrows()` update

Also remove elements with class `chess-detector-heatmap` (in addition to `chess-detector-arrow`).

### Integration in `main.py`

On our turn, before drawing move arrows:
1. Find all squares where we have a piece that is attacked by the opponent: `board.is_attacked_by(not board.turn, sq)` for each square with our piece.
2. Call `reader.draw_heatmap(threatened_squares)`.
3. Only when `--heatmap` is active.

## Feature 3: Post-Game Review (`--review` flag)

### New CLI flag

`--review`: Enable post-game review. Off by default.

### Tracking actual moves played

In the main loop, when the FEN changes and it's NOW the opponent's turn (meaning we just played), determine what move we actually made:

```python
prev_board = chess.Board(previous_fen)
for move in prev_board.legal_moves:
    prev_board.push(move)
    if prev_board.fen().split()[:4] == current_fen.split()[:4]:
        actual_move = move
        break
    prev_board.pop()
```

Store in `game_moves` list: `{"fen": str, "played_san": str, "played_uci": str, "engine_best_san": str, "engine_best_eval": int}`.

The engine_best info is already computed during our turn analysis — just save it before the FEN moves on.

### Post-game analysis

When game over is detected and `--review` is active:

1. For each move in `game_moves`, re-analyze the position quickly (depth 14, time 1s) to get eval of the move actually played (push the played move, analyze resulting position at depth 1 for a quick eval).
2. Compute delta = `engine_best_eval - played_eval` for each move.
3. Classify:
   - delta < 10cp: Perfect
   - delta < 50cp: Good
   - delta < 100cp: Inaccuracy
   - delta < 300cp: Mistake
   - delta >= 300cp: Blunder
4. Print summary:

```
=== POST-GAME REVIEW ===
Moves: 32 | Accuracy: 87%
Perfect: 18 | Good: 8 | Inaccuracy: 4 | Mistake: 2 | Blunder: 0

Worst: move 14 Bxf7?? (lost 3.2 pawns)
Best:  move 8  Nd5!! (brilliant sacrifice)
```

### Engine reuse

Use the main `engine` (not premove_engine) for review analysis since the game is over and no real-time analysis is needed.

## Files affected

| File | Change |
|---|---|
| `core/tactics.py` | **New** — `classify_tactic()`, `find_opponent_threats()` |
| `core/board_reader.py` | New `draw_heatmap()`, update `clear_arrows()` |
| `core/main.py` | `--heatmap` and `--review` flags, tactics integration, move tracking, post-game review |

## What does NOT change

- `engine.py` — no changes
- `config.py` — no changes (flags are CLI-only)
- `brilliant.py` — untouched
- `style.py` — untouched
- Existing arrow/mate/premove behavior — untouched
