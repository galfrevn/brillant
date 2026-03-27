"""Chess Brilliant Move Detector — entry point and monitoring loop."""

import argparse
import sys
import threading
import time
from datetime import datetime

import chess
from colorama import Fore, Style, init as colorama_init

from config import load_config
from engine import StockfishEngine
from board_reader import ChessBoardReader
from brilliant import find_brilliant_move
from tactics import classify_tactic, find_opponent_threats
from style import StyleTracker

PIECE_NAMES = {
    "P": "Pawn", "N": "Knight", "B": "Bishop",
    "R": "Rook", "Q": "Queen", "K": "King",
}


def ts():
    return datetime.now().strftime("%H:%M:%S")


def display_brilliant(info):
    piece = PIECE_NAMES.get(info["piece"], info["piece"])
    captured = PIECE_NAMES.get(info["captured"], "") if info["captured"] else ""
    eval_str = f"{info['eval'] / 100:+.1f}"
    next_str = f"{info['next_best_eval'] / 100:+.1f}"
    gap = abs(info["eval"] - info["next_best_eval"]) / 100
    capture_desc = f"{piece} for {captured}" if captured else f"{piece} to open square"

    print(f"\n{Fore.YELLOW}{Style.BRIGHT}")
    print("=" * 48)
    print(f"  {'!!'} BRILLIANT MOVE FOUND {'!!'}")
    print(f"  Play: {info['move_san']}")
    print(f"  Evaluation: {eval_str} (next best: {next_str})")
    print(f"  Sacrifice: {capture_desc} (net: {info['sacrifice_net']})")
    print(f"  Why: Only good move — alternatives lose > {gap:.1f} pawns")
    print("=" * 48)
    print(f"{Style.RESET_ALL}")


def _pos_key(fen):
    """Position key from FEN (board + turn + castling + en passant, ignoring move counters)."""
    return " ".join(fen.split()[:4])


def detect_played_move(prev_fen, current_fen):
    """Determine what move was played by comparing two FENs."""
    try:
        board = chess.Board(prev_fen)
        # Compare board position + active color (ignore castling/ep/counters)
        target_parts = current_fen.split()
        target_key = target_parts[0] + " " + target_parts[1]
        for move in board.legal_moves:
            board.push(move)
            parts = board.fen().split()
            key = parts[0] + " " + parts[1]
            if key == target_key:
                board.pop()
                return move
            board.pop()
    except Exception:
        pass
    return None


def show_review(game_moves, engine):
    """Display post-game review with accuracy and move classifications."""
    if not game_moves:
        print(f"\n{Fore.CYAN}No moves to review.{Style.RESET_ALL}")
        return

    categories = {"Perfect": 0, "Good": 0, "Inaccuracy": 0, "Mistake": 0, "Blunder": 0}
    worst_move = None
    worst_delta = 0
    best_move = None
    best_info = None
    total_delta = 0

    for i, m in enumerate(game_moves):
        delta = abs(m.get("delta_cp", 0))
        total_delta += delta

        if delta < 10:
            cat = "Perfect"
        elif delta < 50:
            cat = "Good"
        elif delta < 100:
            cat = "Inaccuracy"
        elif delta < 300:
            cat = "Mistake"
        else:
            cat = "Blunder"
        categories[cat] += 1

        if delta > worst_delta:
            worst_delta = delta
            worst_move = m

        if m.get("is_brilliant"):
            best_move = m

    total = len(game_moves)
    perfect_and_good = categories["Perfect"] + categories["Good"]
    accuracy = round(perfect_and_good / total * 100) if total > 0 else 0

    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 48}")
    print(f"  POST-GAME REVIEW")
    print(f"{'=' * 48}{Style.RESET_ALL}")
    print(f"  Moves: {total} | Accuracy: {Fore.GREEN}{accuracy}%{Style.RESET_ALL}")
    print(f"  Perfect: {categories['Perfect']} | Good: {categories['Good']} | "
          f"Inaccuracy: {categories['Inaccuracy']} | "
          f"Mistake: {Fore.YELLOW}{categories['Mistake']}{Style.RESET_ALL} | "
          f"Blunder: {Fore.RED}{categories['Blunder']}{Style.RESET_ALL}")

    if worst_move and worst_delta >= 50:
        print(f"\n  Worst: move {worst_move['move_num']} {worst_move['played_san']} "
              f"({Fore.RED}-{worst_delta / 100:.1f} pawns{Style.RESET_ALL})")
    if best_move:
        print(f"  Best:  move {best_move['move_num']} {best_move['played_san']} "
              f"({Fore.YELLOW}brilliant!{Style.RESET_ALL})")
    print()


def get_forced_mate_fens(fen, pv_uci):
    """If opponent has exactly one legal move at each of their steps in the PV,
    return the set of position keys for every position in the sequence.
    Returns None if not fully forced."""
    board = chess.Board(fen)
    keys = {_pos_key(fen)}
    for i, uci in enumerate(pv_uci):
        move = chess.Move.from_uci(uci)
        if i % 2 == 1:  # opponent's turn
            if len(list(board.legal_moves)) != 1:
                return None
        board.push(move)
        keys.add(_pos_key(board.fen()))
    return keys



def get_elo_premove_settings(opponent_elo):
    """Return (candidates, depth, time_limit) based on opponent's ELO."""
    if opponent_elo is None or opponent_elo > 1800:
        return 3, 14, 1.0
    elif opponent_elo > 1200:
        return 2, 12, 0.8
    else:
        return 1, 10, 0.5


def get_elo_analysis_settings(opponent_elo, config):
    """Return (depth, time_limit) for main analysis adjusted by opponent ELO."""
    if opponent_elo is None or opponent_elo > 1800:
        return config["depth"], config["engine_time"]
    elif opponent_elo > 1200:
        return min(config["depth"], 16), min(config["engine_time"], 1.5)
    else:
        return min(config["depth"], 14), min(config["engine_time"], 1.0)


def get_clock_overrides(our_time, elo_depth, elo_time, config):
    """Return (depth, time_limit, poll_interval) adjusted for time pressure.
    Takes ELO-adjusted depth/time as baseline instead of config defaults."""
    if our_time is None or our_time > 60:
        return elo_depth, elo_time, config["poll_interval"]
    elif our_time > 30:
        return min(elo_depth, 16), min(elo_time, 1.5), 0.3
    elif our_time > 10:
        return min(elo_depth, 12), min(elo_time, 0.8), 0.2
    else:
        return 8, 0.3, 0.15


def analyze_premoves(fen, engine, reader, reader_lock, args, config,
                     candidates=3, pm_depth=14, pm_time=1.0):
    """Analyze opponent's likely moves and suggest premove responses.

    Runs in a background thread with its own Stockfish engine.
    Uses reader_lock to safely access the shared ChessBoardReader.
    """
    board = chess.Board(fen)

    # Get opponent's top moves (quick analysis, depth/candidates adjusted by ELO)
    opp_moves = engine.analyze_top_moves(fen, candidates, depth=pm_depth, time_limit=pm_time)
    if not opp_moves:
        return

    if args.assist:
        with reader_lock:
            reader.clear_arrows()

    print(f"[{ts()}] {Fore.BLUE}Premove suggestions:{Style.RESET_ALL}")

    # Visual weight per likelihood rank
    arrow_styles = [
        {"width": 10},  # most likely
        {"width": 7},   # possible
        {"width": 5},   # unlikely
    ]

    for i, (opp_uci, opp_san, opp_eval, opp_mate, _, _) in enumerate(opp_moves[:candidates]):
        try:
            opp_move = chess.Move.from_uci(opp_uci)
            board.push(opp_move)
            response_fen = board.fen()

            # Analyze our best response (fast)
            responses = engine.analyze_top_moves(response_fen, 1, depth=pm_depth, time_limit=pm_time)
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
                with reader_lock:
                    reader.draw_arrow(
                        resp_uci[:2], resp_uci[2:4],
                        color="#3399ff", width=style["width"])

        except Exception:
            continue


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chess Brilliant Move Detector — reads chess.com via Chrome."
    )
    parser.add_argument("--port", type=int, default=9222,
                        help="Chrome remote debugging port (default: 9222)")
    parser.add_argument("--depth", type=int, default=None,
                        help="Stockfish analysis depth")
    parser.add_argument("--debug", action="store_true",
                        help="Show FEN for each position")
    parser.add_argument("--assist", action="store_true",
                        help="Draw arrows on the board for best moves and mates")
    parser.add_argument("--bullet", action="store_true",
                        help="Bullet mode: fast analysis (depth 8, instant response)")
    parser.add_argument("--stats", action="store_true",
                        help="Show your playing style stats and exit")
    parser.add_argument("--heatmap", action="store_true",
                        help="Highlight squares where your pieces are under attack")
    parser.add_argument("--review", action="store_true",
                        help="Show post-game review with accuracy and move classification")
    parser.add_argument("--tactics-only", action="store_true",
                        help="Only show tactical patterns — no best moves, no premoves")
    return parser.parse_args()


def show_stats():
    """Display player style statistics."""
    tracker = StyleTracker()
    stats = tracker.get_stats()
    openings = tracker.get_opening_stats()
    tracker.close()

    if stats["total_moves"] == 0:
        print(f"  Games played: {stats['total_games']}, but no moves analyzed yet.")
        print("  Play some games with the tool running first!")
        return

    print(f"\n{Fore.CYAN}{Style.BRIGHT}=== YOUR PLAYING STYLE ==={Style.RESET_ALL}\n")
    print(f"  Games played:    {stats['total_games']}")
    print(f"  Moves analyzed:  {stats['total_moves']}")
    print(f"  Brilliants:      {Fore.YELLOW}{stats['brilliants']}{Style.RESET_ALL}")
    print(f"  Sacrifices:      {stats['sacrifices']} ({stats['sacrifice_rate']}% of moves)")
    print(f"  Engine accuracy: {stats['accuracy']}%")
    print(f"  Avg evaluation:  {stats['avg_eval_cp'] / 100:+.1f}")

    if stats.get("favorite_pieces"):
        pieces = ", ".join(f"{PIECE_NAMES.get(p, p)}({c})" for p, c in stats["favorite_pieces"])
        print(f"  Favorite pieces: {pieces}")

    if openings:
        opn = ", ".join(f"{m}({c})" for m, c in openings)
        print(f"  Favorite opens:  {opn}")

    print(f"\n  {Fore.GREEN}{Style.BRIGHT}Style: {stats['style']}{Style.RESET_ALL}\n")


def main():
    colorama_init()
    args = parse_args()

    if args.stats:
        show_stats()
        return

    config = load_config()

    if args.bullet:
        config["depth"] = 8
        config["multipv"] = 3
        config["poll_interval"] = 0.2
    if args.depth is not None:
        config["depth"] = args.depth

    # --- Connect to Chrome ---
    print(f"[{ts()}] Connecting to Chrome on port {args.port}...")
    try:
        reader = ChessBoardReader(port=args.port)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    print(f"{Fore.GREEN}Connected to Chrome.{Style.RESET_ALL}")

    # --- Start Stockfish ---
    print(f"[{ts()}] Loading Stockfish...")
    engine = StockfishEngine(
        path=config["stockfish_path"],
        depth=config["depth"],
        threads=config["threads"],
        hash_size=config["hash_size"],
        engine_time=config["engine_time"],
    )
    # Second engine for premoves (runs in background thread)
    premove_engine = StockfishEngine(
        path=config["stockfish_path"],
        depth=14,
        threads=1,
        hash_size=64,
        engine_time=1,
    )

    reader_lock = threading.Lock()
    premove_thread = None
    forced_mate_fens = None  # set of position keys when forced mate sequence is active

    poll = config["poll_interval"]
    base_poll = poll  # remember original for clock reset
    prev_fen = None
    last_analyzed_fen = None
    player_color = None
    in_game = False
    opponent_elo = None
    pm_candidates, pm_depth, pm_time = 3, 14, 1.0  # premove settings (adjusted by ELO)
    elo_depth, elo_time = config["depth"], config["engine_time"]  # main analysis (adjusted by ELO)
    game_moves = []  # for post-game review: list of move dicts
    last_engine_best = None  # {san, eval, fen} — saved when we analyze on our turn
    last_our_fen = None  # FEN from our last analyzed turn
    tracker = StyleTracker()
    style_profile = tracker.get_style_profile()
    if style_profile:
        print(f"  Style loaded: sacrifice_rate={style_profile['sacrifice_rate']}%, "
              f"accuracy={style_profile['accuracy']}%")
    game_id = None
    move_number = 0

    print(f"\n{Fore.GREEN}{Style.BRIGHT}Monitoring started.{Style.RESET_ALL}")
    print(f"  Depth: {config['depth']} | Poll: {poll}s")
    print(f"  Waiting for a game...\n")

    try:
        while True:
            time.sleep(poll)

            # 1. Read game state from chess.com
            try:
                with reader_lock:
                    state = reader.get_state()
            except Exception as e:
                if args.debug:
                    print(f"  [DEBUG] read error: {e}")
                try:
                    reader.close()
                    reader = ChessBoardReader(port=args.port)
                except Exception:
                    pass
                continue

            if not state or not state.get("fen"):
                if in_game:
                    print(f"[{ts()}] No board found — waiting...")
                    in_game = False
                continue

            fen = state["fen"]
            playing_as = state.get("playing_as")
            game_over = state.get("is_game_over", False)

            # 2. Game over — only skip if we already reported it
            if game_over:
                if in_game:
                    result = state.get("result") or ""
                    print(f"[{ts()}] {Fore.RED}Game over.{Style.RESET_ALL} {result}")
                    if game_id:
                        tracker.end_game(game_id, result or "unknown")
                    if args.review and game_moves:
                        show_review(game_moves, engine)
                    in_game = False
                    prev_fen = None
                    last_analyzed_fen = None
                    forced_mate_fens = None
                    game_id = None
                    move_number = 0
                    game_moves = []
                    last_engine_best = None
                    last_our_fen = None
                continue

            # 3. Detect new game — also catch rematches by FEN move counter reset
            fen_parts = fen.split()
            fullmove = int(fen_parts[5]) if len(fen_parts) > 5 else 1
            if in_game and fullmove == 1 and move_number > 2:
                # FEN reset to move 1 mid-session = new game started
                in_game = False

            # 3b. Detect color — playing_as can be 1, 2, or None
            if playing_as is None:
                playing_as = 1

            if playing_as != player_color or not in_game:
                player_color = playing_as
                in_game = True
                prev_fen = None
                last_analyzed_fen = None
                forced_mate_fens = None
                move_number = 0
                color_display = "white" if player_color == 1 else "black"
                game_id = tracker.start_game(color_display)
                game_moves = []
                last_engine_best = None
                last_our_fen = None

                # Read opponent ELO and adapt strategy
                opponent_elo = state.get("opponent_elo")
                pm_candidates, pm_depth, pm_time = get_elo_premove_settings(opponent_elo)
                elo_depth, elo_time = get_elo_analysis_settings(opponent_elo, config)
                elo_str = str(opponent_elo) if opponent_elo else "?"
                print(f"[{ts()}] {Fore.GREEN}Game active!{Style.RESET_ALL} "
                      f"Playing as {Fore.CYAN}{color_display}{Style.RESET_ALL} "
                      f"vs {Fore.YELLOW}{elo_str} ELO{Style.RESET_ALL}")

            # 4. FEN unchanged — skip
            if fen == prev_fen:
                continue
            prev_fen = fen

            # 4.5. Forced mate in progress — keep arrows, skip analysis
            if forced_mate_fens is not None:
                if _pos_key(fen) in forced_mate_fens:
                    continue
                else:
                    # Position deviated from forced line
                    forced_mate_fens = None

            # 5. Adapt to clock pressure (ELO-adjusted baseline)
            our_time = state.get("our_time")
            clock_depth, clock_time, clock_poll = get_clock_overrides(our_time, elo_depth, elo_time, config)
            poll = clock_poll

            # 6. Determine whose turn it is from FEN
            parts = fen.split()
            active_color = parts[1] if len(parts) > 1 else "w"

            # Is it the player's turn?
            player_turn = "w" if player_color == 1 else "b"
            if active_color != player_turn:
                # Track actual move played (for post-game review)
                if args.review and last_our_fen and last_engine_best:
                    played = detect_played_move(last_our_fen, fen)
                    if played:
                        try:
                            pb = chess.Board(last_our_fen)
                            played_san = pb.san(played)
                        except Exception:
                            played_san = played.uci()
                        game_moves.append({
                            "move_num": len(game_moves) + 1,
                            "fen": last_our_fen,
                            "played_san": played_san,
                            "played_uci": played.uci(),
                            "engine_best_san": last_engine_best["san"],
                            "engine_best_eval": last_engine_best["eval"],
                            "delta_cp": last_engine_best.get("delta", 0),
                            "is_brilliant": last_engine_best.get("is_brilliant", False),
                        })
                    last_engine_best = None

                # Opponent's turn — launch premoves in background thread
                if not args.tactics_only and fen != last_analyzed_fen and "K" in fen and "k" in fen:
                    last_analyzed_fen = fen
                    if premove_thread is None or not premove_thread.is_alive():
                        premove_thread = threading.Thread(
                            target=analyze_premoves,
                            args=(fen, premove_engine, reader, reader_lock, args, config,
                                  pm_candidates, pm_depth, pm_time),
                            daemon=True)
                        premove_thread.start()
                continue

            # Skip if already analyzed this exact position
            if fen == last_analyzed_fen:
                continue

            if args.debug:
                print(f"  [DEBUG] Our turn. FEN: {fen}")

            # Validate: both kings present
            if "K" not in fen or "k" not in fen:
                continue

            # 6. Detect last move destination (for recapture filtering)
            last_move_sq = None
            if prev_fen:
                try:
                    # Compare boards to find where opponent moved
                    prev_board = chess.Board(last_analyzed_fen) if last_analyzed_fen else None
                except Exception:
                    prev_board = None

            last_analyzed_fen = fen

            # Tactics-only mode: detect patterns without engine analysis
            if args.tactics_only:
                try:
                    tac_board = chess.Board(fen)
                    # Offensive: check each legal move for tactics
                    found_any = False
                    for move in tac_board.legal_moves:
                        tactic = classify_tactic(tac_board, move)
                        if tactic:
                            san = tac_board.san(move)
                            print(f"[{ts()}] {Fore.YELLOW}{tactic}: {san}{Style.RESET_ALL}")
                            if args.assist:
                                uci = move.uci()
                                with reader_lock:
                                    if not found_any:
                                        reader.clear_arrows()
                                    reader.draw_arrow(uci[:2], uci[2:4], color="#ffcc00",
                                                      width=10, label=tactic)
                            found_any = True

                    # Defensive: opponent threats
                    threats = find_opponent_threats(tac_board)
                    for t in threats:
                        print(f"[{ts()}] {Fore.RED}  Threat: {t['move_san']} ({t['tactic']}){Style.RESET_ALL}")

                    # Heatmap
                    if args.heatmap and args.assist:
                        threatened = []
                        for sq in chess.SQUARES:
                            p = tac_board.piece_at(sq)
                            if p and p.color == tac_board.turn:
                                if tac_board.is_attacked_by(not tac_board.turn, sq):
                                    threatened.append(chess.square_name(sq))
                        if threatened:
                            with reader_lock:
                                reader.draw_heatmap(threatened)
                except Exception:
                    pass
                continue

            # 8. Analyze! (depth/time adapted to clock)
            print(f"[{ts()}] Analyzing...", end=" ", flush=True)
            top_moves = engine.analyze_top_moves(fen, config["multipv"],
                                                  depth=clock_depth, time_limit=clock_time)
            if not top_moves:
                print("skip.")
                continue

            result = find_brilliant_move(fen, engine, last_move_sq, top_moves)

            # Always clear previous arrows first
            if args.assist:
                with reader_lock:
                    reader.clear_arrows()

            best_uci, best_san, best_eval, best_mate, best_pv, best_pv_uci = top_moves[0]

            # Save for post-game review: engine's best + eval delta
            last_our_fen = fen
            second_eval = top_moves[1][2] if len(top_moves) > 1 else best_eval
            last_engine_best = {
                "san": best_san,
                "eval": best_eval,
                "delta": abs(best_eval - second_eval),
                "is_brilliant": False,
            }

            # Detect tactics on best move
            try:
                tactic_board = chess.Board(fen)
                best_move_obj = chess.Move.from_uci(best_uci)
                tactic_label = classify_tactic(tactic_board, best_move_obj)
                if tactic_label:
                    print(f"{Fore.YELLOW}{tactic_label}!{Style.RESET_ALL} ", end="")
            except Exception:
                tactic_label = None

            # Detect opponent threats
            try:
                tactic_board = chess.Board(fen)
                threats = find_opponent_threats(tactic_board)
                for t in threats:
                    print(f"{Fore.RED}  ⚠ Opponent threat: {t['move_san']} ({t['tactic']}){Style.RESET_ALL}")
            except Exception:
                threats = []

            # Heatmap: highlight our pieces under attack
            if args.heatmap and args.assist:
                try:
                    hm_board = chess.Board(fen)
                    threatened = []
                    for sq in chess.SQUARES:
                        p = hm_board.piece_at(sq)
                        if p and p.color == hm_board.turn:
                            if hm_board.is_attacked_by(not hm_board.turn, sq):
                                threatened.append(chess.square_name(sq))
                    if threatened:
                        with reader_lock:
                            reader.draw_heatmap(threatened)
                except Exception:
                    pass

            # Track move in style DB
            move_number += 1
            piece_moved = None
            captured = None
            try:
                board = chess.Board(fen)
                move_obj = chess.Move.from_uci(best_uci)
                p = board.piece_at(move_obj.from_square)
                if p:
                    piece_moved = p.symbol().upper()
                if board.is_capture(move_obj):
                    cap = board.piece_at(move_obj.to_square)
                    if cap:
                        captured = cap.symbol().upper()
            except Exception:
                pass

            if game_id:
                tracker.record_move(
                    game_id=game_id,
                    move_number=move_number,
                    fen=fen,
                    move_played=best_san,  # We record engine's best as "played" for now
                    engine_best=best_san,
                    eval_cp=best_eval,
                    is_brilliant=bool(result),
                    is_sacrifice=result is not None and result.get("sacrifice_net", 0) < 0,
                    is_mate_move=best_mate is not None,
                    piece_moved=piece_moved,
                    captured_piece=captured,
                )

            if result:
                print()
                display_brilliant(result)
                if last_engine_best:
                    last_engine_best["is_brilliant"] = True

                if args.assist:
                    uci = result["move_uci"]
                    with reader_lock:
                        reader.draw_arrow(uci[:2], uci[2:4], color="#ffcc00", width=12, label="!!")
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

                    # Check if mate is forced (opponent has only one legal move at each step)
                    fm_fens = get_forced_mate_fens(fen, best_pv_uci)
                    if fm_fens is not None:
                        forced_mate_fens = fm_fens

                        print(f"  {Fore.GREEN}Forced mate — arrows locked, premove the whole line!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Opponent has mate in {mate_moves}. "
                          f"Best: {best_san}{Style.RESET_ALL}")

                # Draw full mate sequence as numbered arrows
                if args.assist:
                    with reader_lock:
                        if our_mate:
                            reader.draw_move_sequence(
                                best_pv_uci, player_turn,
                                our_color="#ff3333", opp_color="#888888")
                        else:
                            reader.draw_move_sequence(
                                best_pv_uci, player_turn,
                                our_color="#cc0000", opp_color="#888888")
            else:
                # Re-rank by style if we have a profile
                style_pick = None
                if style_profile and len(top_moves) > 1:
                    board_for_style = chess.Board(fen)
                    scored = []
                    for m_uci, m_san, m_eval, m_mate, m_pv, _ in top_moves:
                        if m_mate is not None:
                            continue
                        try:
                            mv = chess.Move.from_uci(m_uci)
                            p = board_for_style.piece_at(mv.from_square)
                            pm = p.symbol().upper() if p else None
                            is_sac = board_for_style.is_attacked_by(
                                not board_for_style.turn, mv.to_square)
                        except Exception:
                            pm, is_sac = None, False
                        bonus = tracker.score_move_for_style(
                            style_profile, m_uci, m_eval, best_eval, is_sac, pm)
                        scored.append((m_uci, m_san, m_eval, bonus))

                    if scored:
                        scored.sort(key=lambda x: -(x[2] + x[3]))
                        pick = scored[0]
                        if pick[1] != best_san and pick[3] > 0:
                            style_pick = pick

                if style_pick:
                    s_uci, s_san, s_eval, s_bonus = style_pick
                    print(f"Best: {best_san} ({best_eval / 100:+.1f}) | "
                          f"{Fore.CYAN}Your style: {s_san} ({s_eval / 100:+.1f}){Style.RESET_ALL}")
                    if args.assist:
                        with reader_lock:
                            reader.draw_arrow(s_uci[:2], s_uci[2:4], color="#33cccc", width=10)
                else:
                    print(f"Best: {best_san} ({best_eval / 100:+.1f})")
                    if args.assist:
                        with reader_lock:
                            reader.draw_arrow(best_uci[:2], best_uci[2:4], color="#33cc33",
                                              width=10, label=tactic_label)

    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Shutting down...{Style.RESET_ALL}")
    finally:
        engine.close()
        premove_engine.close()
        reader.close()
        tracker.close()
        print("Goodbye!")


if __name__ == "__main__":
    main()
