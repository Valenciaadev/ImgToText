from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

from imgtotext.models import DescriptionResult, GenerationOptions
from imgtotext.prompts import RESPONSE_SCHEMA, build_prompt


class GeminiServiceError(RuntimeError):
    pass


def prepare_image(path: Path, max_dimension: int = 3072) -> tuple[bytes, str]:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        return output.getvalue(), "image/jpeg"


class GeminiService:
    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise GeminiServiceError("Falta la clave de Gemini")
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiServiceError("Falta la dependencia google-genai") from exc
        self._client = genai.Client(api_key=api_key.strip())

    def describe(
        self,
        path: Path,
        options: GenerationOptions,
        regeneration_note: str = "",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> DescriptionResult:
        report = progress_callback or (lambda _value, _message: None)
        report(8, "Preparando la imagen")
        image_bytes, mime_type = prepare_image(path)
        report(28, "Imagen optimizada")
        try:
            report(42, "Enviando la imagen a Gemini")
            interaction = self._client.interactions.create(
                model=options.model,
                input=[
                    {"type": "text", "text": build_prompt(options, regeneration_note)},
                    {
                        "type": "image",
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                        "mime_type": mime_type,
                    },
                ],
                generation_config={"thinking_level": options.thinking_level},
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": RESPONSE_SCHEMA,
                },
            )
            report(88, "Validando la respuesta")
            raw_text = (interaction.output_text or "").strip()
        except Exception as exc:
            message = str(exc)
            if "429" in message or "RESOURCE_EXHAUSTED" in message:
                raise GeminiServiceError("Se alcanzo el limite temporal de Gemini. Intenta de nuevo en unos minutos") from exc
            if "401" in message or "403" in message or "API key" in message:
                raise GeminiServiceError("Gemini rechazo la clave o el proyecto no tiene acceso") from exc
            raise GeminiServiceError(f"No fue posible obtener la descripcion: {message}") from exc
        if not raw_text:
            raise GeminiServiceError("Gemini devolvio una respuesta vacia")
        try:
            payload = json.loads(raw_text)
            description = str(payload.get("description", "")).strip()
            if not description:
                raise ValueError("Falta description")
            result = DescriptionResult(
                description=description,
                visible_text=str(payload.get("visible_text", "")).strip(),
                uncertainty=str(payload.get("uncertainty", "")).strip(),
            )
            report(100, "Descripcion completada")
            return result
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise GeminiServiceError("Gemini devolvio una respuesta con formato inesperado") from exc
