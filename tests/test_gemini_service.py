from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imgtotext.gemini_service import GeminiService, prepare_image
from imgtotext.models import GenerationOptions


class FakeInteraction:
    def __init__(self, payload: dict[str, str]) -> None:
        self.output_text = json.dumps(payload)


class FakeInteractions:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def create(self, **kwargs: object) -> FakeInteraction:
        self.arguments = kwargs
        return FakeInteraction(
            {
                "description": "Una figura azul centrada.",
                "visible_text": "",
                "uncertainty": "",
            }
        )


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()


class GeminiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.image_path = Path(self.folder.name) / "large.png"
        Image.new("RGBA", (4000, 2000), (20, 40, 220, 128)).save(self.image_path)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_prepare_image_resizes_and_converts(self) -> None:
        data, mime_type = prepare_image(self.image_path, max_dimension=1000)
        self.assertEqual(mime_type, "image/jpeg")
        from io import BytesIO

        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (1000, 500))

    def test_describe_uses_structured_inline_request(self) -> None:
        service = object.__new__(GeminiService)
        service._client = FakeClient()
        progress: list[tuple[int, str]] = []
        result = service.describe(
            self.image_path,
            GenerationOptions(),
            progress_callback=lambda value, message: progress.append((value, message)),
        )
        self.assertEqual(result.description, "Una figura azul centrada.")
        args = service._client.interactions.arguments
        self.assertEqual(args["model"], "gemini-3.6-flash")
        self.assertEqual(args["response_format"]["mime_type"], "application/json")
        self.assertEqual(args["input"][1]["type"], "image")
        self.assertEqual([value for value, _message in progress], [8, 28, 42, 88, 100])


if __name__ == "__main__":
    unittest.main()
