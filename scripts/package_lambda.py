"""Build a reproducible ZIP; Lambda supplies Boto3 in its Python runtime."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def package():
    root = Path(__file__).resolve().parents[1]
    target = root / "dist" / "intentguard-lambda.zip"
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted((root / "intentguard").glob("*.py")):
            archive.write(path, path.relative_to(root).as_posix())
    return target


if __name__ == "__main__":
    print(package())
