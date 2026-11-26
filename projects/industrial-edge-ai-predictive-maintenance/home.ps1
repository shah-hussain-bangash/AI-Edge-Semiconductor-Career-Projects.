# Native Windows entry point. No Git clone, firmware upload or equipment control.
[CmdletBinding()]
param(
    [ValidateSet('Setup','Check','Ports','Start','Demo','Update','Status','Stop')]
    [string]$Action = 'Start',
    [ValidateSet('esp32-only','sensors')]
    [string]$Mode = 'esp32-only',
    [string]$SerialPort = '',
    [string]$DeviceId = 'motor-001',
    [ValidateRange(1024,65535)]
    [int]$WebPort = 8878,
    [string]$PythonPath = 'python'
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'Use bash home_setup.command / home_start.command in macOS Terminal.'
}
Push-Location $PSScriptRoot
try {
    $homePython = Join-Path $PSScriptRoot '.venv-home/Scripts/python.exe'
    if ($Action -eq 'Setup') {
        $bootstrap = Get-Command $PythonPath -ErrorAction SilentlyContinue
        if (-not $bootstrap -or $bootstrap.Source -like '*\Microsoft\WindowsApps\*') {
            throw 'Choose an installed Python 3.12-3.14 executable with -PythonPath, or run: pymanager exec -V:3.13 home-mode/manage.py setup'
        }
        & $bootstrap.Source home-mode/manage.py setup
        if ($LASTEXITCODE -ne 0) { throw 'Setup stopped. Review the message above; existing files were preserved.' }
        return
    }
    if (-not (Test-Path -LiteralPath $homePython)) {
        throw 'Run .\home.ps1 -Action Setup first. You can also use: pymanager exec -V:3.13 home-mode/manage.py setup'
    }
    & $homePython home-mode/manage.py verify
    if ($LASTEXITCODE -ne 0) { throw 'Environment verification failed. Stop home mode, then run Setup.' }
    if ($Action -eq 'Status' -or $Action -eq 'Stop') {
        $controlAction = if ($Action -eq 'Status') { 'status' } else { 'stop-demo' }
        & $homePython home-mode/manage.py $controlAction --web-port $WebPort
        if ($LASTEXITCODE -ne 0) { throw 'Local control stopped without force-killing anything. Review the message above.' }
        return
    }
    if ($Action -eq 'Update') {
        & $homePython home-mode/manage.py update
        if ($LASTEXITCODE -ne 0) { throw 'Update stopped without discarding local work.' }
        & $homePython home-mode/manage.py setup
        if ($LASTEXITCODE -ne 0) { throw 'Source updated, but dependency setup needs attention before launch.' }
        return
    }
    if ($Action -eq 'Check' -or $Action -eq 'Ports') {
        & $homePython home-mode/manage.py check
        if ($LASTEXITCODE -ne 0) { throw 'Python requirements are not met.' }
        & $homePython home-mode/manage.py ports
        if ($LASTEXITCODE -ne 0) { throw 'Serial enumeration failed.' }
        Write-Host 'A Windows PC cannot detect USB hardware connected to the home Mac.'
        return
    }
    $dashboardUrl = "http://127.0.0.1:$WebPort/app"
    $existing = $null
    try { $existing = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/api/status" -TimeoutSec 2 } catch { }
    if ($existing -and $existing.scope -eq 'edgeops-lightweight-home') {
        Write-Host "An EDGEOPS home server is already responding: $dashboardUrl"
        Write-Host 'Use .\home.ps1 -Action Status to inspect it. Use -Action Stop for this checkout''s updated demo, or Ctrl+C in its original Terminal.'
        Write-Host 'No reader settings or existing processes were changed.'
        return
    }
    $launchArgs = @('home-mode/home_server.py','--web-port',"$WebPort")
    if ($Action -eq 'Demo') {
        $launchArgs += @('--mode','demo','--connect')
    } else {
        $launchArgs += @('--mode',$Mode,'--device-id',$DeviceId)
        if ($SerialPort) {
            if ($SerialPort -notmatch '^COM[1-9][0-9]{0,2}$') { throw 'Use the confirmed Windows COM port. /dev/cu.* belongs to the Mac.' }
            $launchArgs += @('--port',$SerialPort,'--connect')
        }
    }
    Write-Host "Keep this Terminal open. Open $dashboardUrl in your browser. Ctrl+C stops this session."
    & $homePython @launchArgs
    if ($LASTEXITCODE -ne 0) { throw 'Home mode stopped. Review the message above; no existing process was killed.' }
} finally {
    Pop-Location
}
