param(
  [Parameter(Mandatory = $true)] [string] $InstallDirectory,
  [Parameter(Mandatory = $true)] [string] $Version
)

$ErrorActionPreference = "Stop"
$appName = "PU2PTU - Radio Link Planner"
$expectedTarget = Join-Path $InstallDirectory "RadioLinkPlanner.exe"
$expectedIcon = Join-Path $InstallDirectory "RadioLinkPlanner-$Version.ico"
$sourceIcon = Join-Path $PSScriptRoot "..\assets\app-icon.ico"
$versionInfo = (Get-Item -LiteralPath $expectedTarget).VersionInfo
if ($versionInfo.ProductName -ne $appName -or $versionInfo.FileDescription -ne $appName -or
    $versionInfo.ProductVersion -ne $Version) {
  throw "The installed executable has unexpected Windows product metadata."
}
if (-not (Test-Path -LiteralPath $expectedIcon)) {
  throw "Installed shortcut icon is missing: $expectedIcon"
}
if ((Get-FileHash $sourceIcon -Algorithm SHA256).Hash -ne
    (Get-FileHash $expectedIcon -Algorithm SHA256).Hash) {
  throw "The installed shortcut icon differs from the approved asset."
}

# Exercise the Windows icon decoder, not just the existence of a .ico file.
Add-Type -AssemblyName System.Drawing
$icon = [System.Drawing.Icon]::new($expectedIcon)
try {
  $bitmap = $icon.ToBitmap()
  try {
    if ($bitmap.Width -le 0 -or $bitmap.Height -le 0) {
      throw "Windows could not decode the installed icon."
    }
  } finally {
    $bitmap.Dispose()
  }
} finally {
  $icon.Dispose()
}

$shortcutFolders = @(
  [Environment]::GetFolderPath("CommonPrograms"),
  [Environment]::GetFolderPath("CommonDesktopDirectory")
)
$shell = New-Object -ComObject WScript.Shell
try {
  $results = foreach ($folder in $shortcutFolders) {
    $legacyLocation = Join-Path $folder "Radio Link Planner.lnk"
    if (Test-Path -LiteralPath $legacyLocation) {
      throw "The upgrade left a shortcut with the previous name: $legacyLocation"
    }
    $location = Join-Path $folder "$appName.lnk"
    if (-not (Test-Path -LiteralPath $location)) {
      throw "Installer did not create shortcut: $location"
    }
    $shortcut = $shell.CreateShortcut($location)
    try {
      if ($shortcut.TargetPath -ne $expectedTarget) {
        throw "Unexpected shortcut target: $($shortcut.TargetPath)"
      }
      $parts = $shortcut.IconLocation -split ",", 2
      if ($parts.Count -ne 2 -or $parts[0] -ne $expectedIcon -or [int]$parts[1] -ne 0) {
        throw "Shortcut does not explicitly use the approved icon: $($shortcut.IconLocation)"
      }
      [pscustomobject]@{
        Shortcut = $location
        Target = $shortcut.TargetPath
        IconLocation = $shortcut.IconLocation
        IconVerified = $true
      }
    } finally {
      [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)
    }
  }
  $results | ConvertTo-Json -Depth 3
} finally {
  [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
}
