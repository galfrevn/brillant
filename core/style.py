"""Player style tracker — learns from your games using SQLite."""

import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_style.db")


class StyleTracker:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                played_as TEXT,
                result TEXT
            );
            CREATE TABLE IF NOT EXISTS moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                move_number INTEGER,
                fen TEXT,
                move_played TEXT,
                engine_best TEXT,
                eval_cp INTEGER,
                is_brilliant INTEGER DEFAULT 0,
                is_sacrifice INTEGER DEFAULT 0,
                is_mate_move INTEGER DEFAULT 0,
                piece_moved TEXT,
                captured_piece TEXT,
                timestamp TEXT,
                FOREIGN KEY (game_id) REFERENCES games(id)
            );
        """)
        self.conn.commit()

    def start_game(self, played_as):
        """Record start of a new game. Returns game_id."""
        cur = self.conn.execute(
            "INSERT INTO games (started_at, played_as) VALUES (?, ?)",
            (datetime.now().isoformat(), played_as),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_game(self, game_id, result="unknown"):
        """Record game result."""
        self.conn.execute(
            "UPDATE games SET result = ? WHERE id = ?",
            (result, game_id),
        )
        self.conn.commit()

    def record_move(self, game_id, move_number, fen, move_played, engine_best,
                    eval_cp, is_brilliant=False, is_sacrifice=False,
                    is_mate_move=False, piece_moved=None, captured_piece=None):
        """Record a single move."""
        self.conn.execute(
            """INSERT INTO moves
               (game_id, move_number, fen, move_played, engine_best, eval_cp,
                is_brilliant, is_sacrifice, is_mate_move, piece_moved,
                captured_piece, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (game_id, move_number, fen, move_played, engine_best, eval_cp,
             int(is_brilliant), int(is_sacrifice), int(is_mate_move),
             piece_moved, captured_piece, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_stats(self):
        """Get player style statistics."""
        stats = {}

        # Total games and results
        row = self.conn.execute("SELECT COUNT(*) FROM games").fetchone()
        stats["total_games"] = row[0]

        row = self.conn.execute("SELECT COUNT(*) FROM games WHERE result = 'win'").fetchone()
        stats["wins"] = row[0]

        # Total moves analyzed
        row = self.conn.execute("SELECT COUNT(*) FROM moves").fetchone()
        stats["total_moves"] = row[0]

        if stats["total_moves"] == 0:
            return stats

        # Brilliants
        row = self.conn.execute("SELECT COUNT(*) FROM moves WHERE is_brilliant = 1").fetchone()
        stats["brilliants"] = row[0]

        # Sacrifices
        row = self.conn.execute("SELECT COUNT(*) FROM moves WHERE is_sacrifice = 1").fetchone()
        stats["sacrifices"] = row[0]

        # Accuracy: how often player's move matched engine's best
        row = self.conn.execute(
            "SELECT COUNT(*) FROM moves WHERE move_played = engine_best"
        ).fetchone()
        stats["engine_matches"] = row[0]
        stats["accuracy"] = round(100 * row[0] / stats["total_moves"], 1)

        # Average eval
        row = self.conn.execute("SELECT AVG(eval_cp) FROM moves").fetchone()
        stats["avg_eval_cp"] = round(row[0]) if row[0] else 0

        # Favorite pieces to move
        rows = self.conn.execute(
            """SELECT piece_moved, COUNT(*) as cnt FROM moves
               WHERE piece_moved IS NOT NULL
               GROUP BY piece_moved ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()
        stats["favorite_pieces"] = rows

        # Sacrifice rate
        if stats["total_moves"] > 0:
            stats["sacrifice_rate"] = round(100 * stats["sacrifices"] / stats["total_moves"], 1)
        else:
            stats["sacrifice_rate"] = 0

        # Style classification
        stats["style"] = self._classify_style(stats)

        return stats

    def _classify_style(self, stats):
        """Classify playing style based on stats."""
        traits = []

        if stats.get("sacrifice_rate", 0) > 8:
            traits.append("Aggressive")
        elif stats.get("sacrifice_rate", 0) > 3:
            traits.append("Tactical")
        else:
            traits.append("Positional")

        if stats.get("accuracy", 0) > 70:
            traits.append("Precise")
        elif stats.get("accuracy", 0) > 50:
            traits.append("Solid")
        else:
            traits.append("Creative")

        if stats.get("brilliants", 0) > stats.get("total_games", 1) * 0.5:
            traits.append("Brilliant-finder")

        return " / ".join(traits) if traits else "Unknown"

    def get_opening_stats(self):
        """Get most common first moves."""
        rows = self.conn.execute(
            """SELECT move_played, COUNT(*) as cnt FROM moves
               WHERE move_number = 1
               GROUP BY move_played ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()
        return rows

    def get_style_profile(self):
        """Get a compact style profile for move recommendation."""
        stats = self.get_stats()
        if stats["total_moves"] < 10:
            return None  # Not enough data

        profile = {
            "prefers_sacrifices": stats.get("sacrifice_rate", 0) > 5,
            "sacrifice_rate": stats.get("sacrifice_rate", 0),
            "accuracy": stats.get("accuracy", 50),
            "favorite_pieces": {},
        }

        # Build piece preference weights
        if stats.get("favorite_pieces"):
            total = sum(c for _, c in stats["favorite_pieces"])
            for piece, count in stats["favorite_pieces"]:
                profile["favorite_pieces"][piece] = count / total

        return profile

    def score_move_for_style(self, profile, move_uci, eval_cp, best_eval_cp,
                             is_sacrifice, piece_moved):
        """Score a move based on how well it fits the player's style.

        Returns a float bonus (can be negative). The final ranking combines
        engine eval with this style bonus.
        """
        if profile is None:
            return 0.0

        bonus = 0.0

        # Sacrifice bonus for aggressive players
        if is_sacrifice and profile["prefers_sacrifices"]:
            bonus += 30  # cp bonus for sacrificial moves

        # Piece preference bonus
        if piece_moved and piece_moved in profile["favorite_pieces"]:
            weight = profile["favorite_pieces"][piece_moved]
            bonus += weight * 20  # Up to ~20cp for favorite pieces

        # Don't recommend moves that are too far from the best
        eval_loss = best_eval_cp - eval_cp
        if eval_loss > 100:  # More than 1 pawn worse — no style override
            bonus = 0.0

        return bonus

    def close(self):
        self.conn.close()
