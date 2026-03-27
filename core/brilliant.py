import chess


PIECE_VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}


def is_sacrifice(board, move):
    """Determine whether a move is a material sacrifice.

    Returns (is_sac, net_material) where net_material is negative for
    sacrifices.  For captures the net is captured_value - moved_piece_value
    when the destination is attacked by the opponent; for non-captures the
    net is 0 - moved_piece_value.
    """
    moving_piece = board.piece_at(move.from_square)
    moved_value = PIECE_VALUES[moving_piece.symbol().upper()]

    destination_attacked = board.is_attacked_by(not board.turn, move.to_square)

    if board.is_capture(move):
        captured_piece = board.piece_at(move.to_square)

        # En passant: the captured pawn is not on the destination square
        if captured_piece is None and board.is_en_passant(move):
            captured_value = PIECE_VALUES['P']
        elif captured_piece is not None:
            captured_value = PIECE_VALUES[captured_piece.symbol().upper()]
        else:
            captured_value = 0

        if destination_attacked:
            net = captured_value - moved_value
            return (net < 0, net)
        else:
            # Capturing a piece on a safe square is never a sacrifice
            return (False, captured_value - moved_value)
    else:
        if destination_attacked:
            net = 0 - moved_value
            return (True, net)
        else:
            return (False, 0)


def is_non_obvious(board, move, last_move_square=None):
    """Return True if the move is non-obvious.

    A move is considered obvious (and thus returns False) when any of the
    following hold:
      a) It delivers checkmate in one.
      b) It is a recapture on the same square as the opponent's last move.
      c) It is the only legal move that gives check.
    """
    # (a) Mate in 1
    board.push(move)
    if board.is_checkmate():
        board.pop()
        return False
    gives_check = board.is_check()
    board.pop()

    # (b) Recapture
    if last_move_square is not None:
        target_square = chess.parse_square(last_move_square) if isinstance(
            last_move_square, str
        ) else last_move_square
        if move.to_square == target_square:
            return False

    # (c) Only checking move
    if gives_check:
        other_checks = 0
        for legal_move in board.legal_moves:
            if legal_move == move:
                continue
            board.push(legal_move)
            if board.is_check():
                other_checks += 1
            board.pop()
        if other_checks == 0:
            return False

    return True


def find_brilliant_move(fen, engine, last_move_square=None, top_moves=None):
    """Detect whether the best engine move in a position qualifies as
    brilliant.

    Returns a dict with move details when a brilliant move is found, or
    None otherwise.  If *top_moves* is provided it is used directly;
    otherwise the engine is queried.
    """
    if top_moves is None:
        top_moves = engine.analyze_top_moves(fen, 5)

    if len(top_moves) < 2:
        return None

    best_uci, best_san, eval_1 = top_moves[0][:3]
    eval_2 = top_moves[1][2]

    board = chess.Board(fen)
    move = chess.Move.from_uci(best_uci)

    # --- Criterion 1: material sacrifice ---
    is_sac, net_material = is_sacrifice(board, move)
    if not is_sac:
        return None

    # --- Criterion 2: uniquely good (eval gap > 80 cp) ---
    if abs(eval_1 - eval_2) <= 80:
        return None

    # --- Criterion 3: non-obvious ---
    if not is_non_obvious(board, move, last_move_square):
        return None

    # --- Criterion 4: positive outcome (>= -200 cp from side-to-move) ---
    # eval_1 is already from side-to-move perspective
    if eval_1 < -200:
        return None

    # All criteria passed — build the result
    moving_piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)

    # Handle en passant for the captured piece symbol
    if captured_piece is None and board.is_en_passant(move):
        captured_symbol = 'P'
    else:
        captured_symbol = captured_piece.symbol().upper() if captured_piece else None

    return {
        "move_san": best_san,
        "move_uci": best_uci,
        "eval": eval_1,
        "next_best_eval": eval_2,
        "sacrifice_net": net_material,
        "piece": moving_piece.symbol().upper(),
        "captured": captured_symbol,
    }
