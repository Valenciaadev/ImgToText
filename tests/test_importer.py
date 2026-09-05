from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from imgtotext.importer import ImageImporter, natural_key


class ImageImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.importer = ImageImporter(max_images=10)

    def tearDown(self) -> None:
        self.importer.close()
        self.folder.cleanup()

    def create_image(self, name: str, color: str = "red") -> Path:
        path = self.root / name
        Image.new("RGB", (40, 30), color).save(path)
        return path

    def test_imports_valid_image_and_detects_duplicate(self) -> None:
        image = self.create_image("one.png")
        items, errors = self.importer.load_paths([image, image])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].display_name, "one.png")
        self.assertTrue(any("duplicada" in error for error in errors))

    def test_zip_keeps_natural_filename_order(self) -> None:
        image_10 = self.create_image("10.png", "blue")
        image_2 = self.create_image("2.png", "green")
        archive_path = self.root / "images.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(image_10, "folder/image10.png")
            archive.write(image_2, "folder/image2.png")
        items, errors = self.importer.load_paths([archive_path])
        self.assertFalse(errors)
        self.assertEqual([item.display_name for item in items], ["folder/image2.png", "folder/image10.png"])

    def test_zip_rejects_path_traversal(self) -> None:
        image = self.create_image("safe.png")
        archive_path = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(image, "../outside.png")
        items, errors = self.importer.load_paths([archive_path])
        self.assertFalse(items)
        self.assertTrue(any("Ruta insegura" in error for error in errors))

    def test_natural_key(self) -> None:
        names = ["image10.png", "image2.png", "image1.png"]
        self.assertEqual(sorted(names, key=natural_key), ["image1.png", "image2.png", "image10.png"])


if __name__ == "__main__":
    unittest.main()

