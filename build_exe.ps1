$ErrorActionPreference = "Stop"
$Python = "C:\Users\Larissi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
& $Python -c "import PIL, reportlab, packaging, PyInstaller"
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar as dependências." }
}
& $Python -m unittest discover -v
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; o instalador não será gerado." }
& $Python -m PyInstaller --noconfirm --clean --windowed --onefile --name "ControleDeVendas" --distpath "work\payload" --workpath "work\pyinstaller" --specpath "work" main.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o aplicativo." }
$Payload = (Resolve-Path "work\payload\ControleDeVendas.exe").Path
& $Python -m PyInstaller --noconfirm --clean --windowed --onefile --name "ControleDeVendas-Setup" --add-binary "$Payload;." --distpath "outputs" --workpath "work\setup" --specpath "work" installer_launcher.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
$Hash = (Get-FileHash "outputs\ControleDeVendas-Setup.exe" -Algorithm SHA256).Hash.ToLower()
"$Hash  ControleDeVendas-Setup.exe" | Set-Content -Encoding Ascii "outputs\SHA256.txt"
Write-Host "Instalador criado em outputs\ControleDeVendas-Setup.exe"
