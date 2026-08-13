$ErrorActionPreference = "Stop"
$Python = $env:VENDAS_PRO_PYTHON
if (-not $Python) {
    $Candidates = @(
        (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
        "python"
    )
    foreach ($Candidate in $Candidates) {
        try {
            & $Candidate -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $Python = $Candidate
                break
            }
        }
        catch {
            continue
        }
    }
}
if (-not $Python) {
    throw "Python 3.10 ou superior não foi encontrado. Defina VENDAS_PRO_PYTHON com o caminho do python.exe."
}
& $Python -c "import PIL, reportlab, packaging, PyInstaller, ruff"
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar as dependências." }
}
& $Python -m ruff check --select E4,E7,E9,F,I,UP,B,C4 main.py installer_launcher.py sales_control tests
if ($LASTEXITCODE -ne 0) { throw "A análise estática encontrou erros; o instalador não será gerado." }
& $Python -m unittest discover -v
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; o instalador não será gerado." }
& $Python -m PyInstaller --noconfirm --clean --windowed --onefile --collect-submodules "reportlab.graphics.barcode" --collect-data "reportlab" --name "ControleDeVendas" --distpath "work\payload" --workpath "work\pyinstaller" --specpath "work" main.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o aplicativo." }
$Payload = (Resolve-Path "work\payload\ControleDeVendas.exe").Path
$SmokeTest = Start-Process -FilePath $Payload -ArgumentList "--smoke-test" -Wait -PassThru -WindowStyle Hidden
if ($SmokeTest.ExitCode -ne 0) { throw "O aplicativo empacotado falhou no teste de inicialização e etiquetas." }
& $Python -m PyInstaller --noconfirm --clean --windowed --onefile --name "ControleDeVendas-Setup" --add-binary "$Payload;." --distpath "outputs" --workpath "work\setup" --specpath "work" installer_launcher.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
$SmokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("VendasPRO-Install-Smoke-" + [guid]::NewGuid().ToString("N"))
$InstallDir = Join-Path $SmokeRoot "app"
$DataDir = Join-Path $SmokeRoot "data"
New-Item -ItemType Directory -Path $SmokeRoot | Out-Null
try {
    $env:VENDAS_PRO_INSTALL_DIR = $InstallDir
    $env:VENDAS_PRO_DATA_DIR = $DataDir
    $env:VENDAS_PRO_SKIP_SHORTCUTS = "1"
    $env:VENDAS_PRO_SKIP_STOP = "1"
    $Setup = (Resolve-Path "outputs\ControleDeVendas-Setup.exe").Path
    $InstallTest = Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT", "/NOLAUNCH" -Wait -PassThru -WindowStyle Hidden
    if ($InstallTest.ExitCode -ne 0) { throw "O instalador completo falhou no teste." }
    $InstalledApp = Join-Path $InstallDir "ControleDeVendas.exe"
    if (-not (Test-Path $InstalledApp)) { throw "O instalador não criou o aplicativo no destino de teste." }
    $InstalledSmokeTest = Start-Process -FilePath $InstalledApp -ArgumentList "--smoke-test" -Wait -PassThru -WindowStyle Hidden
    if ($InstalledSmokeTest.ExitCode -ne 0) { throw "O aplicativo instalado falhou no teste final." }
}
finally {
    Remove-Item Env:VENDAS_PRO_INSTALL_DIR, Env:VENDAS_PRO_DATA_DIR, Env:VENDAS_PRO_SKIP_SHORTCUTS, Env:VENDAS_PRO_SKIP_STOP -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $SmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
}
$Hash = (Get-FileHash "outputs\ControleDeVendas-Setup.exe" -Algorithm SHA256).Hash.ToLower()
"$Hash  ControleDeVendas-Setup.exe" | Set-Content -Encoding Ascii "outputs\SHA256.txt"
Write-Host "Instalador criado em outputs\ControleDeVendas-Setup.exe"
