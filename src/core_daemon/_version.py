from pathlib import Path

VERSION = (
    Path(__file__).resolve().parent.parent.parent / "VERSION"
).read_text().strip()
