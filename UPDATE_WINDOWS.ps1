param(
    [string]$ProjectPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads\FinPredict_AI_gpt')
)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $ProjectPath 'backend\app.py'))) {
    throw 'Project folder not found. Pass -ProjectPath with the existing project folder.'
}
$target = (Resolve-Path -LiteralPath $ProjectPath).Path.TrimEnd('\')
if ($source -eq $target) { throw 'Run this script from the separately extracted NEW project folder.' }
$backup = $target + '_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
New-Item -ItemType Directory -Path $backup | Out-Null
$changed = [Collections.Generic.List[string]]::new()
$newFiles = [Collections.Generic.List[string]]::new()
$files = @(Get-ChildItem -LiteralPath $source -File -Recurse -Force)
try {
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($source.Length + 1)
        if ($relative -match '(^|[\\/])(\.venv|node_modules|\.git|__pycache__|\.openai)[\\/]') { continue }
        if ($relative -match '(^|[\\/])\.env$|(^|[\\/])\.session-secret$') { continue }
        $destination = Join-Path $target $relative
        # Keep the user's connection settings, including a custom database name.
        if ($relative -eq 'backend\config.py' -and (Test-Path -LiteralPath $destination)) { continue }
        if (Test-Path -LiteralPath $destination) {
            $saved = Join-Path $backup $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $saved) | Out-Null
            Copy-Item -LiteralPath $destination -Destination $saved -Force
            $changed.Add($relative)
        } else { $newFiles.Add($relative) }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
} catch {
    foreach ($relative in $changed) {
        Copy-Item -LiteralPath (Join-Path $backup $relative) -Destination (Join-Path $target $relative) -Force
    }
    foreach ($relative in $newFiles) {
        $created = Join-Path $target $relative
        if (Test-Path -LiteralPath $created -PathType Leaf) { Remove-Item -LiteralPath $created -Force }
    }
    throw
}
Write-Host 'Project updated. Database settings, .env and session secret preserved.' -ForegroundColor Green
Write-Host ('Backup: ' + $backup)
Write-Host 'Now open the OLD project folder, install requirements and start backend/app.py.'
Write-Host 'Refresh the website with Ctrl+F5. No client re-import or password reset is required.'
