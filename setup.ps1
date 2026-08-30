param(
    [switch]$SkipClaudeCode
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

$PythonCandidates = @(
    'F:\anaconda\python.exe',
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $PythonCandidates) {
    throw 'Python 3.10+ was not found. Install Python and rerun setup.ps1.'
}

$BootstrapPython = $PythonCandidates[0]
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $BootstrapPython -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment (exit $LASTEXITCODE)." }
}

function Invoke-Checked {
    param([string[]]$Arguments)
    & $VenvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

Invoke-Checked @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-Checked @('-m', 'pip', 'install', '-r', (Join-Path $ProjectRoot 'requirements.txt'))
Invoke-Checked @((Join-Path $ProjectRoot 'scripts\bootstrap_demo.py'))
Invoke-Checked @((Join-Path $ProjectRoot 'scripts\generate_reports.py'))
Invoke-Checked @((Join-Path $ProjectRoot 'scripts\generate_architecture.py'))
Invoke-Checked @('-m', 'pytest')
Invoke-Checked @((Join-Path $ProjectRoot 'evals\run_evals.py'))

if (-not $SkipClaudeCode) {
    $ClaudeCommand = Get-Command claude -ErrorAction SilentlyContinue
    $LocalClaude = Join-Path $ProjectRoot '.tools\claude\node_modules\@anthropic-ai\claude-code\bin\claude.exe'
    if (-not $ClaudeCommand -and -not (Test-Path -LiteralPath $LocalClaude)) {
        & (Join-Path $ProjectRoot 'install_claude_code.ps1')
        if ($LASTEXITCODE -ne 0) { throw "Claude Code installer failed (exit $LASTEXITCODE)." }
    }
    if ($ClaudeCommand -or (Test-Path -LiteralPath $LocalClaude)) {
        $DetectedClaude = if ($ClaudeCommand) { $ClaudeCommand.Source } else { $LocalClaude }
        Write-Host "Claude Code detected: $DetectedClaude"
        Write-Host 'Run .\claude-local.ps1 once interactively to authenticate, then .\claude-local.ps1 mcp list.'
    } else {
        Write-Warning 'Claude Code is not installed. The deterministic replay and all MCP tools are ready; install Claude Code separately for authenticated open-ended runs.'
    }
}

Write-Host 'Setup complete. Run .\run.ps1 and open http://localhost:8501.'
