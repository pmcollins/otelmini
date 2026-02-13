from pathlib import Path


def package():
    return str(Path(__file__).resolve().parent.parent)
