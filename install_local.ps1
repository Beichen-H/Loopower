param(
    [string]$Skill = "prompt-to-loop-engineering",
    [string]$Target = "$HOME\.codex\skills",
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Verify,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "install_local.py"

if (-not (Test-Path -LiteralPath $installer)) {
    throw "Missing installer: $installer"
}

$argsList = @($installer, "--skill", $Skill, "--target", $Target)

if ($Force) {
    $argsList += "--force"
}

if ($DryRun) {
    $argsList += "--dry-run"
}

if ($Verify) {
    $argsList += "--verify"
}

& $Python @argsList
exit $LASTEXITCODE
