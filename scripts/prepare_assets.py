from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "Contexto" / "logo.jpg"
ASSETS = PROJECT_ROOT / "assets"


def fitted_logo(source: Image.Image, size: tuple[int, int], padding: int = 0) -> Image.Image:
    canvas = Image.new("RGB", size, "#071b2d")
    target = (max(1, size[0] - padding * 2), max(1, size[1] - padding * 2))
    logo = ImageOps.contain(source, target, Image.Resampling.LANCZOS)
    x = (size[0] - logo.width) // 2
    y = (size[1] - logo.height) // 2
    canvas.paste(logo, (x, y))
    return canvas


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"No se encontro el logo: {SOURCE}")
    ASSETS.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as opened:
        source = ImageEnhance.Sharpness(opened.convert("RGB")).enhance(1.08)
        square = ImageOps.fit(source, (1024, 1024), Image.Resampling.LANCZOS)
        square.save(ASSETS / "ImgToText.png", optimize=True)
        square.save(
            ASSETS / "ImgToText.ico",
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        fitted_logo(source, (164, 314), padding=4).save(ASSETS / "WizardImage.bmp")
        fitted_logo(source, (55, 55)).save(ASSETS / "WizardSmallImage.bmp")
    print(f"Recursos creados en {ASSETS}")


if __name__ == "__main__":
    main()

