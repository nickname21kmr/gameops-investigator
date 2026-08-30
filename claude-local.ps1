$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeExecutable = Join-Path $ProjectRoot '.tools\claude\node_modules\@anthropic-ai\claude-code\bin\claude.exe'
if (-not (Test-Path -LiteralPath $ClaudeExecutable)) {
    throw 'Local Claude Code is missing. Reinstall it under .tools\claude.'
}
Set-Location -LiteralPath $ProjectRoot
& $ClaudeExecutable @args
exit $LASTEXITCODE
