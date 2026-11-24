#Requires -Version 5.1
[CmdletBinding()]
param(
    [Alias('Release')][string]$ReleasePath = (Split-Path -Parent $PSScriptRoot),
    [string]$Java = 'java.exe',
    [string]$Python = 'python.exe',
    [ValidateRange(10, 900)][int]$StartupTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

function Get-RequiredSetting([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "Missing environment variable: $Name" }
    return $value
}

function Get-Executable([string]$Name) {
    if (Test-Path -LiteralPath $Name -PathType Leaf) {
        return (Get-Item -LiteralPath $Name).FullName
    }
    return (Get-Command -Name $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
}

function Start-HubChild([bool]$IsWorker, [string]$Arguments) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.Arguments = $Arguments
    if ($IsWorker) {
        $info.FileName = $pythonPath
        $info.WorkingDirectory = $workerRoot
        if (!$info.EnvironmentVariables['PGUSER']) { $info.EnvironmentVariables['PGUSER'] = $env:DB_USER }
        if (!$info.EnvironmentVariables['PGPASSWORD']) { $info.EnvironmentVariables['PGPASSWORD'] = $env:DB_PASSWORD }
        foreach ($key in 'DATABASE_URL','DB_URL','DB_USER','DB_PASSWORD','JWT_SECRET','CF_AUDIENCE','CF_TEAM_DOMAIN') {
            $info.EnvironmentVariables.Remove($key)
        }
    } else {
        $info.FileName = $javaPath
        $info.WorkingDirectory = $releaseRoot
        foreach ($key in 'X_BEARER_TOKEN','DATABASE_URL','PGPASSWORD','PGPASSFILE') {
            $info.EnvironmentVariables.Remove($key)
        }
    }
    $process = [Diagnostics.Process]::Start($info)
    # Drain both streams. Only supervisor lifecycle events are written to its console.
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()
    return $process
}

function Stop-HubChild($Child) {
    if ($null -eq $Child) { return }
    try {
        if (!$Child.HasExited) {
            # Windows venv launchers run the interpreter in a child process.
            # The native tree operation is also available to .NET Framework / PowerShell 5.1.
            $info = New-Object System.Diagnostics.ProcessStartInfo
            $info.FileName = Join-Path ([Environment]::SystemDirectory) 'taskkill.exe'
            $info.Arguments = '/PID ' + $Child.Id + ' /T /F'
            $info.UseShellExecute = $false
            $info.CreateNoWindow = $true
            $killer = [Diagnostics.Process]::Start($info)
            try {
                $killer.WaitForExit()
                if (!$Child.WaitForExit(5000)) { throw 'Could not stop the supervised process tree.' }
            } finally { $killer.Dispose() }
        }
    } finally { $Child.Dispose() }
}

function Test-ApiReady([int]$Port) {
    try {
        $response = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/internal/ready" -f $Port) -TimeoutSec 2 -ErrorAction Stop
        return $response.status -eq 'UP'
    } catch { return $false }
}

foreach ($key in 'DB_URL','DB_USER','DB_PASSWORD','PGHOST','PGPORT','PGDATABASE','MEDIA_ROOT','SPOOL_ROOT','JWT_SECRET','PUBLIC_ORIGIN') {
    [void](Get-RequiredSetting $key)
}
$releaseRoot = (Get-Item -LiteralPath $ReleasePath).FullName
$workerRoot = Join-Path $releaseRoot 'crawler-middleware'
if (!(Test-Path -LiteralPath (Join-Path $releaseRoot 'tcg-hub.jar') -PathType Leaf) -or
    !(Test-Path -LiteralPath (Join-Path $workerRoot 'tcg_worker/__main__.py') -PathType Leaf)) {
    throw 'ReleasePath must be an extracted release containing tcg-hub.jar and crawler-middleware.'
}
$javaPath = Get-Executable $Java
$pythonPath = Get-Executable $Python
$apiPort = 8080
if ($env:PORT) {
    if (![int]::TryParse($env:PORT, [ref]$apiPort) -or $apiPort -lt 1 -or $apiPort -gt 65535) {
        throw 'PORT must be between 1 and 65535.'
    }
}
foreach ($key in 'MEDIA_ROOT','SPOOL_ROOT') {
    if (![IO.Path]::IsPathRooted((Get-RequiredSetting $key))) { throw "$key must be an absolute path." }
}
$api = $null
$worker = $null
$probe = $null
try {
    $probe = Start-HubChild $true '-c "import psycopg, PIL, bs4, protego, tcg_worker"'
    if (!$probe.WaitForExit(20000) -or $probe.ExitCode -ne 0) {
        throw 'Python could not import the worker dependencies. Install the release requirements into the supplied interpreter.'
    }
    Stop-HubChild $probe
    $probe = $null
    while ($true) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $apiPort)
        try { $listener.Start() } catch { throw 'The API loopback port cannot be bound. Check PORT or stop the existing instance.' }
        finally { $listener.Stop() }
        $api = Start-HubChild $false '-Xms256m -Xmx1024m -XX:ActiveProcessorCount=2 -jar tcg-hub.jar'
        Write-Host ('Starting TCG API (PID {0})' -f $api.Id)
        $until = [datetime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
        while ($true) {
            if ($api.HasExited) { throw ('TCG API exited during startup, code {0}.' -f $api.ExitCode) }
            if (Test-ApiReady $apiPort) { break }
            if ([datetime]::UtcNow -ge $until) { throw 'Timed out waiting for API database readiness.' }
            Start-Sleep -Milliseconds 750
        }
        Write-Host 'TCG API and database ready.'
        $nextWorker = [datetime]::UtcNow
        while (!$api.HasExited) {
            if ($worker -and $worker.HasExited) {
                $code = $worker.ExitCode
                Stop-HubChild $worker
                $worker = $null
                $delay = if ($code -in 0,75) { 1 } else { 10 }
                $nextWorker = [datetime]::UtcNow.AddSeconds($delay)
                Write-Host ("TCG worker exited (code {0}); relaunch in {1}s." -f $code,$delay)
            }
            if (!$worker -and [datetime]::UtcNow -ge $nextWorker) {
                $worker = Start-HubChild $true '-m tcg_worker run'
                Write-Host ('Started TCG worker (PID {0})' -f $worker.Id)
            }
            Start-Sleep -Milliseconds 500
        }
        Write-Host ('TCG API exited (code {0}); restarting services.' -f $api.ExitCode)
        Stop-HubChild $worker
        $worker = $null
        Stop-HubChild $api
        $api = $null
        Start-Sleep -Seconds 5
    }
} finally {
    Stop-HubChild $probe
    Stop-HubChild $worker
    Stop-HubChild $api
}
