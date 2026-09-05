from __future__ import annotations

import os


SERVICE_NAME = "ImgToText.Gemini"
ACCOUNT_NAME = "default"


class CredentialStore:
    def __init__(self) -> None:
        self._session_key = ""

    def get(self) -> str:
        env_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if env_key:
            return env_key.strip()
        if self._session_key:
            return self._session_key
        try:
            import keyring

            return (keyring.get_password(SERVICE_NAME, ACCOUNT_NAME) or "").strip()
        except Exception:
            return ""

    def save(self, api_key: str, persist: bool) -> None:
        cleaned = api_key.strip()
        self._session_key = cleaned
        if not persist:
            return
        try:
            import keyring

            keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, cleaned)
        except Exception as exc:
            raise RuntimeError("No fue posible guardar la clave en el almacen seguro de Windows") from exc

    def delete(self) -> None:
        self._session_key = ""
        try:
            import keyring

            keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        except Exception:
            pass

