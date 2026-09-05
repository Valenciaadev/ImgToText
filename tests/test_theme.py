from __future__ import annotations

from imgtotext.ui import build_style_sheet


def test_light_theme_styles_combo_popup_and_messages() -> None:
    style = build_style_sheet(False)
    assert "QComboBox QAbstractItemView" in style
    assert "QMessageBox QLabel" in style
    assert "background: white" in style


def test_dark_theme_has_explicit_text_and_popup_colors() -> None:
    style = build_style_sheet(True)
    assert "QWidget#central, QDialog, QMessageBox { background: #10141c; }" in style
    assert "QComboBox QAbstractItemView { background: #1a202b; color: #f0f2f6;" in style
    assert "QMessageBox QLabel, QInputDialog QLabel { color: #eef1f6; }" in style
