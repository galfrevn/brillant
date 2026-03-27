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


def analyze_premoves(fen, engine, reader, reader_lock, args, config):
    """Analyze opponent's likely moves and suggest premove responses.

    Runs in a background thread with its own Stockfish engine.
    Uses reader_lock to safely access the shared ChessBoardReader.
    """
    board = chess.Board(fen)

    # Get opponent's top moves (quick analysis)
    opp_moves = engine.analyze_top_moves(fen, 3, depth=14, time_limit=1)
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

    for i, (opp_uci, opp_san, opp_eval, opp_mate, _, _) in enumerate(opp_moves[:3]):
        try:
            opp_move = chess.Move.from_uci(opp_uci)
            board.push(opp_move)
            response_fen = board.fen()

            # Analyze our best response (fast)
            responses = engine.analyze_top_moves(response_fen, 1, depth=14, time_limit=1)
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
    prev_fen = None
    last_analyzed_fen = None
    player_color = None
    in_game = False
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
                    in_game = False
                    prev_fen = None
                    last_analyzed_fen = None
                    forced_mate_fens = None
                    game_id = None
                    move_number = 0
                continue

            # 3. Detect color — playing_as can be 1, 2, or None
            # If None (live game), fall back to FEN-based detection
            if playing_as is None:
                # Assume white=1 if not flipped, board_reader handles this
                playing_as = 1  # default, board_reader detects flip

            if playing_as != player_color or not in_game:
                player_color = playing_as
                in_game = True
                prev_fen = None
                last_analyzed_fen = None
                forced_mate_fens = None
                move_number = 0
                color_display = "white" if player_color == 1 else "black"
                game_id = tracker.start_game(color_display)
                print(f"[{ts()}] {Fore.GREEN}Game active!{Style.RESET_ALL} "
                      f"Playing as {Fore.CYAN}{color_display}{Style.RESET_ALL}")

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

            # 5. Determine whose turn it is from FEN
            parts = fen.split()
            active_color = parts[1] if len(parts) > 1 else "w"

            # Is it the player's turn?
            player_turn = "w" if player_color == 1 else "b"
            if active_color != player_turn:
                # Opponent's turn — launch premoves in background thread
                if fen != last_analyzed_fen and "K" in fen and "k" in fen:
                    last_analyzed_fen = fen
                    if premove_thread is None or not premove_thread.is_alive():
                        premove_thread = threading.Thread(
                            target=analyze_premoves,
                            args=(fen, premove_engine, reader, reader_lock, args, config),
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

            # 7. Analyze!
            print(f"[{ts()}] Analyzing...", end=" ", flush=True)
            top_moves = engine.analyze_top_moves(fen, config["multipv"])
            if not top_moves:
                print("skip.")
                continue

            result = find_brilliant_move(fen, engine, last_move_sq, top_moves)

            # Always clear previous arrows first
            if args.assist:
                with reader_lock:
                    reader.clear_arrows()

            best_uci, best_san, best_eval, best_mate, best_pv, best_pv_uci = top_moves[0]

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
                            reader.draw_arrow(best_uci[:2], best_uci[2:4], color="#33cc33", width=10)

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
