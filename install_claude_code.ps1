param(
    [string]$NodeVersion = '24.19.0'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolsRoot = Join-Path $ProjectRoot '.tools'
if (-not $ToolsRoot.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unexpected tools target.'
}

$ArchiveName = "node-v$NodeVersion-win-x64.zip"
$CacheDirectory = Join-Path $ToolsRoot 'cache'
$NodeArchive = Join-Path $CacheDirectory $ArchiveName
$NodeDirectory = Join-Path $ToolsRoot "node-v$NodeVersion-win-x64"
$ClaudeDirectory = Join-Path $ToolsRoot 'claude'
New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null

if (-not (Test-Path -LiteralPath $NodeArchive)) {
    Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/$ArchiveName" -OutFile $NodeArchive
}
$ChecksumText = (Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/SHASUMS256.txt").Content
$ExpectedLine = $ChecksumText -split "`n" | Where-Object { $_ -match [regex]::Escape($ArchiveName) } | Select-Object -First 1
if (-not $ExpectedLine) { throw "Checksum entry not found for $ArchiveName" }
$ExpectedHash = ($ExpectedLine -split '\s+')[0].ToUpperInvariant()
$ActualHash = (Get-FileHash -LiteralPath $NodeArchive -Algorithm SHA256).Hash
if ($ActualHash -ne $ExpectedHash) { throw 'Node archive checksum mismatch.' }

if (-not (Test-Path -LiteralPath $NodeDirectory)) {
    Expand-Archive -LiteralPath $NodeArchive -DestinationPath $ToolsRoot
}
$NodeExecutable = Join-Path $NodeDirectory 'node.exe'
$NpmExecutable = Join-Path $NodeDirectory 'npm.cmd'
if (-not (Test-Path -LiteralPath $NodeExecutable)) { throw 'Portable Node extraction failed.' }

$env:PATH = "$NodeDirectory;$env:PATH"
& $NpmExecutable install --prefix $ClaudeDirectory '@anthropic-ai/claude-code@latest'
if ($LASTEXITCODE -ne 0) { throw "Claude Code installation failed (exit $LASTEXITCODE)." }

$ClaudeExecutable = Join-Path $ClaudeDirectory 'node_modules\@anthropic-ai\claude-code\bin\claude.exe'
if (-not (Test-Path -LiteralPath $ClaudeExecutable)) { throw 'Claude Code executable was not created.' }
& $ClaudeExecutable --version
if ($LASTEXITCODE -ne 0) { throw "Claude Code verification failed (exit $LASTEXITCODE)." }
Write-Host 'Portable Claude Code is installed. Run .\claude-local.ps1 once to complete interactive sign-in.'
