"""Allowlisted text and bounded decoded raster images; never execute content."""
from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from io import BytesIO
import re
import unicodedata
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from app.core.errors import ApiError
from app.evidence.schemas import FileInput, MAX_UPLOAD_BYTES, MAX_TEXT_BYTES

FORMATS = {
    '.txt': ('text/plain', None), '.md': ('text/markdown', None),
    '.csv': ('text/csv', None), '.json': ('application/json', None),
    '.png': ('image/png', 'PNG'), '.jpg': ('image/jpeg', 'JPEG'),
    '.jpeg': ('image/jpeg', 'JPEG'), '.webp': ('image/webp', 'WEBP'),
}
MAX_PIXELS = 8_000_000
MAX_DIMENSION = 8192
MAX_PREVIEW_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class CheckedFile:
    filename: str
    media_type: str
    data: bytes
    preview: bytes | None
    width: int | None = None
    height: int | None = None


def invalid(message='This artifact is not an allowed, valid file.'):
    return ApiError(422, 'invalid_artifact', message)


def filename_and_format(value: str):
    value = unicodedata.normalize('NFC', value)
    # Original filename is a display label ONLY, never a stored path.
    if (not 1 <= len(value) <= 120 or value[0] in '.- ' or value[-1] in '. '
        or '..' in value or any(c in '/\\:%<>|?*"' or unicodedata.category(c) in {'Cc', 'Cf'} for c in value)
        or value.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}):
        raise invalid('Use a short filename without paths, reserved names or hidden controls.')
    extension = '.' + value.rsplit('.', 1)[-1].lower()
    if extension not in FORMATS:
        raise invalid('Allowed files: TXT, MD, CSV, JSON, PNG, JPEG and static WebP.')
    return value, FORMATS[extension]


def checked_file(body: FileInput) -> CheckedFile:
    filename, (media_type, image_format) = filename_and_format(body.filename)
    if body.media_type.lower() != media_type:
        raise invalid('The declared file type does not match its extension.')
    try: data = b64decode(body.content_base64, validate=True)
    except (ValueError, Base64Error): raise invalid('The file encoding is invalid.') from None
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, 'artifact_too_large', 'Artifacts must contain between 1 byte and 2 MiB.')
    if image_format is None:
        if len(data) > MAX_TEXT_BYTES:
            raise ApiError(413, 'text_too_large', 'Text artifacts are limited to 256 KiB.')
        try: text = data.decode('utf-8-sig')
        except UnicodeDecodeError: raise invalid('Text artifacts must be valid UTF-8.') from None
        if not text.strip() or any(unicodedata.category(c) in {'Cc', 'Cf'} and c not in '\n\r\t' for c in text):
            raise invalid('Text artifacts cannot contain binary data or hidden controls.')
        return CheckedFile(filename, media_type, data, None)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=[image_format]) as image:
                width, height = image.size
                if (image.format != image_format or not 0 < width <= MAX_DIMENSION
                    or not 0 < height <= MAX_DIMENSION or width * height > MAX_PIXELS
                    or getattr(image, 'n_frames', 1) != 1):
                    raise invalid('Use one static raster image of at most 8 million pixels and 8,192 pixels per side.')
                image.verify()
            with Image.open(BytesIO(data), formats=[image_format]) as image:
                image.load()  # verify() alone does not fully decode the pixel data.
                preview_image = ImageOps.exif_transpose(image).convert('RGBA')
                preview_image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                # A fresh image drops metadata, EXIF, comments, ICC and ancillary data.
                clean = Image.new('RGBA', preview_image.size)
                clean.paste(preview_image)
                target = BytesIO(); clean.save(target, format='PNG', optimize=False)
                preview = target.getvalue()
                if len(preview) > MAX_PREVIEW_BYTES: raise invalid('The regenerated preview is too large.')
                return CheckedFile(filename, media_type, data, preview, width, height)
    except ApiError: raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise invalid('The raster image could not be safely decoded.') from None
