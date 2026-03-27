import chess
import chess.engine


class StockfishEngine:
    def __init__(self, path="stockfish/stockfish.exe", depth=20, threads=2, hash_size=128, engine_time=5):
        self.path = path
        self.depth = depth
        self.engine_time = engine_time
        self.threads = threads
        self.hash_size = hash_size
        self._start_engine()

    def _start_engine(self):
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self.engine.configure({"Threads": self.threads, "Hash": self.hash_size})

    def analyze_top_moves(self, fen, num_moves=5, depth=None, time_limit=None):
        board = chess.Board(fen)
        try:
            results = self.engine.analyse(
                board,
                chess.engine.Limit(
                    depth=depth or self.depth,
                    time=time_limit or self.engine_time),
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

            # Convert full PV to SAN and UCI
            pv_san = []
            pv_uci = []
            temp = board.copy()
            for m in info["pv"]:
                pv_san.append(temp.san(m))
                pv_uci.append(m.uci())
                temp.push(m)

            moves.append((move_uci, move_san, eval_cp, mate_in, pv_san, pv_uci))

        return moves

    def close(self):
        self.engine.quit()
