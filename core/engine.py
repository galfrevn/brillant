import chess
import chess.engine


class StockfishEngine:
    def __init__(self, path="stockfish/stockfish.exe", depth=20, threads=2, hash_size=128):
        self.path = path
        self.depth = depth
        self.threads = threads
        self.hash_size = hash_size
        self._start_engine()

    def _start_engine(self):
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self.engine.configure({"Threads": self.threads, "Hash": self.hash_size})

    def analyze_top_moves(self, fen, num_moves=5):
        board = chess.Board(fen)
        try:
            results = self.engine.analyse(
                board,
                chess.engine.Limit(depth=self.depth, time=10),
                multipv=num_moves,
            )
        except (chess.engine.EngineTerminatedError, chess.engine.EngineError, Exception):
            try:
                self._start_engine()
            except Exception:
                pass
            return []

        moves = []
        for info in results:
            if "pv" not in info or not info["pv"]:
                continue
            move = info["pv"][0]
            move_uci = move.uci()
            move_san = board.san(move)
            score = info["score"].white()
            eval_cp = score.score(mate_score=100000)
            mate_in = score.mate()

            # Convert full PV to SAN
            pv_san = []
            temp = board.copy()
            for m in info["pv"]:
                pv_san.append(temp.san(m))
                temp.push(m)

            moves.append((move_uci, move_san, eval_cp, mate_in, pv_san))

        return moves

    def close(self):
        self.engine.quit()
