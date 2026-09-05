from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from PIL import Image, UnidentifiedImageError

from imgtotext.models import ImageItem


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ImportValidationError(ValueError):
    pass


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


class ImageImporter:
    def __init__(
        self,
        max_images: int = 500,
        max_file_bytes: int = 25 * 1024 * 1024,
        max_archive_bytes: int = 500 * 1024 * 1024,
        max_expanded_bytes: int = 1024 * 1024 * 1024,
        max_pixels: int = 60_000_000,
    ) -> None:
        self.max_images = max_images
        self.max_file_bytes = max_file_bytes
        self.max_archive_bytes = max_archive_bytes
        self.max_expanded_bytes = max_expanded_bytes
        self.max_pixels = max_pixels
        self._temp_dir = tempfile.TemporaryDirectory(prefix="imgtotext-")
        self._seen_hashes: set[str] = set()

    def close(self) -> None:
        self._temp_dir.cleanup()

    def load_paths(self, paths: Iterable[str | Path]) -> tuple[list[ImageItem], list[str]]:
        candidates: list[tuple[Path, str, str]] = []
        errors: list[str] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                if not path.is_file():
                    raise ImportValidationError("El archivo no existe o no es accesible")
                if path.suffix.casefold() == ".zip":
                    candidates.extend(self._extract_zip(path))
                elif path.suffix.casefold() in SUPPORTED_EXTENSIONS:
                    candidates.append((path, path.name, path.name))
                else:
                    raise ImportValidationError("Formato no compatible")
            except (OSError, zipfile.BadZipFile, ImportValidationError) as exc:
                errors.append(f"{path.name}: {exc}")

        items: list[ImageItem] = []
        for path, display_name, source_name in candidates:
            if len(items) >= self.max_images:
                errors.append(f"Se alcanzo el limite de {self.max_images} imagenes")
                break
            try:
                item = self._create_item(path, display_name, source_name)
                if item.sha256 in self._seen_hashes:
                    errors.append(f"{display_name}: imagen duplicada omitida")
                    continue
                self._seen_hashes.add(item.sha256)
                items.append(item)
            except (OSError, ImportValidationError, UnidentifiedImageError) as exc:
                errors.append(f"{display_name}: {exc}")
        return items, errors

    def forget(self, item: ImageItem) -> None:
        self._seen_hashes.discard(item.sha256)

    def _create_item(self, path: Path, display_name: str, source_name: str) -> ImageItem:
        size = path.stat().st_size
        if size <= 0:
            raise ImportValidationError("El archivo esta vacio")
        if size > self.max_file_bytes:
            raise ImportValidationError(f"Supera el limite de {self.max_file_bytes // (1024 * 1024)} MB")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
        if width <= 0 or height <= 0 or width * height > self.max_pixels:
            raise ImportValidationError("Dimensiones de imagen no permitidas")
        return ImageItem(
            path=path,
            display_name=display_name,
            source_name=source_name,
            sha256=digest.hexdigest(),
            width=width,
            height=height,
        )

    def _extract_zip(self, archive_path: Path) -> list[tuple[Path, str, str]]:
        if archive_path.stat().st_size > self.max_archive_bytes:
            raise ImportValidationError("El ZIP supera el limite permitido")
        archive_folder = Path(self._temp_dir.name) / hashlib.sha256(str(archive_path).encode()).hexdigest()[:12]
        archive_folder.mkdir(parents=True, exist_ok=True)
        extracted: list[tuple[Path, str, str]] = []
        with zipfile.ZipFile(archive_path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir() and Path(m.filename).suffix.casefold() in SUPPORTED_EXTENSIONS]
            members.sort(key=lambda member: natural_key(member.filename))
            if len(members) > self.max_images:
                raise ImportValidationError(f"El ZIP contiene mas de {self.max_images} imagenes")
            total_size = sum(member.file_size for member in members)
            if total_size > self.max_expanded_bytes:
                raise ImportValidationError("El contenido expandido del ZIP es demasiado grande")
            for index, member in enumerate(members, start=1):
                safe_name = self._validated_member_name(member)
                if member.file_size > self.max_file_bytes:
                    raise ImportValidationError(f"{safe_name}: archivo demasiado grande")
                ratio = member.file_size / max(member.compress_size, 1)
                if ratio > 200:
                    raise ImportValidationError(f"{safe_name}: relacion de compresion sospechosa")
                destination = archive_folder / f"{index:04d}_{Path(safe_name).name}"
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                extracted.append((destination, safe_name, archive_path.name))
        if not extracted:
            raise ImportValidationError("El ZIP no contiene imagenes compatibles")
        return extracted

    @staticmethod
    def _validated_member_name(member: zipfile.ZipInfo) -> str:
        if member.flag_bits & 0x1:
            raise ImportValidationError(f"{member.filename}: los archivos cifrados no son compatibles")
        normalized = member.filename.replace("\\", "/")
        pure_path = PurePosixPath(normalized)
        if pure_path.is_absolute() or ".." in pure_path.parts or not pure_path.name:
            raise ImportValidationError(f"Ruta insegura dentro del ZIP: {member.filename}")
        if ":" in pure_path.parts[0]:
            raise ImportValidationError(f"Ruta insegura dentro del ZIP: {member.filename}")
        return pure_path.as_posix()

