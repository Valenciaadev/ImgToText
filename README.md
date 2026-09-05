# ImgToText

Aplicacion de escritorio para importar una imagen, varias imagenes o un ZIP y
generar descripciones en espanol con Gemini. Cada resultado puede editarse,
copiarse, regenerarse y exportarse a PDF, DOCX o JSON.

## Requisitos

- Windows 10 u 11
- Python 3.11 o posterior
- Una clave de autorizacion de Gemini creada en Google AI Studio

## Instalacion para desarrollo

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m imgtotext
```

La clave se introduce desde **Configuracion**. Si Windows Credential Manager
esta disponible, puede guardarse alli; de lo contrario permanece solo durante
la sesion. Tambien puede definirse `GEMINI_API_KEY` o `GOOGLE_API_KEY`.

## Uso

1. Agrega imagenes o un ZIP, tambien puedes arrastrarlos sobre la ventana.
2. Elige el modo y la longitud de la descripcion.
3. Pulsa **Generar descripciones**.
4. Edita, copia o regenera resultados individuales.
5. Exporta el lote desde el menu **Exportar**.

## Seguridad y limites

- Los ZIP se validan contra rutas inseguras, archivos cifrados, expansion
  excesiva y limites de cantidad o tamano.
- Los archivos temporales extraidos se eliminan al cerrar la aplicacion.
- La clave nunca se guarda en archivos del proyecto.
- Cada imagen se procesa de forma independiente para permitir reintentos.

## Pruebas

```powershell
python -m pytest
```

## Ejecutable de Windows

```powershell
.\scripts\build.ps1
```

El script ejecuta las pruebas, compila la aplicacion y lanza el autodiagnostico
del paquete. El resultado se guarda en `dist\ImgToText`.

## Instalador de Windows

Con Inno Setup 6 instalado:

```powershell
.\scripts\build-installer.ps1
```

Para compilar, instalar en una carpeta temporal, comprobar la aplicacion y
desinstalarla automaticamente:

```powershell
.\scripts\build-installer.ps1 -SmokeTest
```

El instalador final se guarda en `installer\output`.
