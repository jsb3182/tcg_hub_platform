import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


CELL = (300, 438)
COLUMNS, ROWS = 4, 3
LIMIT_BYTES = 8 * 1024 * 1024
LIMIT_PIXELS = 12_000_000
FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


class InvalidImage(ValueError):
    pass


def normalized_png(source: Path) -> bytes:
    expected = FORMATS.get(source.suffix.lower())
    if not expected:
        raise InvalidImage("Expected .jpg, .jpeg, .png or .webp")
    with source.open("rb") as stream:
        data = stream.read(LIMIT_BYTES + 1)
    if len(data) > LIMIT_BYTES:
        raise InvalidImage("Image exceeds 8 MiB")
    try:
        with Image.open(io.BytesIO(data), formats=[expected]) as image:
            if image.width * image.height > LIMIT_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise InvalidImage("Expected a single frame of at most 12 megapixels")
            image.verify()
        with Image.open(io.BytesIO(data), formats=[expected]) as image:
            # Apply orientation and scale before allocating the small padded cell.
            oriented = ImageOps.contain(ImageOps.exif_transpose(image), CELL, Image.Resampling.LANCZOS)
            cell = Image.new("RGB", CELL, (24, 24, 24))
            foreground = oriented.convert("RGBA")
            offset = ((CELL[0] - foreground.width) // 2, (CELL[1] - foreground.height) // 2)
            cell.paste(foreground, offset, foreground)
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InvalidImage("Damaged image or signature does not match extension") from exc
    result = io.BytesIO()
    cell.save(result, format="PNG")
    return result.getvalue()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def publish(root: Path, directory: str, data: bytes) -> str:
    key = f"{directory}/{hashlib.sha256(data).hexdigest()}.webp"
    if not (root / key).is_file():
        atomic_write(root / key, data)
    return key


def place_cell(sheet: Image.Image, data: bytes, slot: int) -> tuple[int, int]:
    col, row = slot % COLUMNS, slot // COLUMNS
    if not 0 <= row < ROWS:
        raise ValueError("Atlas is full")
    with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
        if image.size != CELL or image.n_frames != 1:
            raise InvalidImage("Unexpected spooled cell dimensions")
        sheet.paste(image.convert("RGB"), (col * CELL[0], row * CELL[1]))
    return col, row


def encode_sheet(sheet: Image.Image, *, revision: str = "") -> bytes:
    output = io.BytesIO()
    sheet.save(output, format="WEBP", quality=80, method=4, xmp=revision.encode("ascii"))
    return output.getvalue()
