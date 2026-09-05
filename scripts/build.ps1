$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "No existe .venv. Crea el entorno e instala el proyecto antes de compilar."
}

Push-Location $projectRoot
try {
    & $pythonPath "scripts\prepare_assets.py"
    if ($LASTEXITCODE -ne 0) { throw "No fue posible preparar los recursos visuales." }

    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallaron." }

    & $pythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name ImgToText `
        --paths src `
        --icon "assets\ImgToText.ico" `
        --add-data "assets\ImgToText.ico;assets" `
        --collect-all keyring `
        --hidden-import keyring.backends.Windows `
        --hidden-import win32ctypes.pywin32.win32cred `
        src\imgtotext\__main__.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller no pudo crear el ejecutable." }

    $executablePath = Join-Path $projectRoot "dist\ImgToText\ImgToText.exe"
    $diagnosticProcess = Start-Process `
        -FilePath $executablePath `
        -ArgumentList "--self-test" `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($diagnosticProcess.ExitCode -ne 0) { throw "El autodiagnostico del ejecutable fallo." }
} finally {
    Pop-Location
}

Write-Host "Compilacion lista en dist\ImgToText"
