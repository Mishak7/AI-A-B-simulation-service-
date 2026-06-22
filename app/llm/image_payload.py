import io

from PIL import Image


def prepare_chat_image(
    image_bytes: bytes,
    mime_type: str,
    *,
    max_dimension: int = 1600,
    max_bytes: int = 700_000,
) -> tuple[bytes, str]:
    """Return a compact vision-model copy while leaving the source untouched."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        if max(image.size) <= max_dimension and len(image_bytes) <= max_bytes:
            return image_bytes, mime_type

        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image.convert("RGB"), mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")

        for quality in (85, 75, 65):
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            prepared = output.getvalue()
            if len(prepared) <= max_bytes:
                return prepared, "image/jpeg"
        return prepared, "image/jpeg"
