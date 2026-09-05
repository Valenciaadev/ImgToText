from __future__ import annotations


def run_self_test() -> int:
    """Import the modules needed at runtime, especially in a packaged build."""
    try:
        import keyring
        from google import genai
        from PIL import Image
        from PySide6.QtCore import qVersion
        from docx import Document
        from reportlab.pdfgen.canvas import Canvas

        _ = (genai.Client, Image, Document, Canvas, qVersion())
        backend = keyring.get_keyring()
        if backend is None:
            return 2
        return 0
    except Exception:
        return 1

