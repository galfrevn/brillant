import ctypes
import mss
import imagehash
from PIL import Image
import cv2
import numpy as np

# Make this process DPI-aware on Windows so mss coordinates match the real screen
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def capture_board(region):
    """Capture the board region of the screen and return a PIL Image (RGB)."""
    with mss.mss() as sct:
        screenshot = sct.grab(region)
    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    return img


def has_board_changed(current_img, previous_hash, threshold=5):
    """Detect whether the board has changed using perceptual hashing.

    Returns (changed: bool, current_hash).
    """
    current_hash = imagehash.phash(current_img)
    if previous_hash is None:
        return (True, current_hash)
    distance = current_hash - previous_hash
    changed = distance > threshold
    return (changed, current_hash)


def calibrate():
    """Interactive calibration: user selects the board region and playing color.

    Returns (region_dict, player_color) where region_dict has keys
    {top, left, width, height} and player_color is "white" or "black".
    """
    print("Open chess.com and start a game. Press Enter when ready.")
    input()

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        screenshot = sct.grab(monitor)
        print(f"Screen captured: {screenshot.width}x{screenshot.height}")

    img_np = np.array(screenshot)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)

    # Scale down for display so it fits the screen
    display_h, display_w = img_bgr.shape[:2]
    scale = min(1.0, 900 / display_h, 1600 / display_w)
    if scale < 1.0:
        display_img = cv2.resize(img_bgr, None, fx=scale, fy=scale)
    else:
        display_img = img_bgr

    points = []

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 2:
            # Convert display coords back to real screen coords
            real_x = int(x / scale) + monitor["left"]
            real_y = int(y / scale) + monitor["top"]
            points.append((real_x, real_y))
            print(f"Point {len(points)} selected: ({real_x}, {real_y})")

    window_name = "Click top-left then bottom-right of the board"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(window_name, display_img)
    cv2.setMouseCallback(window_name, mouse_callback)

    while len(points) < 2:
        if cv2.waitKey(1) == 27:  # ESC to cancel
            break

    cv2.destroyAllWindows()

    if len(points) < 2:
        raise SystemExit("Calibration cancelled.")

    top_left = points[0]
    bottom_right = points[1]

    region = {
        "top": min(top_left[1], bottom_right[1]),
        "left": min(top_left[0], bottom_right[0]),
        "width": abs(bottom_right[0] - top_left[0]),
        "height": abs(bottom_right[1] - top_left[1]),
    }

    print(f"Board region: {region}")

    # Auto-generate templates from starting position
    print("\nMake sure the board shows the STARTING POSITION (any side).")
    input("Press Enter to capture templates...")
    board_img = capture_board(region)

    # Auto-detect which color is at the bottom to generate correct templates
    gray = np.array(board_img.convert("L"))
    sq_h = gray.shape[0] // 8
    # Bottom row is brighter if white pieces (white pieces are lighter)
    top_brightness = gray[:sq_h, :].mean()
    bottom_brightness = gray[-sq_h:, :].mean()
    player_color = "white" if bottom_brightness > top_brightness else "black"
    print(f"Detected {player_color} at bottom — generating templates...")

    _generate_templates_from_board(board_img, player_color)

    return (region, player_color)


def _generate_templates_from_board(board_img, player_color):
    """Generate 20 piece templates from a starting position capture."""
    import os

    w, h = board_img.size
    sq_w, sq_h = w // 8, h // 8
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

    # Starting position piece map: (row, col) -> (filename, square_color)
    # Row 0 = top of screen. If white: top = rank 8 (black pieces)
    # If black: top = rank 1 (white pieces)
    if player_color == "white":
        pieces = {
            # Black pieces at top
            (0, 0): ("br", "light"), (0, 1): ("bn", "dark"),
            (0, 2): ("bb", "light"), (0, 3): ("bq", "dark"),
            (0, 4): ("bk", "light"), (0, 5): ("bb", "dark"),
            (0, 6): ("bn", "light"), (0, 7): ("br", "dark"),
            (1, 0): ("bp", "dark"),  (1, 1): ("bp", "light"),
            # White pieces at bottom
            (6, 0): ("wp", "light"), (6, 1): ("wp", "dark"),
            (7, 0): ("wr", "dark"),  (7, 1): ("wn", "light"),
            (7, 2): ("wb", "dark"),  (7, 3): ("wq", "light"),
            (7, 4): ("wk", "dark"),  (7, 5): ("wb", "light"),
            (7, 6): ("wn", "dark"),  (7, 7): ("wr", "light"),
        }
    else:
        # Black perspective: white at top, black at bottom
        pieces = {
            # White pieces at top (row 0 = rank 1 visually flipped)
            (0, 0): ("wr", "light"), (0, 1): ("wn", "dark"),
            (0, 2): ("wb", "light"), (0, 3): ("wk", "dark"),
            (0, 4): ("wq", "light"), (0, 5): ("wb", "dark"),
            (0, 6): ("wn", "light"), (0, 7): ("wr", "dark"),
            (1, 0): ("wp", "dark"),  (1, 1): ("wp", "light"),
            # Black pieces at bottom
            (6, 0): ("bp", "light"), (6, 1): ("bp", "dark"),
            (7, 0): ("br", "dark"),  (7, 1): ("bn", "light"),
            (7, 2): ("bb", "dark"),  (7, 3): ("bk", "light"),
            (7, 4): ("bq", "dark"),  (7, 5): ("bb", "light"),
            (7, 6): ("bn", "dark"),  (7, 7): ("br", "light"),
        }

    saved = set()
    for (row, col), (piece, color) in pieces.items():
        key = (piece, color)
        if key in saved:
            continue
        x0, y0 = col * sq_w, row * sq_h
        square = board_img.crop((x0, y0, x0 + sq_w, y0 + sq_h))
        path = os.path.join(templates_dir, color, f"{piece}.png")
        square.save(path)
        saved.add(key)

    print(f"Generated {len(saved)} templates from live board ({sq_w}x{sq_h} per square).")
    print("Note: 4 templates (king/queen on opposite square color) need manual creation.")
