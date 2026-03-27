# Brillant -- Chess Brilliant Move Detector

> **Disclaimer:** This project was built for educational and hackathon purposes only.
> It is **not** intended for use in competitive or rated games. Using external assistance
> during online rated play violates the terms of service of chess platforms and constitutes
> cheating. Use this tool only for learning, analysis of your own past games, or
> unrated/friendly matches where all participants consent.

## What It Does

Brillant monitors your chess.com games in real time through the Chrome DevTools Protocol.
It reads the board state directly from the page, sends positions to a local Stockfish
engine, and provides real-time analysis: brilliant move detection, full mate sequences
with premove arrows, tactical pattern recognition, danger heatmaps, and post-game
reviews.

## Features

- **Brilliant move detection** -- identifies sacrificial moves that are uniquely strong,
  non-obvious, and lead to a winning position.
- **Full mate sequences** -- when a forced checkmate exists, draws numbered arrows for
  your moves (red) and opponent responses (gray) on the board. If the mate is fully
  forced (opponent has only one legal reply at each step), arrows stay locked so you
  can premove the entire sequence.
- **Smart premoves** -- on the opponent's turn, predicts their most likely replies and
  suggests your best premove response to each (up to 3 arrows with visual weight by
  likelihood). Runs in a background thread with a dedicated Stockfish engine.
- **Tactical pattern detection** -- labels best moves with their tactic type (Fork, Pin,
  Disc+) on the arrow. Also warns you of opponent threats in the console.
- **Danger heatmap** (`--heatmap`) -- highlights squares where your pieces are under
  attack with a red semi-transparent overlay.
- **Post-game review** (`--review`) -- after the game ends, shows accuracy %, move
  classification (Perfect/Good/Inaccuracy/Mistake/Blunder), worst move, and best move.
- **ELO-adaptive analysis** -- reads opponent's rating from chess.com and adjusts
  analysis depth and premove strategy accordingly. Against lower-rated opponents, uses
  shallower analysis (faster responses). Against higher-rated opponents, deeper search.
- **Clock-adaptive analysis** -- reads your remaining time and dynamically adjusts
  analysis depth. Under 10 seconds: instant responses at depth 8.
- **Arrow overlay on board** (`--assist`) -- draws colored arrows directly on the
  chess.com board via SVG injection (green for best move, yellow for brilliant, red for
  mate, blue for premoves, cyan for style picks).
- **Parallel analysis** -- main analysis and premove analysis run on separate Stockfish
  engines in separate threads. Premoves compute while the opponent thinks.
- **Bullet mode** (`--bullet`) -- lowers analysis depth and poll interval for fast
  time controls.
- **Style learning** -- tracks your moves in SQLite, builds a player profile, and
  suggests moves that match your style alongside the engine's best.
- **Style stats** (`--stats`) -- shows your playing style summary: accuracy,
  sacrifice rate, favorite pieces, and style classification.

## Requirements

- Python 3.8+
- [Stockfish](https://stockfishchess.org/download/) chess engine binary
- Google Chrome (launched with remote debugging enabled)

## Installation

1. **Clone the repository:**

   ```
   git clone https://github.com/galfrevn/brillant.git
   cd brillant
   ```

2. **Install Python dependencies:**

   ```
   pip install -r requirements.txt
   ```

3. **Download Stockfish:**

   - Go to <https://stockfishchess.org/download/>
   - Download the binary for your platform
   - Place the executable at `stockfish/stockfish.exe` relative to the project root
     (or update the path in `config.json`)

4. **Launch Chrome with remote debugging:**

   ```
   chrome.exe --remote-debugging-port=9222 --remote-allow-origins=*
   ```

   If Chrome is already running, close it first. The tool will attempt to launch Chrome
   automatically if it cannot connect.

5. **Open chess.com** in the Chrome window and navigate to a game.

## Usage

Run from the `core/` subdirectory:

```
cd core
py main.py
```

### Common invocations

| Command                                        | Description                                 |
|------------------------------------------------|---------------------------------------------|
| `py main.py --assist`                          | Arrows + tactics + ELO/clock adaptation     |
| `py main.py --assist --heatmap`                | Arrows + danger heatmap overlay             |
| `py main.py --assist --review`                 | Arrows + post-game review on finish         |
| `py main.py --assist --heatmap --review`       | Full experience                             |
| `py main.py --bullet`                          | Bullet mode (depth 8, fast poll)            |
| `py main.py --depth 24`                        | Override analysis depth                     |
| `py main.py --stats`                           | Show playing style stats and exit           |

### CLI Flags

| Flag           | Type  | Default | Description                                      |
|----------------|-------|---------|--------------------------------------------------|
| `--port`       | int   | 9222    | Chrome remote debugging port                     |
| `--depth`      | int   | 20      | Stockfish analysis depth (overrides config)       |
| `--debug`      | flag  | off     | Print FEN and diagnostic info for each position  |
| `--assist`     | flag  | off     | Draw move arrows on the chess.com board          |
| `--heatmap`    | flag  | off     | Highlight squares where your pieces are attacked |
| `--review`     | flag  | off     | Show post-game review with accuracy stats        |
| `--bullet`     | flag  | off     | Bullet mode: depth 8, 0.2s poll interval         |
| `--stats`      | flag  | off     | Show your playing style statistics and exit       |

## How It Works

1. **Connects to Chrome** via the DevTools Protocol on `localhost:9222`.
2. **Reads the board state** by evaluating JavaScript inside the chess.com tab -- it
   calls the site's own `wc-chess-board` element API to retrieve the FEN, detects the
   board orientation, and checks for game-over modals.
3. **Reads opponent ELO and clock** from the page DOM to adapt analysis depth and
   premove strategy dynamically.
4. **Analyzes with Stockfish** using MultiPV (multiple principal variations) to get the
   top candidate moves and their evaluations. Uses two Stockfish engines in parallel:
   one for main analysis, one for premoves in a background thread.
5. **Detects brilliant moves** by checking four criteria:
   - The move is a material sacrifice (the moved piece is worth more than what it
     captures, and the destination is attacked).
   - The move is uniquely good (evaluation gap > 0.8 pawns vs. the second-best move).
   - The move is non-obvious (not a simple checkmate-in-one, recapture, or the only
     checking move).
   - The resulting position is still good for the player (eval >= -2.0).
6. **Detects tactical patterns** (forks, pins, discovered attacks) on the best move and
   labels them on the arrow. Also scans for opponent threats.
7. **Suggests premoves** on the opponent's turn by predicting their likely replies and
   computing your best response to each. Number of candidates adapts to opponent ELO.
8. **Draws arrows** (when `--assist` is active) by injecting an SVG overlay into the
   page via `Runtime.evaluate`.

## Configuration

On first run, if no `config.json` exists the tool uses sensible defaults. You can create
a `config.json` in the `core/` directory to override settings:

```json
{
  "stockfish_path": "../stockfish/stockfish.exe",
  "depth": 20,
  "engine_time": 2,
  "threads": 8,
  "hash_size": 512,
  "multipv": 3,
  "poll_interval": 0.3
}
```

## Known Limitations

- Only works with **chess.com** (not Lichess or other sites).
- Castling rights and en passant squares in the FEN are approximated -- the JS API
  provides a FEN, but edge cases may arise in unusual positions.
- Brilliant move criteria are an approximation of chess.com's proprietary algorithm.
- Material sacrifice detection uses a simplified static evaluation, not a full Static
  Exchange Evaluation (SEE).
- The `--assist` arrow overlay depends on the chess.com DOM structure, which may change
  with site updates.
- Analysis speed depends on Stockfish depth and your hardware -- bullet mode trades
  accuracy for speed.
- The tool must be started before or during a game; it does not retroactively analyze
  past moves.

## Project Structure

```
brillant/
├── core/
│   ├── main.py           # Entry point, monitoring loop, CLI
│   ├── config.py         # Configuration loading (JSON + defaults)
│   ├── engine.py         # Stockfish UCI wrapper (MultiPV, configurable depth/time)
│   ├── board_reader.py   # Chrome DevTools Protocol (arrows, heatmap, sequences)
│   ├── brilliant.py      # Brilliant move classification logic
│   ├── tactics.py        # Tactical pattern detection (fork, pin, discovery)
│   └── style.py          # Player style tracker (SQLite)
├── stockfish/            # Place stockfish.exe here (not tracked)
├── requirements.txt
├── .gitignore
└── README.md
```

## License

MIT License. See [LICENSE](LICENSE) for details.
