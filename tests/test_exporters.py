from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imgtotext.exporters import ExportError, export_docx, export_json, export_pdf
from imgtotext.models import ImageItem, ImageStatus


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.image_path = self.root / "sample.png"
        Image.new("RGB", (32, 24), "purple").save(self.image_path)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def make_item(self, status: ImageStatus, description: str) -> ImageItem:
        return ImageItem(
            path=self.image_path,
            display_name="sample.png",
            source_name="sample.png",
            sha256="abc",
            width=32,
            height=24,
            status=status,
            description=description,
        )

    def test_json_only_exports_completed_items(self) -> None:
        destination = self.root / "result.json"
        export_json(
            [
                self.make_item(ImageStatus.COMPLETED, "Una imagen morada."),
                self.make_item(ImageStatus.PENDING, ""),
            ],
            destination,
        )
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["images"][0]["description"], "Una imagen morada.")

    def test_export_without_results_fails(self) -> None:
        with self.assertRaises(ExportError):
            export_json([], self.root / "none.json")

    def test_pdf_and_docx_are_created(self) -> None:
        item = self.make_item(ImageStatus.COMPLETED, "Un rectangulo morado sobre fondo uniforme.")
        pdf_path = self.root / "result.pdf"
        docx_path = self.root / "result.docx"
        export_pdf([item], pdf_path)
        export_docx([item], docx_path)
        self.assertGreater(pdf_path.stat().st_size, 500)
        self.assertGreater(docx_path.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
