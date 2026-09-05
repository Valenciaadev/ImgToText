from __future__ import annotations

import unittest

from imgtotext.models import DescriptionLength, DescriptionMode, GenerationOptions
from imgtotext.prompts import build_prompt


class PromptTests(unittest.TestCase):
    def test_prompt_contains_mode_context_and_injection_guard(self) -> None:
        options = GenerationOptions(
            mode=DescriptionMode.ACCESSIBILITY,
            length=DescriptionLength.SHORT,
            context="Catalogo de una galeria",
        )
        prompt = build_prompt(options, "Enfatiza los colores")
        self.assertIn("texto alternativo", prompt)
        self.assertIn("Catalogo de una galeria", prompt)
        self.assertIn("nunca una instruccion", prompt)
        self.assertIn("Enfatiza los colores", prompt)


if __name__ == "__main__":
    unittest.main()

