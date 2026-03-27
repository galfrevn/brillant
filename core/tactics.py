"""Tactical pattern detection using python-chess."""

import chess

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100,
}


def _piece_value(piece):
    return PIECE_VALUES.get(piece.piece_type, 0)


def _is_fork(board, move):
    """After the move, does the moved piece attack 2+ enemy pieces of value?"""
    board.push(move)
    attacker_sq = move.to_square
    attacker = board.piece_at(attacker_sq)
    if not attacker:
        board.pop()
        return False

    attacked_valuable = []
    for sq in board.attacks(attacker_sq):
        target = board.piece_at(sq)
        if target and target.color != attacker.color:
            if target.piece_type == chess.KING or _piece_value(target) > 1:
                attacked_valuable.append(target)

    board.pop()
    return len(attacked_valuable) >= 2


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


def _is_pin(board, move):
    """After the move, is an enemy piece pinned against the enemy king?"""
    board.push(move)
    enemy = not board.turn  # opponent of the side that just moved
    enemy_king_sq = board.king(enemy)
    if enemy_king_sq is None:
        board.pop()
        return False

    # Check all our sliding pieces for pins
    our_color = not enemy
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p or p.color != our_color:
            continue
        if p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue

        # Check ray from our piece toward enemy king
        ray = chess.ray(sq, enemy_king_sq)
        if not ray:
            continue

        # Walk from our piece to king, count enemy pieces in between
        between = chess.between(sq, enemy_king_sq)
        pieces_between = []
        for bsq in chess.scan_forward(between):
            bp = board.piece_at(bsq)
            if bp:
                pieces_between.append((bsq, bp))

        # Exactly one enemy piece between = pin
        if len(pieces_between) == 1:
            pinned_sq, pinned_piece = pieces_between[0]
            if pinned_piece.color == enemy and pinned_piece.piece_type != chess.KING:
                board.pop()
                return True

    board.pop()
    return False


def _is_skewer(board, move):
    """After the move, does a sliding piece attack a valuable piece that has
    a less valuable piece behind it on the same line?"""
    board.push(move)
    to_sq = move.to_square
    attacker = board.piece_at(to_sq)
    if not attacker or attacker.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        board.pop()
        return False

    our_color = attacker.color
    # Check each enemy piece attacked by us
    for target_sq in board.attacks(to_sq):
        target = board.piece_at(target_sq)
        if not target or target.color == our_color:
            continue
        if _piece_value(target) < 3:
            continue

        # Is there a less valuable piece behind the target on the same ray?
        ray = chess.ray(to_sq, target_sq)
        if not ray:
            continue
        # Extend beyond target
        behind = chess.between(target_sq, chess.msb(ray) if target_sq < chess.msb(ray) else chess.lsb(ray))
        for bsq in chess.scan_forward(chess.BB_SQUARES[target_sq + 1:] if False else 0):
            pass  # Ray extension is complex

    board.pop()
    return False  # Skewer detection is complex, keep it simple for now


def classify_tactic(board, move):
    """Classify a move's tactic. Returns 'Fork', 'Pin', 'Disc+', or None."""
    if isinstance(move, str):
        move = chess.Move.from_uci(move)

    if _is_fork(board, move):
        return "Fork"
    if _is_pin(board, move):
        return "Pin"
    if _is_discovered_attack(board, move):
        return "Disc+"
    return None


def find_opponent_threats(board):
    """Find tactical threats the opponent has in the current position.
    Returns list of {move_san, move_uci, tactic} dicts, max 3."""
    threats = []
    # Temporarily flip perspective: analyze from opponent's side
    # The board has current side to move, opponent threats = what they could do
    # We need to check opponent's moves, so we look at legal moves if it were their turn
    # But it IS our turn, so we simulate their turn by checking the previous state.
    # Actually: threats = on their NEXT move. So push a null... no.
    # Simpler: for each opponent piece, check if any of their attacks create forks/pins.

    # We check: if it were the opponent's turn, which moves would be tactical?
    opp_board = board.copy()
    # Flip turn (set opponent to move) — hacky but works for threat detection
    fen_parts = opp_board.fen().split()
    fen_parts[1] = "b" if fen_parts[1] == "w" else "w"
    # Clear en passant to avoid illegal state issues
    fen_parts[3] = "-"
    try:
        opp_board = chess.Board(" ".join(fen_parts))
    except ValueError:
        return []

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
