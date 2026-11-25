$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot.Replace('\', '/')
$prefs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'houdini22.0'
$packages = Join-Path $prefs 'packages'
New-Item -ItemType Directory -Force -Path $packages | Out-Null
$package = @{env = @(@{SPIRULA_ROOT = $packageRoot}); path = '$SPIRULA_ROOT'}
$package | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $packages 'spirula-studio.json')
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktopPath 'Spirula Pipeline.lnk'))
$shortcut.TargetPath = Join-Path $PSScriptRoot 'Ouvrir_Spirula_Pipeline.cmd'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Pipeline guidé : scan, objet, éclairage, génération et export'
$shortcut.IconLocation = 'C:\Program Files\Side Effects Software\Houdini 22.0.368\bin\houdinifx.exe,0'
$shortcut.Save()
Write-Output "Spirula Pipeline installé. Utilisez le raccourci du Bureau ou Tab > Spirula Pipeline dans une nouvelle session Houdini."
