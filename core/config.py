"""Configuration module for the Chess Brilliant Move Detector."""

import copy
import json
import os

DEFAULT_CONFIG = {
    "stockfish_path": "../stockfish/stockfish.exe",
    "depth": 22,
    "engine_time": 3,
    "threads": 2,
    "hash_size": 128,
    "multipv": 5,
    "poll_interval": 0.3,
    "confidence": 0.75,
    "hash_threshold": 5,
    "eval_gap": 150,
    "min_eval": -50,
    "board_region": None,
    "player_color": "white",
}


def load_config(path="config.json"):
    """Load configuration from a JSON file, merged with DEFAULT_CONFIG.

    Missing keys in the file are filled in from DEFAULT_CONFIG.
    If the file does not exist, a copy of DEFAULT_CONFIG is returned.
    """
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULT_CONFIG)

    with open(path, "r", encoding="utf-8") as f:
        user_config = json.load(f)

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(user_config)
    return config


def save_config(config, path="config.json"):
    """Save a configuration dict to a JSON file with indent=2."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
