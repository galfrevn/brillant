"""Read chess.com board state via Chrome DevTools Protocol."""

import json
import os
import subprocess
import time

import requests
import websocket


def _find_chrome():
    """Find Chrome executable on Windows."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return "chrome"


def launch_chrome(port=9222):
    """Launch Chrome with remote debugging enabled."""
    chrome = _find_chrome()
    data_dir = os.path.join(os.environ.get("TEMP", "."), "chess-detector-chrome")
    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins=*",
        f"--user-data-dir={data_dir}",
        "https://www.chess.com/play/online",
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ChessBoardReader:
    def __init__(self, port=9222):
        self.port = port
        self.ws = None
        self._msg_id = 0
        self._connect()

    def _connect(self):
        """Find chess.com tab and connect via WebSocket."""
        try:
            resp = requests.get(f"http://localhost:{self.port}/json", timeout=3)
        except requests.ConnectionError:
            print("Chrome not found on debug port. Launching Chrome...")
            launch_chrome(self.port)
            for _ in range(15):
                time.sleep(1)
                try:
                    resp = requests.get(f"http://localhost:{self.port}/json", timeout=2)
                    break
                except requests.ConnectionError:
                    continue
            else:
                raise RuntimeError("Could not start Chrome.")

        tabs = resp.json()
        target = None
        for tab in tabs:
            if "chess.com" in tab.get("url", ""):
                target = tab
                break

        if target is None:
            print("Opening chess.com...")
            requests.get(
                f"http://localhost:{self.port}/json/new?https://www.chess.com/play/online",
                timeout=5,
            )
            time.sleep(3)
            resp = requests.get(f"http://localhost:{self.port}/json", timeout=3)
            for tab in resp.json():
                if "chess.com" in tab.get("url", ""):
                    target = tab
                    break

        if target is None:
            raise RuntimeError("Could not open chess.com tab.")

        ws_url = target["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url, timeout=5)

    def _eval_js(self, expression):
        """Execute JavaScript in the chess.com tab and return the result."""
        self._msg_id += 1
        msg = {
            "id": self._msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self._msg_id:
                result = resp.get("result", {}).get("result", {})
                return result.get("value")

    def get_state(self):
        """Read FEN, player color, and game status from chess.com.

        Returns dict with keys: fen, playing_as, is_game_over, result
        Or None if no board is found.
        """
        js = """
        (() => {
            const b = document.querySelector('wc-chess-board');
            if (!b || !b.game) return null;
            let fen;
            try { fen = b.game.getFEN(); } catch(e) { return null; }

            // Detect player color from board orientation
            const flipped = b.hasAttribute('flipped') ||
                (b.getAttribute('class') || '').includes('flipped');
            const playing_as = flipped ? 2 : 1;

            // Detect game over — check for visible game-over UI elements
            // state.isGameOver stays true even when reviewing, so check the DOM
            const gameOverModal = document.querySelector(
                '.game-over-modal-content, .game-result-header, ' +
                '[class*="game-over-modal"], [class*="modal-game-over"]'
            );
            const is_game_over = !!gameOverModal;

            return {
                fen: fen,
                playing_as: playing_as,
                is_game_over: is_game_over,
                result: null,
            };
        })()
        """
        return self._eval_js(js)

    def draw_arrow(self, from_sq, to_sq, color="#33cc33", width=10, label=None):
        """Draw an arrow on the board. Optional label (e.g. move number) shown at midpoint."""
        label_js = "null" if label is None else f"'{label}'"
        js = f"""
        (() => {{
            const board = document.querySelector('wc-chess-board');
            if (!board) return 'no-board';
            const canvas = board.querySelector('canvas');
            // Canvas might be direct child or the board itself acts as container
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

            // Create or reuse SVG overlay on document.body
            let svg = document.getElementById('chess-detector-arrows');
            if (!svg) {{
                svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                svg.id = 'chess-detector-arrows';
                svg.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:99999;';

                const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
                const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
                marker.id = 'chess-detector-arrowhead';
                marker.setAttribute('markerWidth', '10');
                marker.setAttribute('markerHeight', '7');
                marker.setAttribute('refX', '10');
                marker.setAttribute('refY', '3.5');
                marker.setAttribute('orient', 'auto');
                marker.setAttribute('markerUnits', 'strokeWidth');
                const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                poly.setAttribute('points', '0 0, 10 3.5, 0 7');
                poly.setAttribute('fill', '{color}');
                marker.appendChild(poly);
                defs.appendChild(marker);
                svg.appendChild(defs);

                document.body.appendChild(svg);
            }}

            const [x1, y1] = sqToXY('{from_sq}');
            const [x2, y2] = sqToXY('{to_sq}');

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x1);
            line.setAttribute('y1', y1);
            line.setAttribute('x2', x2);
            line.setAttribute('y2', y2);
            line.setAttribute('stroke', '{color}');
            line.setAttribute('stroke-width', '{width}');
            line.setAttribute('stroke-opacity', '0.8');
            line.setAttribute('stroke-linecap', 'round');
            line.setAttribute('marker-end', 'url(#chess-detector-arrowhead)');
            line.classList.add('chess-detector-arrow');
            svg.appendChild(line);

            const lbl = {label_js};
            if (lbl !== null) {{
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;
                const r = sqSize * 0.2;

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', mx);
                circle.setAttribute('cy', my);
                circle.setAttribute('r', r);
                circle.setAttribute('fill', '{color}');
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
                text.textContent = lbl;
                text.classList.add('chess-detector-arrow');
                svg.appendChild(text);
            }}

            return true;
        }})()
        """
        return self._eval_js(js)

    def draw_move_sequence(self, moves, player_color="w", our_color="#ff3333", opp_color="#888888"):
        """Draw a full PV sequence. Player moves are bold+numbered, opponent moves are dim."""
        if not moves:
            return
        move_data = []
        player_num = 0
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

    def clear_arrows(self):
        """Remove all drawn arrows."""
        js = """
        (() => {
            const svg = document.getElementById('chess-detector-arrows');
            if (svg) svg.remove();
            return true;
        })()
        """
        return self._eval_js(js)

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
