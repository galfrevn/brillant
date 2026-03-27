# Deep Mate Sequences & Enhanced Premoves — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deeper engine analysis with full mate sequence arrows and multi-premove visualization.

**Architecture:** Bump Stockfish depth to 22, add PV-UCI to engine output, add `draw_move_sequence()` to board_reader for multi-arrow rendering, update main loop to use sequences for mates and draw premoves for top 3 opponent responses.

**Tech Stack:** Python, python-chess, Stockfish UCI, Chrome DevTools Protocol (JS injection)

---

## File Structure

| File | Role | Change |
|------|------|--------|
| `core/config.py` | Default config | depth 16→22, add `engine_time` field |
| `core/engine.py` | Stockfish wrapper | Return `pv_uci` in tuple, use `engine_time` |
| `core/board_reader.py` | Arrow rendering | New `draw_move_sequence()` method |
| `core/main.py` | Main loop | Mate sequences, enhanced premoves, new tuple unpacking |
| `core/brilliant.py` | Brilliant detection | Update tuple unpacking (add `_` for pv_uci) |

---

### Task 1: Config — bump depth and add engine_time

**Files:**
- Modify: `core/config.py:7-20`

- [ ] **Step 1: Update DEFAULT_CONFIG**

In `core/config.py`, change the `DEFAULT_CONFIG` dict:

```python
DEFAULT_CONFIG = {
    "stockfish_path": "../stockfish/stockfish.exe",
    "depth": 22,
    "engine_time": 5,
    "threads": 2,
    "hash_size": 128,
    "multipv": 5,
    "poll_interval": 0.3,
    "confidence": 0.75,
    "hash_threshold": 5,
    "eval_gap": 150,
    "min_eval": -50,
    "board_region": None,
    "player_color": "white",
}
```

Two changes: `"depth": 16` → `"depth": 22`, and add `"engine_time": 5` after depth.

- [ ] **Step 2: Commit**

```bash
git add core/config.py
git commit -m "feat: bump default depth to 22, add engine_time config"
```

---

### Task 2: Engine — return PV in UCI format and use engine_time

**Files:**
- Modify: `core/engine.py:6,17-50`

- [ ] **Step 1: Add engine_time parameter to __init__**

In `core/engine.py`, update `__init__` to accept and store `engine_time`:

```python
def __init__(self, path="stockfish/stockfish.exe", depth=20, threads=2, hash_size=128, engine_time=5):
    self.path = path
    self.depth = depth
    self.engine_time = engine_time
    self.threads = threads
    self.hash_size = hash_size
    self._start_engine()
```

- [ ] **Step 2: Update analyze_top_moves to use engine_time and return pv_uci**

Replace the `analyze_top_moves` method body:

```python
def analyze_top_moves(self, fen, num_moves=5):
    board = chess.Board(fen)
    try:
        results = self.engine.analyse(
            board,
            chess.engine.Limit(depth=self.depth, time=self.engine_time),
            multipv=num_moves,
        )
    except (chess.engine.EngineTerminatedError, chess.engine.EngineError, Exception):
        try:
            self._start_engine()
        except Exception:
            pass
        return []

    moves = []
    for info in results:
        if "pv" not in info or not info["pv"]:
            continue
        move = info["pv"][0]
        move_uci = move.uci()
        move_san = board.san(move)
        score = info["score"].white()
        eval_cp = score.score(mate_score=100000)
        mate_in = score.mate()

        # Convert full PV to SAN and UCI
        pv_san = []
        pv_uci = []
        temp = board.copy()
        for m in info["pv"]:
            pv_san.append(temp.san(m))
            pv_uci.append(m.uci())
            temp.push(m)

        moves.append((move_uci, move_san, eval_cp, mate_in, pv_san, pv_uci))

    return moves
```

Key changes: `time=10` → `time=self.engine_time`, add `pv_uci` list built alongside `pv_san`, append it to the tuple.

- [ ] **Step 3: Commit**

```bash
git add core/engine.py
git commit -m "feat: engine returns pv_uci, uses configurable engine_time"
```

---

### Task 3: Update callers for new 6-element tuple

**Files:**
- Modify: `core/brilliant.py:86-101`
- Modify: `core/main.py:61,74,306,372`

- [ ] **Step 1: Update brilliant.py unpacking**

In `core/brilliant.py` line 100, change:

```python
best_uci, best_san, eval_1 = top_moves[0][:3]
```

No change needed — it already uses `[:3]` slice, so the extra element is ignored. Same for `eval_2 = top_moves[1][2]`. **No action required.**

- [ ] **Step 2: Update main.py — analyze_premoves unpacking**

In `core/main.py` line 61, change:

```python
for i, (opp_uci, opp_san, opp_eval, opp_mate, _) in enumerate(opp_moves[:3]):
```

to:

```python
for i, (opp_uci, opp_san, opp_eval, opp_mate, _, _) in enumerate(opp_moves[:3]):
```

Line 74, change:

```python
resp_uci, resp_san, resp_eval, resp_mate, _ = responses[0]
```

to:

```python
resp_uci, resp_san, resp_eval, resp_mate, _, _ = responses[0]
```

- [ ] **Step 3: Update main.py — main loop unpacking**

Line 306, change:

```python
best_uci, best_san, best_eval, best_mate, best_pv = top_moves[0]
```

to:

```python
best_uci, best_san, best_eval, best_mate, best_pv, best_pv_uci = top_moves[0]
```

Line 372, change:

```python
for m_uci, m_san, m_eval, m_mate, m_pv in top_moves:
```

to:

```python
for m_uci, m_san, m_eval, m_mate, m_pv, _ in top_moves:
```

- [ ] **Step 4: Update main.py — pass engine_time to StockfishEngine**

Line 171-176, change:

```python
engine = StockfishEngine(
    path=config["stockfish_path"],
    depth=config["depth"],
    threads=config["threads"],
    hash_size=config["hash_size"],
)
```

to:

```python
engine = StockfishEngine(
    path=config["stockfish_path"],
    depth=config["depth"],
    threads=config["threads"],
    hash_size=config["hash_size"],
    engine_time=config["engine_time"],
)
```

- [ ] **Step 5: Verify no other unpacking sites were missed**

Search for any other place that unpacks engine results:

```bash
cd core && grep -n "top_moves\|opp_moves\|responses\[" main.py brilliant.py
```

- [ ] **Step 6: Commit**

```bash
git add core/main.py core/brilliant.py
git commit -m "feat: update all callers for 6-element engine tuple"
```

---

### Task 4: board_reader — draw_move_sequence method

**Files:**
- Modify: `core/board_reader.py` (add method after `draw_arrow`, before `clear_arrows`)

- [ ] **Step 1: Add draw_move_sequence method**

Insert this method after `draw_arrow` (after line 243) and before `clear_arrows` (line 245):

```python
def draw_move_sequence(self, moves, player_color="w", our_color="#ff3333", opp_color="#888888"):
    """Draw a full PV sequence. Player moves are bold+numbered, opponent moves are dim."""
    if not moves:
        return
    # Build JSON array of moves with metadata
    move_data = []
    player_num = 0
    # Index 0 = side to move. If player_color matches side to move, even indices are ours.
    # We analyze on our turn, so index 0 is always ours.
    for i, uci in enumerate(moves):
        is_ours = (i % 2 == 0)
        if is_ours:
            player_num += 1
        move_data.append({
            "from": uci[:2],
            "to": uci[2:4],
            "ours": is_ours,
            "label": str(player_num) if is_ours else None,
        })

    import json as _json
    moves_json = _json.dumps(move_data)

    js = f"""
    (() => {{
        const board = document.querySelector('wc-chess-board');
        if (!board) return 'no-board';
        const canvas = board.querySelector('canvas');
        const target = canvas || board;
        const rect = target.getBoundingClientRect();
        if (rect.width === 0) return 'no-rect';
        const sqSize = rect.width / 8;
        const flipped = board.hasAttribute('flipped') ||
                        (board.getAttribute('class') || '').includes('flipped');

        function sqToXY(sq) {{
            const file = sq.charCodeAt(0) - 97;
            const rank = parseInt(sq[1]) - 1;
            let x, y;
            if (flipped) {{
                x = rect.left + (7 - file + 0.5) * sqSize;
                y = rect.top + (rank + 0.5) * sqSize;
            }} else {{
                x = rect.left + (file + 0.5) * sqSize;
                y = rect.top + (7 - rank + 0.5) * sqSize;
            }}
            return [x, y];
        }}

        let svg = document.getElementById('chess-detector-arrows');
        if (!svg) {{
            svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.id = 'chess-detector-arrows';
            svg.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:99999;';
            document.body.appendChild(svg);
        }}

        // Arrowhead markers for both colors
        let defs = svg.querySelector('defs');
        if (!defs) {{
            defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            svg.appendChild(defs);
        }}
        function ensureMarker(id, color) {{
            if (document.getElementById(id)) return;
            const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
            marker.id = id;
            marker.setAttribute('markerWidth', '10');
            marker.setAttribute('markerHeight', '7');
            marker.setAttribute('refX', '10');
            marker.setAttribute('refY', '3.5');
            marker.setAttribute('orient', 'auto');
            marker.setAttribute('markerUnits', 'strokeWidth');
            const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
            poly.setAttribute('points', '0 0, 10 3.5, 0 7');
            poly.setAttribute('fill', color);
            marker.appendChild(poly);
            defs.appendChild(marker);
        }}
        ensureMarker('chess-seq-arrow-ours', '{our_color}');
        ensureMarker('chess-seq-arrow-opp', '{opp_color}');

        const moves = {moves_json};
        for (const m of moves) {{
            const [x1, y1] = sqToXY(m.from);
            const [x2, y2] = sqToXY(m.to);

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x1);
            line.setAttribute('y1', y1);
            line.setAttribute('x2', x2);
            line.setAttribute('y2', y2);

            if (m.ours) {{
                line.setAttribute('stroke', '{our_color}');
                line.setAttribute('stroke-width', '12');
                line.setAttribute('stroke-opacity', '0.8');
                line.setAttribute('marker-end', 'url(#chess-seq-arrow-ours)');
            }} else {{
                line.setAttribute('stroke', '{opp_color}');
                line.setAttribute('stroke-width', '6');
                line.setAttribute('stroke-opacity', '0.4');
                line.setAttribute('marker-end', 'url(#chess-seq-arrow-opp)');
            }}
            line.setAttribute('stroke-linecap', 'round');
            line.classList.add('chess-detector-arrow');
            svg.appendChild(line);

            if (m.label) {{
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;
                const r = sqSize * 0.2;

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', mx);
                circle.setAttribute('cy', my);
                circle.setAttribute('r', r);
                circle.setAttribute('fill', '{our_color}');
                circle.classList.add('chess-detector-arrow');
                svg.appendChild(circle);

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', mx);
                text.setAttribute('y', my);
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('dominant-baseline', 'central');
                text.setAttribute('fill', 'white');
                text.setAttribute('font-size', r * 1.6);
                text.setAttribute('font-weight', 'bold');
                text.setAttribute('font-family', 'Arial, sans-serif');
                text.textContent = m.label;
                text.classList.add('chess-detector-arrow');
                svg.appendChild(text);
            }}
        }}
        return true;
    }})()
    """
    return self._eval_js(js)
```

- [ ] **Step 2: Commit**

```bash
git add core/board_reader.py
git commit -m "feat: add draw_move_sequence for multi-arrow PV rendering"
```

---

### Task 5: main.py — mate sequence visualization

**Files:**
- Modify: `core/main.py:346-365`

- [ ] **Step 1: Replace mate arrow drawing with sequence**

Replace the mate handling block (lines 346-365). Current code:

```python
elif best_mate is not None:
    mate_moves = abs(best_mate)
    our_mate = (player_turn == "w" and best_mate > 0) or \
               (player_turn == "b" and best_mate < 0)
    if our_mate:
        our_moves = [best_pv[i] for i in range(0, len(best_pv), 2)]
        sequence = " → ".join(our_moves)
        print(f"{Fore.MAGENTA}{Style.BRIGHT}")
        print(f"  MATE in {mate_moves}!")
        print(f"  Premoves: {sequence}")
        print(f"{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Opponent has mate in {mate_moves}. "
              f"Best: {best_san}{Style.RESET_ALL}")

    # Arrow for the first move only
    if args.assist:
        color = "#ff3333" if our_mate else "#cc0000"
        reader.draw_arrow(best_uci[:2], best_uci[2:4], color=color, width=12,
                          label=f"M{mate_moves}")
```

Replace with:

```python
elif best_mate is not None:
    mate_moves = abs(best_mate)
    our_mate = (player_turn == "w" and best_mate > 0) or \
               (player_turn == "b" and best_mate < 0)
    if our_mate:
        our_moves = [best_pv[i] for i in range(0, len(best_pv), 2)]
        sequence = " → ".join(our_moves)
        print(f"{Fore.MAGENTA}{Style.BRIGHT}")
        print(f"  MATE in {mate_moves}!")
        print(f"  Premoves: {sequence}")
        print(f"{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Opponent has mate in {mate_moves}. "
              f"Best: {best_san}{Style.RESET_ALL}")

    # Draw full mate sequence as numbered arrows
    if args.assist:
        if our_mate:
            reader.draw_move_sequence(
                best_pv_uci, player_turn,
                our_color="#ff3333", opp_color="#888888")
        else:
            reader.draw_move_sequence(
                best_pv_uci, player_turn,
                our_color="#cc0000", opp_color="#888888")
```

- [ ] **Step 2: Commit**

```bash
git add core/main.py
git commit -m "feat: draw full mate sequence as numbered arrow chain"
```

---

### Task 6: main.py — enhanced premoves

**Files:**
- Modify: `core/main.py:46-90`

- [ ] **Step 1: Update analyze_premoves to draw 3 premove arrows**

Replace the `analyze_premoves` function entirely:

```python
def analyze_premoves(fen, engine, reader, args, config):
    """Analyze opponent's likely moves and suggest premove responses."""
    board = chess.Board(fen)

    # Get opponent's top moves
    opp_moves = engine.analyze_top_moves(fen, 3)
    if not opp_moves:
        return

    if args.assist:
        reader.clear_arrows()

    print(f"[{ts()}] {Fore.BLUE}Premove suggestions:{Style.RESET_ALL}")

    # Visual weight per likelihood rank
    arrow_styles = [
        {"width": 10, "opacity": 0.8},   # most likely
        {"width": 7,  "opacity": 0.5},   # possible
        {"width": 5,  "opacity": 0.3},   # unlikely
    ]

    for i, (opp_uci, opp_san, opp_eval, opp_mate, _, _) in enumerate(opp_moves[:3]):
        try:
            opp_move = chess.Move.from_uci(opp_uci)
            board.push(opp_move)
            response_fen = board.fen()

            # Analyze our best response (quick)
            responses = engine.analyze_top_moves(response_fen, 1)
            board.pop()

            if not responses:
                continue

            resp_uci, resp_san, resp_eval, resp_mate, _, _ = responses[0]

            if resp_mate is not None:
                eval_display = f"mate {abs(resp_mate)}"
            else:
                eval_display = f"{resp_eval / 100:+.1f}"

            prefix = "  →" if i == 0 else "   "
            likelihood = ["(likely)", "(possible)", "(unlikely)"][i]
            print(f"{prefix} If {opp_san} {likelihood} → premove {Fore.GREEN}{resp_san}{Style.RESET_ALL} ({eval_display})")

            if args.assist:
                style = arrow_styles[i]
                reader.draw_arrow(
                    resp_uci[:2], resp_uci[2:4],
                    color="#3399ff", width=style["width"])

        except Exception:
            continue
```

Note: the opacity per-arrow isn't supported by the current `draw_arrow` method (it hardcodes `stroke-opacity: 0.8`). Since this is a minor visual detail and adding an opacity param would complicate the signature, we keep the width differentiation as the primary visual hierarchy. The width difference (10 vs 7 vs 5) is sufficient to distinguish likelihood.

- [ ] **Step 2: Commit**

```bash
git add core/main.py
git commit -m "feat: draw premove arrows for top 3 opponent responses"
```

---

### Task 7: Verify everything works together

- [ ] **Step 1: Run a syntax check**

```bash
cd core && python -c "import main" 2>&1 || echo "Import failed"
```

This will fail if there are syntax errors or broken imports. Expected: no output (clean import) or a connection error from ChessBoardReader (which is fine — means syntax is OK).

- [ ] **Step 2: Verify engine tuple shape**

```bash
cd core && python -c "
from engine import StockfishEngine
e = StockfishEngine(depth=10, engine_time=2)
moves = e.analyze_top_moves('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1', 3)
for m in moves:
    print(f'len={len(m)}, uci={m[0]}, san={m[1]}, pv_san={m[4][:3]}, pv_uci={m[5][:3]}')
e.close()
"
```

Expected: each tuple has length 6, pv_uci contains UCI strings like `['e7e5', 'g1f3', ...]`.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: deep mate sequences and enhanced premoves complete"
```
