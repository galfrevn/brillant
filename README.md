# Brillant -- Chess Brilliant Move Detector

> **Disclaimer:** This project was built for educational and hackathon purposes only.
> It is **not** intended for use in competitive or rated games. Using external assistance
> during online rated play violates the terms of service of chess platforms and constitutes
> cheating. Use this tool only for learning, analysis of your own past games, or
> unrated/friendly matches where all participants consent.

## What It Does

Brillant monitors your chess.com games in real time through the Chrome DevTools Protocol.
It reads the board state directly from the page, sends positions to a local Stockfish
engine, and tells you when a **brilliant move** (`!!`) is available. It also finds forced
mate sequences with premove suggestions and can draw move arrows directly on the board.

## Features

- **Brilliant move detection** -- identifies sacrificial moves that are uniquely strong,
  non-obvious, and lead to a winning position.
- **Mate finder with premove sequences** -- when a forced checkmate exists, displays the
  full sequence of moves you need to premove.
- **Premove suggestions** -- on the opponent's turn, predicts their most likely replies
  and suggests your best premove response to each.
- **Arrow overlay on board** (`--assist`) -- draws colored arrows directly on the
  chess.com board via SVG injection (green for best move, yellow for brilliant, red for
  mate).
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
cd chess
py main.py
```

### Common invocations

| Command                         | Description                                  |
|---------------------------------|----------------------------------------------|
| `py main.py`                    | Standard monitoring (depth 16, no arrows)    |
| `py main.py --assist`           | Draw best-move arrows on the board           |
| `py main.py --bullet`           | Bullet mode (depth 8, fast poll)             |
| `py main.py --assist --bullet`  | Arrows + bullet mode                         |
| `py main.py --depth 22`         | Override analysis depth                      |
| `py main.py --debug`            | Show FEN and extra diagnostic output         |

### CLI Flags

| Flag           | Type  | Default | Description                                      |
|----------------|-------|---------|--------------------------------------------------|
| `--port`       | int   | 9222    | Chrome remote debugging port                     |
| `--depth`      | int   | 16      | Stockfish analysis depth (overrides config)       |
| `--debug`      | flag  | off     | Print FEN and diagnostic info for each position  |
| `--assist`     | flag  | off     | Draw move arrows on the chess.com board          |
| `--bullet`     | flag  | off     | Bullet mode: depth 8, 0.2s poll interval         |
| `--stats`      | flag  | off     | Show your playing style statistics and exit       |

## How It Works

1. **Connects to Chrome** via the DevTools Protocol on `localhost:9222`.
2. **Reads the board state** by evaluating JavaScript inside the chess.com tab -- it
   calls the site's own `wc-chess-board` element API to retrieve the FEN, detects the
   board orientation, and checks for game-over modals.
3. **Analyzes with Stockfish** using MultiPV (multiple principal variations) to get the
   top candidate moves and their evaluations.
4. **Detects brilliant moves** by checking four criteria:
   - The move is a material sacrifice (the moved piece is worth more than what it
     captures, and the destination is attacked).
   - The move is uniquely good (evaluation gap > 0.8 pawns vs. the second-best move).
   - The move is non-obvious (not a simple checkmate-in-one, recapture, or the only
     checking move).
   - The resulting position is still good for the player (eval >= -2.0).
5. **Suggests premoves** on the opponent's turn by predicting their likely replies and
   computing your best response to each.
6. **Draws arrows** (when `--assist` is active) by injecting an SVG overlay into the
   page via `Runtime.evaluate`.

## Configuration

On first run, if no `config.json` exists the tool uses sensible defaults. You can create
a `config.json` in the `core/` directory to override settings:

```json
{
  "stockfish_path": "../stockfish/stockfish.exe",
  "depth": 16,
  "threads": 2,
  "hash_size": 128,
  "multipv": 5,
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
│   ├── engine.py         # Stockfish UCI wrapper (MultiPV analysis)
│   ├── board_reader.py   # Chrome DevTools Protocol interface
│   ├── brilliant.py      # Brilliant move classification logic
│   └── style.py          # Player style tracker (SQLite)
├── stockfish/            # Place stockfish.exe here (not tracked)
├── requirements.txt
├── .gitignore
└── README.md
```

## License

MIT License. See [LICENSE](LICENSE) for details.
