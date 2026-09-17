# Install DCM agent @dp-dcm-lz-client (Windows PowerShell)
# cd dataint-dcm-app
# .\packages\dcm-agent\install.ps1
# .\packages\dcm-agent\install.ps1 -Global

param(
    [switch]$Global
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$AgentSrc = Join-Path $ScriptDir "agents\dp-dcm-lz-client.agent.md"

function Install-Copy {
    param([string]$Src, [string]$Dest)
    $parent = Split-Path -Parent $Dest
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    if (Test-Path $Src -PathType Container) {
        Copy-Item -Recurse -Force $Src $Dest
    } else {
        Copy-Item -Force $Src $Dest
    }
    Write-Host "  -> $Dest"
}

function Install-Skills {
    param([string]$SkillsRoot)
    if (-not (Test-Path $SkillsRoot)) { New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null }
    Get-ChildItem (Join-Path $ScriptDir "skills\dp-dcm-*") -Directory | ForEach-Object {
        Install-Copy -Src $_.FullName -Dest (Join-Path $SkillsRoot $_.Name)
    }
}

if ($Global) {
    Write-Host "Installing DCM agent globally..."
    $agentsDir = Join-Path $env:USERPROFILE ".github\agents"
    $skillsDir = Join-Path $env:USERPROFILE ".agents\skills"
    Install-Copy -Src $AgentSrc -Dest (Join-Path $agentsDir "dp-dcm-lz-client.agent.md")
    Install-Skills -SkillsRoot $skillsDir
} else {
    Write-Host "Installing DCM agent in $RepoRoot ..."
    Install-Copy -Src $AgentSrc -Dest (Join-Path $RepoRoot ".github\agents\dp-dcm-lz-client.agent.md")
    Install-Skills -SkillsRoot (Join-Path $RepoRoot ".agents\skills")
}

Write-Host ""
Write-Host "Done. Reload VS Code -> @dp-dcm-lz-client"
