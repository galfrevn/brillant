"""Tactical pattern detection using python-chess."""

import chess

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100,
}


def _piece_value(piece):
    return PIECE_VALUES.get(piece.piece_type, 0)


def _is_fork(board, move):
    """Does the move create a fork — the moved piece attacks 2+ valuable enemy pieces
    that it wasn't attacking before?"""
    from_sq = move.from_square

    # Count valuable targets attacked from the origin square
    attacked_before = set()
    for sq in board.attacks(from_sq):
        target = board.piece_at(sq)
        if target and target.color != board.turn:
            if target.piece_type == chess.KING or _piece_value(target) > 1:
                attacked_before.add(sq)

    board.push(move)
    attacker_sq = move.to_square
    attacker = board.piece_at(attacker_sq)
    if not attacker:
        board.pop()
        return False

    attacked_after = set()
    for sq in board.attacks(attacker_sq):
        target = board.piece_at(sq)
        if target and target.color != attacker.color:
            if target.piece_type == chess.KING or _piece_value(target) > 1:
                attacked_after.add(sq)

    board.pop()
    # Must attack 2+ valuable pieces, and at least one must be new
    new_attacks = attacked_after - attacked_before
    return len(attacked_after) >= 2 and len(new_attacks) >= 1


def _is_discovered_attack(board, move):
    """Does moving the piece uncover an attack from another allied piece?"""
    color = board.turn
    from_sq = move.from_square

    # Find pieces that were blocked by the moving piece
    for direction in [
        chess.BB_FILE_ATTACKS, chess.BB_RANK_ATTACKS,
        chess.BB_DIAG_ATTACKS,
    ]:
        pass  # Complex ray-casting, use a simpler approach

    # Simpler: compare attacks before and after
    enemy_king_sq = board.king(not color)
    enemy_pieces_attacked_before = set()
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.color == color and sq != from_sq:
            for atk_sq in board.attacks(sq):
                target = board.piece_at(atk_sq)
                if target and target.color != color and _piece_value(target) > 1:
                    enemy_pieces_attacked_before.add(atk_sq)

    board.push(move)
    enemy_pieces_attacked_after = set()
    to_sq = move.to_square
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.color == color and sq != to_sq:
            for atk_sq in board.attacks(sq):
                target = board.piece_at(atk_sq)
                if target and target.color != color and _piece_value(target) > 1:
                    enemy_pieces_attacked_after.add(atk_sq)
    board.pop()

    new_attacks = enemy_pieces_attacked_after - enemy_pieces_attacked_before
    return len(new_attacks) > 0


def _find_pins(board, color):
    """Find all pinned enemy pieces for the given color's sliding pieces."""
    enemy = not color
    enemy_king_sq = board.king(enemy)
    if enemy_king_sq is None:
        return set()
    pinned = set()
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p or p.color != color:
            continue
        if p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        ray = chess.ray(sq, enemy_king_sq)
        if not ray:
            continue
        between = chess.between(sq, enemy_king_sq)
        pieces_between = []
        for bsq in chess.scan_forward(between):
            bp = board.piece_at(bsq)
            if bp:
                pieces_between.append((bsq, bp))
        if len(pieces_between) == 1:
            pinned_sq, pinned_piece = pieces_between[0]
            if pinned_piece.color == enemy and pinned_piece.piece_type != chess.KING:
                pinned.add(pinned_sq)
    return pinned


def _is_pin(board, move):
    """Does the move CREATE a new pin that didn't exist before?"""
    our_color = board.turn
    pins_before = _find_pins(board, our_color)
    board.push(move)
    pins_after = _find_pins(board, our_color)
    board.pop()
    return len(pins_after - pins_before) > 0


def _is_skewer(board, move):
    """After the move, does a sliding piece attack a valuable piece that,
    if moved, exposes a less valuable piece behind it on the same ray?"""
    board.push(move)
    to_sq = move.to_square
    attacker = board.piece_at(to_sq)
    if not attacker or attacker.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        board.pop()
        return False

    our_color = attacker.color
    for target_sq in board.attacks(to_sq):
        target = board.piece_at(target_sq)
        if not target or target.color == our_color:
            continue
        if _piece_value(target) < 3:
            continue

        # Check ray from attacker through target for a piece behind
        between_after = chess.between(to_sq, target_sq)
        # Make sure nothing is between attacker and target (clean line)
        blocked = False
        for bsq in chess.scan_forward(between_after):
            if board.piece_at(bsq):
                blocked = True
                break
        if blocked:
            continue

        # Extend ray beyond target: scan squares on the same ray past the target
        # Direction: from attacker (to_sq) through target (target_sq) and beyond
        file_diff = chess.square_file(target_sq) - chess.square_file(to_sq)
        rank_diff = chess.square_rank(target_sq) - chess.square_rank(to_sq)
        # Normalize to -1, 0, 1
        df = (1 if file_diff > 0 else -1) if file_diff != 0 else 0
        dr = (1 if rank_diff > 0 else -1) if rank_diff != 0 else 0

        # Walk beyond target
        sq = target_sq
        while True:
            f = chess.square_file(sq) + df
            r = chess.square_rank(sq) + dr
            if not (0 <= f <= 7 and 0 <= r <= 7):
                break
            sq = chess.square(f, r)
            behind_piece = board.piece_at(sq)
            if behind_piece:
                if behind_piece.color != our_color and _piece_value(behind_piece) < _piece_value(target):
                    board.pop()
                    return True
                break  # blocked by any piece

    board.pop()
    return False


def classify_tactic(board, move):
    """Classify a move's tactic. Returns 'Fork', 'Pin', 'Skewer', 'Disc+', or None."""
    if isinstance(move, str):
        move = chess.Move.from_uci(move)

    if _is_fork(board, move):
        return "Fork"
    if _is_pin(board, move):
        return "Pin"
    if _is_skewer(board, move):
        return "Skewer"
    if _is_discovered_attack(board, move):
        return "Disc+"
    return None


def find_opponent_threats(board):
    """Find tactical threats the opponent has in the current position.
    Returns list of {move_san, move_uci, tactic} dicts, max 3."""
    threats = []
    # Flip turn using chess.Board.turn property (preserves full board state)
    opp_board = board.copy()
    opp_board.turn = not opp_board.turn
    # Clear castling rights to avoid pseudo-legal issues with flipped turn
    opp_board.castling_rights = chess.BB_EMPTY

    for move in opp_board.legal_moves:
        tactic = classify_tactic(opp_board, move)
        if tactic:
            try:
                san = opp_board.san(move)
            except Exception:
                san = move.uci()
            threats.append({
                "move_san": san,
                "move_uci": move.uci(),
                "tactic": tactic,
            })
            if len(threats) >= 3:
                break

    return threats
