from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import pillow_heif
from PIL import Image, ImageOps

# Makes Image.open() accept HEIC/HEIF files from iPhone/iPad camera rolls
pillow_heif.register_heif_opener()

SMALL_WIDTH = 400
MEDIUM_WIDTH = 1000
LARGE_WIDTH = 2000
WEBP_QUALITY = 85


@dataclass
class ProcessedImage:
    small: bytes
    medium: bytes
    large: bytes
    # Dimensions after EXIF orientation correction — matches what the browser displays
    original_width: int
    original_height: int


def process_image(data: bytes) -> ProcessedImage:
    """
    Accept JPEG, PNG, or HEIC bytes. Return three WebP sizes with EXIF stripped.

    Steps:
    1. Apply EXIF orientation so the image is right-side-up before we measure it.
    2. Convert to RGB (HEIC/PNG may be RGBA or a palette mode).
    3. Rebuild from raw pixels — Image.frombytes creates a new object with no
       .info dict, so no EXIF or GPS data can reach the WebP encoder.
    4. Resize to each target width and encode as WebP.
    """
    img = Image.open(BytesIO(data))

    # exif_transpose reads the Orientation tag, rotates/flips, and returns a
    # new image with that tag removed. Record dimensions after this correction.
    img = ImageOps.exif_transpose(img)
    original_width, original_height = img.size

    if img.mode != "RGB":
        img = img.convert("RGB")

    # Strip all metadata by reconstructing from raw pixel bytes. This is the
    # critical step that removes GPS coordinates from iPhone photos.
    clean = Image.frombytes("RGB", img.size, img.tobytes())

    return ProcessedImage(
        small=_to_webp(clean, SMALL_WIDTH),
        medium=_to_webp(clean, MEDIUM_WIDTH),
        large=_to_webp(clean, LARGE_WIDTH),
        original_width=original_width,
        original_height=original_height,
    )


def _to_webp(img: Image.Image, max_width: int) -> bytes:
    w, h = img.size
    if w > max_width:
        # Maintain aspect ratio; round to nearest integer pixel
        img = img.resize((max_width, round(h * max_width / w)), Image.LANCZOS)
    buf = BytesIO()
    # exif= not passed — Pillow's WebP encoder does not copy metadata automatically
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    return buf.getvalue()
