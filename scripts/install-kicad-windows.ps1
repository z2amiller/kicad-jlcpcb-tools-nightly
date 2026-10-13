# Install KiCad <Version> with its own silent installer, where users have it,
# and hand its Python and bin directory to later workflow steps.
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)
$ErrorActionPreference = 'Stop'

$installer = Join-Path $env:RUNNER_TEMP "kicad-$Version-x86_64.exe"
$url = "https://github.com/KiCad/kicad-source-mirror/releases/download/$Version/kicad-$Version-x86_64.exe"
curl.exe --fail --silent --show-error --location --retry 3 --output $installer $url
if ($LASTEXITCODE -ne 0) { throw "Downloading $url failed" }

# KiCad's NSIS installer uses NsisMultiUser: /S needs /allusers or /currentuser
# beside it, or it exits 666660. It ignores /D and installs to
# Program Files\KiCad\<major.minor>.
$process = Start-Process -FilePath $installer -ArgumentList '/S', '/allusers' -Wait -PassThru
if ($process.ExitCode -ne 0) {
    $meanings = @{
        666660 = 'invalid command-line parameters'
        666661 = 'elevation is not allowed'
        666666 = 'elevation failed'
    }
    throw "The KiCad $Version installer exited $($process.ExitCode) $($meanings[$process.ExitCode])"
}

$majorMinor = ($Version -split '\.')[0..1] -join '.'
$bin = Join-Path $env:ProgramFiles "KiCad\$majorMinor\bin"
$python = Join-Path $bin 'python.exe'
if (-not (Test-Path $python)) { throw "No KiCad Python at $python" }

# Forward slashes keep the path usable from bash steps; it contains spaces,
# so those steps always quote it.
"KICAD_PYTHON=$($python -replace '\\', '/')" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
$bin | Out-File -FilePath $env:GITHUB_PATH -Append -Encoding utf8
"KiCad $Version installed in $bin"
