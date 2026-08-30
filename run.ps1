param(
    [int]$Port = 8501
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw 'Project environment is missing. Run .\setup.ps1 first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'data\gameops_demo.db'))) {
    & $VenvPython (Join-Path $ProjectRoot 'scripts\bootstrap_demo.py')
}
Set-Location -LiteralPath $ProjectRoot
& $VenvPython -m streamlit run app.py --server.port $Port --server.headless true

