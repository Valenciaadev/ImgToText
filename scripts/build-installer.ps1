param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$compilerCandidates = @(
    (Join-Path $projectRoot "build\tools\Inno\ISCC.exe"),
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$compilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $compilerPath) {
    throw "Inno Setup 6 no esta instalado. Instala el paquete innosetup y vuelve a ejecutar este script."
}

Push-Location $projectRoot
try {
    & ".venv\Scripts\python.exe" "scripts\prepare_assets.py"
    if ($LASTEXITCODE -ne 0) { throw "No fue posible preparar el logo." }

    & "scripts\build.ps1"
    if ($LASTEXITCODE -ne 0) { throw "No fue posible compilar ImgToText." }

    & $compilerPath "installer\ImgToText.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup no pudo crear el instalador." }

    $setupPath = Join-Path $projectRoot "installer\output\ImgToText-Setup-0.1.1.exe"
    if (-not (Test-Path -LiteralPath $setupPath)) { throw "No se encontro el instalador generado." }

    if ($SmokeTest) {
        $testInstallPath = Join-Path $projectRoot "build\installer-smoke"
        $setupProcess = Start-Process `
            -FilePath $setupPath `
            -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", "/DIR=$testInstallPath" `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
        if ($setupProcess.ExitCode -ne 0) { throw "La instalacion de prueba fallo." }

        $installedExe = Join-Path $testInstallPath "ImgToText.exe"
        $diagnosticProcess = Start-Process -FilePath $installedExe -ArgumentList "--self-test" -WindowStyle Hidden -Wait -PassThru
        if ($diagnosticProcess.ExitCode -ne 0) { throw "El ejecutable instalado fallo el autodiagnostico." }

        $uninstallerPath = Join-Path $testInstallPath "unins000.exe"
        $uninstallProcess = Start-Process `
            -FilePath $uninstallerPath `
            -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
        if ($uninstallProcess.ExitCode -ne 0) { throw "La desinstalacion de prueba fallo." }
    }
} finally {
    Pop-Location
}

Write-Host "Instalador listo en installer\output\ImgToText-Setup-0.1.1.exe"
