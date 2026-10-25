#!/usr/bin/env python3
"""Render a static, orientation-correct tile without changing its source picture."""
import json
from pathlib import Path
import sys
import warnings

from PIL import Image, ImageCms, ImageOps

MAX_EDGE = 800
Image.MAX_IMAGE_PIXELS = 50_000_000


def create_thumbnail(source, destination):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as original:
            # Animated pictures use their first frame for the tile; the viewer keeps the original.
            image = ImageOps.exif_transpose(original)
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            profile = image.info.get("icc_profile")
            if profile:
                from io import BytesIO
                try:
                    image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(BytesIO(profile)),
                                                     ImageCms.createProfile("sRGB"), outputMode="RGBA" if "A" in image.getbands() else "RGB")
                except (ImageCms.PyCMSError, OSError, ValueError):
                    pass  # Some cameras embed broken profiles; still render the picture.
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
            # Strip EXIF (including GPS) and other inherited metadata from the derivative.
            image.info.clear()
            image.save(destination, "WEBP", quality=82, method=6)
            return {"width": image.width, "height": image.height, "bytes": Path(destination).stat().st_size}


if __name__ == "__main__":
    try:
        print(json.dumps(create_thumbnail(sys.argv[1], sys.argv[2])))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
