from pathlib import Path


def package_grpc():
    dirname = str(Path(__file__).resolve().parent.parent)
    return f"{dirname}[grpc]"
