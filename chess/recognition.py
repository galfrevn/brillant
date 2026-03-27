"""Board recognition via OpenCV template matching."""

import cv2
import numpy as np
import os
import sys
from PIL import Image


# Mapping from template filename stem to piece symbol.
# Uppercase = white, lowercase = black.
_FILE_TO_SYMBOL = {
    "wp": "P", "wn": "N", "wb": "B", "wr": "R", "wq": "Q", "wk": "K",
    "bp": "p", "bn": "n", "bb": "b", "br": "r", "bq": "q", "bk": "k",
}


def load_templates(templates_dir=None):
    """Load 24 PNG piece templates (12 on light squares, 12 on dark squares).

    Returns a dict keyed by ``(square_color, piece_symbol)`` where
    *square_color* is ``"light"`` or ``"dark"`` and *piece_symbol* is one of
    ``P N B R Q K p n b r q k``.  Each value is a grayscale ``numpy.ndarray``.
    """
    if templates_dir is None:
        templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    templates = {}
    for square_color in ("light", "dark"):
        color_dir = os.path.join(templates_dir, square_color)
        for stem, symbol in _FILE_TO_SYMBOL.items():
            path = os.path.join(color_dir, f"{stem}.png")
            if not os.path.isfile(path):
                print(f"WARNING: template not found – {path}", file=sys.stderr)
                continue
            try:
                pil_img = Image.open(path).convert("L")
                img = np.array(pil_img)
            except Exception:
                print(f"WARNING: failed to read template – {path}", file=sys.stderr)
                continue
            templates[(square_color, symbol)] = img
    return templates


def recognize_board(board_img, templates, player_color, confidence=0.8):
    """Recognise pieces on *board_img* using template matching.

    Parameters
    ----------
    board_img : PIL.Image.Image
        Screenshot of the chess board (square, or close to it).
    templates : dict
        Output of :func:`load_templates`.
    player_color : str
        ``"white"`` or ``"black"`` – which colour is at the bottom of the
        screen.
    confidence : float
        Minimum ``TM_CCOEFF_NORMED`` score to accept a match.

    Returns
    -------
    list[list[str | None]]
        8×8 grid where ``grid[0]`` is rank 8 and ``grid[7]`` is rank 1
        (regardless of *player_color*).  Each cell is a piece symbol
        (``P N B R Q K p n b r q k``) or ``None`` for an empty square.
    """
    # Convert PIL image to grayscale numpy array.
    gray = np.array(board_img.convert("L"))
    h, w = gray.shape
    sq_h = h // 8
    sq_w = w // 8

    piece_grid = [[None] * 8 for _ in range(8)]

    for row in range(8):
        for col in range(8):
            # --- extract the square image --------------------------------
            y0 = row * sq_h
            x0 = col * sq_w
            square_img = gray[y0 : y0 + sq_h, x0 : x0 + sq_w]
            cell_h, cell_w = sq_h, sq_w

            # --- skip empty squares (low pixel variance = no piece) --------
            if square_img.std() < 10:
                continue  # Empty square — leave as None

            # --- crop center of the square to avoid coordinate labels ----
            margin_y = cell_h // 6
            margin_x = cell_w // 6
            center_img = square_img[margin_y : cell_h - margin_y,
                                    margin_x : cell_w - margin_x]

            # --- determine expected square colour, try it first -----------
            # The visual checkerboard pattern is always the same in the image
            # regardless of board orientation (top-left is always light).
            is_light = (row + col) % 2 == 0
            sq_color = "light" if is_light else "dark"
            other_color = "dark" if is_light else "light"

            best_score = -1.0
            best_symbol = None

            # First pass: expected square color
            for (tc, symbol), tmpl in templates.items():
                if tc != sq_color:
                    continue
                resized = cv2.resize(tmpl, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
                resized_center = resized[margin_y : cell_h - margin_y,
                                         margin_x : cell_w - margin_x]
                result = cv2.matchTemplate(center_img, resized_center, cv2.TM_CCOEFF_NORMED)
                score = result.max()
                if score > best_score:
                    best_score = score
                    best_symbol = symbol

            # Second pass: other color (for highlighted/selected squares)
            if best_score < confidence:
                for (tc, symbol), tmpl in templates.items():
                    if tc != other_color:
                        continue
                    resized = cv2.resize(tmpl, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
                    resized_center = resized[margin_y : cell_h - margin_y,
                                             margin_x : cell_w - margin_x]
                    result = cv2.matchTemplate(center_img, resized_center, cv2.TM_CCOEFF_NORMED)
                    score = result.max()
                    if score > best_score:
                        best_score = score
                        best_symbol = symbol
                if score > best_score:
                    best_score = score
                    best_symbol = symbol

            if best_score >= confidence:
                # Determine where in the output grid this piece belongs.
                # We want grid[0] = rank 8 always.
                if player_color == "white":
                    # row 0 in the image is already rank 8.
                    grid_row = row
                    grid_col = col
                else:
                    # row 0 in the image is rank 1 -> maps to grid row 7.
                    grid_row = 7 - row
                    grid_col = 7 - col

                piece_grid[grid_row][grid_col] = best_symbol

    return piece_grid


def board_to_fen(piece_grid, active_color):
    """Convert an 8×8 piece grid to a FEN string.

    Parameters
    ----------
    piece_grid : list[list[str | None]]
        ``piece_grid[0]`` is rank 8, ``piece_grid[7]`` is rank 1.
    active_color : str
        ``"w"`` or ``"b"`` – side to move.

    Returns
    -------
    str
        Full FEN string (with default castling/en-passant/clocks).
    """
    rank_strings = []
    for rank_row in piece_grid:
        fen_rank = ""
        empty = 0
        for cell in rank_row:
            if cell is None:
                empty += 1
            else:
                if empty:
                    fen_rank += str(empty)
                    empty = 0
                fen_rank += cell
        if empty:
            fen_rank += str(empty)
        rank_strings.append(fen_rank)

    board_fen = "/".join(rank_strings)
    return f"{board_fen} {active_color} KQkq - 0 1"


def detect_player_color(board_img, templates, confidence=0.75):
    """Auto-detect which color the player is by checking the bottom row.

    Returns ``"white"`` if white pieces are at the bottom, ``"black"``
    otherwise.
    """
    # Recognize assuming white at bottom
    pieces = recognize_board(board_img, templates, "white", confidence)

    # Count white vs black pieces in bottom two rows (rows 6-7 = ranks 1-2)
    white_bottom = 0
    black_bottom = 0
    for row in (6, 7):
        for col in range(8):
            p = pieces[row][col]
            if p is not None:
                if p.isupper():
                    white_bottom += 1
                else:
                    black_bottom += 1

    return "white" if white_bottom >= black_bottom else "black"


def _grid_pos_to_algebraic(row, col, player_color):
    """Convert grid position to algebraic notation.

    *row* / *col* refer to the piece_grid produced by :func:`recognize_board`
    where ``grid[0]`` is rank 8.
    """
    file_letter = chr(ord("a") + col)
    rank_number = 8 - row
    return f"{file_letter}{rank_number}"


def detect_turn_and_last_move(prev_pieces, curr_pieces, player_color):
    """Detect who just moved and where, by comparing two piece grids.

    Parameters
    ----------
    prev_pieces, curr_pieces : list[list[str | None]]
        8×8 grids as returned by :func:`recognize_board`.
    player_color : str
        ``"white"`` or ``"black"``.

    Returns
    -------
    tuple[str, str | None]
        ``(active_color, last_move_square)`` where *active_color* is ``"w"``
        or ``"b"`` (the side whose turn it is *next*), and
        *last_move_square* is the algebraic destination of the opponent's last
        move (e.g. ``"e4"``), or ``None`` if it could not be determined.
    """
    changed_squares = []
    for r in range(8):
        for c in range(8):
            if prev_pieces[r][c] != curr_pieces[r][c]:
                changed_squares.append((r, c))

    if not changed_squares:
        # No change detected – assume it is the player's turn.
        active = "w" if player_color == "white" else "b"
        return (active, None)

    # Determine which colour moved by inspecting what appeared / disappeared.
    appeared = []   # (row, col, symbol) – squares that gained a piece
    disappeared = []  # (row, col, symbol) – squares that lost a piece

    for r, c in changed_squares:
        prev = prev_pieces[r][c]
        curr = curr_pieces[r][c]
        if prev is not None and curr is None:
            disappeared.append((r, c, prev))
        elif prev is None and curr is not None:
            appeared.append((r, c, curr))
        elif prev is not None and curr is not None and prev != curr:
            # A piece was replaced (capture where destination already occupied).
            disappeared.append((r, c, prev))
            appeared.append((r, c, curr))

    # Figure out who moved: the colour of the piece that *appeared* on a new
    # square (the destination).  In a normal move one piece disappears from the
    # origin and the same piece appears at the destination.  In a capture a
    # defending piece also disappears.
    moved_color = None
    dest_square = None

    for r, c, sym in appeared:
        # Uppercase symbols are white pieces, lowercase are black.
        piece_is_white = sym.isupper()
        # Check if this piece also existed on one of the disappeared squares
        # (i.e. it moved from there).
        for dr, dc, dsym in disappeared:
            if dsym == sym and (dr, dc) != (r, c):
                # This piece moved from (dr,dc) to (r,c).
                moved_color = "white" if piece_is_white else "black"
                dest_square = (r, c)
                break
        if moved_color is not None:
            break

    # Fallback: if we couldn't pair origin/destination, just use the first
    # piece that appeared.
    if moved_color is None and appeared:
        r, c, sym = appeared[0]
        moved_color = "white" if sym.isupper() else "black"
        dest_square = (r, c)

    # The *next* active colour is the opposite of whoever just moved.
    if moved_color == "white":
        active_color = "b"
    elif moved_color == "black":
        active_color = "w"
    else:
        # Could not determine – default to player's colour.
        active_color = "w" if player_color == "white" else "b"

    last_move_sq = None
    if dest_square is not None:
        last_move_sq = _grid_pos_to_algebraic(dest_square[0], dest_square[1], player_color)

    return (active_color, last_move_sq)
