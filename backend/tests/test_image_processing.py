from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.images.processing import (
    LARGE_WIDTH,
    MEDIUM_WIDTH,
    SMALL_WIDTH,
    ProcessedImage,
    process_image,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg(width: int = 800, height: int = 600, orientation: int | None = None) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    kwargs: dict = {}
    if orientation is not None:
        exif = img.getexif()
        exif[0x0112] = orientation  # Orientation tag
        kwargs["exif"] = exif.tobytes()
    buf = BytesIO()
    img.save(buf, format="JPEG", **kwargs)
    return buf.getvalue()


def _make_jpeg_with_gps() -> bytes:
    """Return a JPEG with GPS coordinates in EXIF, simulating an iPhone photo."""
    img = Image.new("RGB", (800, 600), color=(100, 150, 200))
    exif = img.getexif()
    exif[0x010F] = "Apple"         # Make
    exif[0x0110] = "iPhone 15 Pro" # Model
    exif[0x0112] = 1               # Orientation: normal
    # GPS sub-IFD (tag 0x8825 = 34853); coordinates near San Francisco.
    # Pillow requires IFDRational for RATIONAL-type GPS tags — plain tuples fail.
    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = "N"                                                           # GPSLatitudeRef
    gps_ifd[2] = (IFDRational(37), IFDRational(46), IFDRational(0))           # GPSLatitude
    gps_ifd[3] = "W"                                                           # GPSLongitudeRef
    gps_ifd[4] = (IFDRational(122), IFDRational(25), IFDRational(0))          # GPSLongitude
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProcessImage:
    def test_returns_processed_image_dataclass(self):
        result = process_image(_make_jpeg())
        assert isinstance(result, ProcessedImage)

    def test_all_outputs_are_webp(self):
        result = process_image(_make_jpeg())
        for name, data in [("small", result.small), ("medium", result.medium), ("large", result.large)]:
            assert _open(data).format == "WEBP", f"{name} output is not WebP"

    def test_resizes_large_image_to_target_widths(self):
        result = process_image(_make_jpeg(3000, 2000))
        assert _open(result.small).width == SMALL_WIDTH
        assert _open(result.medium).width == MEDIUM_WIDTH
        assert _open(result.large).width == LARGE_WIDTH

    def test_does_not_upscale_small_image(self):
        """Images narrower than a target size must not be enlarged."""
        tiny = _make_jpeg(200, 150)
        result = process_image(tiny)
        assert _open(result.small).width == 200
        assert _open(result.medium).width == 200
        assert _open(result.large).width == 200

    def test_preserves_aspect_ratio(self):
        result = process_image(_make_jpeg(3000, 2000))
        small = _open(result.small)
        expected_height = round(2000 * SMALL_WIDTH / 3000)
        assert small.width == SMALL_WIDTH
        assert small.height == expected_height

    def test_records_original_dimensions(self):
        result = process_image(_make_jpeg(1200, 900))
        assert result.original_width == 1200
        assert result.original_height == 900

    def test_applies_exif_orientation(self):
        """
        Orientation 6 (rotate 270° CCW = 90° CW) stored on an 800×600 landscape image
        should produce a 600×800 portrait result and report those corrected dimensions.
        """
        raw = _make_jpeg(800, 600, orientation=6)
        result = process_image(raw)
        assert result.original_width == 600
        assert result.original_height == 800

    def test_exif_and_gps_stripped(self):
        """
        All EXIF data — including GPS coordinates from iPhone photos — must be
        absent from every output size. This protects the owner's home address.
        """
        raw = _make_jpeg_with_gps()

        # Confirm the source image actually carries GPS before we process it
        source_exif = Image.open(BytesIO(raw)).getexif()
        assert source_exif.get_ifd(0x8825), (
            "Test setup error: source JPEG has no GPS data — the assertion below would be vacuous"
        )

        result = process_image(raw)

        for label, data in [("small", result.small), ("medium", result.medium), ("large", result.large)]:
            out_exif = _open(data).getexif()
            assert len(out_exif) == 0, f"{label}: EXIF tags found after processing: {dict(out_exif)}"
            assert out_exif.get_ifd(0x8825) == {}, f"{label}: GPS data survived processing"

    def test_accepts_png(self):
        img = Image.new("RGB", (600, 400), color=(50, 100, 150))
        buf = BytesIO()
        img.save(buf, format="PNG")
        result = process_image(buf.getvalue())
        assert _open(result.small).format == "WEBP"

    def test_accepts_heic(self):
        """HEIC input (iPhone camera roll) should be processed without error."""
        pillow_heif = pytest.importorskip("pillow_heif")
        img = Image.new("RGB", (600, 400), color=(80, 120, 160))
        heif_img = pillow_heif.from_pillow(img)
        buf = BytesIO()
        try:
            heif_img.save(buf)
        except Exception:
            pytest.skip("HEIC encoding not available in this environment")
        result = process_image(buf.getvalue())
        assert _open(result.small).format == "WEBP"
