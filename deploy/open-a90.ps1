#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9-]+$')][string]$Serial,
    [ValidateRange(1,65535)][int]$Port = 18085,
    [ValidateRange(1,65535)][int]$AdbPort,
    [string]$AdbPath,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

function Get-Listeners([int]$Number) {
    Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $Number
}

function Get-AdbServerPort {
    if ($AdbPort) { return $AdbPort }
    if ($env:ADB_SERVER_SOCKET) {
        if ($env:ADB_SERVER_SOCKET -notmatch '^tcp:(?:(?:localhost|127\.0\.0\.1|\[::1\]):)?(\d{1,5})$') {
            throw 'Use a local ADB server. Supply its port with -AdbPort.'
        }
        return [int]$Matches[1]
    }
    if ($env:ANDROID_ADB_SERVER_PORT) { return [int]$env:ANDROID_ADB_SERVER_PORT }
    if (Get-Listeners 5037) { return 5037 }
    $ports = @(Get-CimInstance Win32_Process -Filter "Name='adb.exe'" | ForEach-Object {
        if ($_.CommandLine -match '\bserver\b' -and
            $_.CommandLine -match '(?:^|\s)-L\s+"?tcp:(?:(?:localhost|127\.0\.0\.1|\[::1\]):)?(\d+)\b') {
            $number = [int]$Matches[1]
            if ((Get-Listeners $number).OwningProcess -contains $_.ProcessId) { $number }
        }
    } | Sort-Object -Unique)
    if ($ports.Count -gt 1) { throw 'Multiple ADB servers found. Supply -AdbPort.' }
    if ($ports.Count -eq 1) { return $ports[0] }
    return 5037
}

function Get-AdbExecutable {
    $rows = @(Get-Listeners $AdbPort)
    if ($rows) {
        $owners = @($rows.OwningProcess | Sort-Object -Unique)
        if ($owners.Count -ne 1 -or @($rows | Where-Object LocalAddress -notin '127.0.0.1','::1').Count) {
            throw 'The ADB control port must belong to one loopback ADB server.'
        }
        $owner = Get-Process -Id $owners[0]
        if ($owner.ProcessName -ne 'adb' -or !$owner.Path) { throw 'Another program owns the ADB port. Supply -AdbPort.' }
        return $owner.Path
    }
    if ($AdbPath) { return (Get-Item -LiteralPath $AdbPath).FullName }
    $command = Get-Command adb.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    foreach ($sdk in @($env:ANDROID_HOME,$env:ANDROID_SDK_ROOT,"$env:LOCALAPPDATA\Android\Sdk")) {
        if ($sdk -and (Test-Path -LiteralPath "$sdk\platform-tools\adb.exe" -PathType Leaf)) { return "$sdk\platform-tools\adb.exe" }
    }
    throw 'Install Android SDK Platform-Tools or supply -AdbPath.'
}

function Invoke-Adb([string[]]$Command, [switch]$Optional) {
    $ErrorActionPreference = 'Continue'
    $lines = & $exe -H localhost -P $AdbPort @Command 2>&1
    if ($LASTEXITCODE -eq 0) { $lines | ForEach-Object { "$_" }; return }
    if (!$Optional) { throw 'ADB command failed. Check the USB cable, debugging authorization and selected ports.' }
}

function Select-UsbA90 {
    $candidates = @(foreach ($line in (Invoke-Adb @('devices','-l'))) {
        if ($line -match '^([A-Za-z0-9-]+)\s+device\s+.*\bmodel:SM[_-]A908[A-Z0-9]{1,3}\b') {
            $id = $Matches[1]
            if ((!$Serial -or $id -ceq $Serial) -and $id -notlike 'emulator-*') { $id }
        }
    })
    $usb = @(if ($candidates) {
        $onlyUsb = Invoke-Adb @('-d','get-serialno') -Optional
        $parents = $null
        foreach ($id in $candidates) {
            if (($onlyUsb -ceq $id) -or ((Invoke-Adb @('-s',$id,'get-devpath') -Optional) -like 'usb:*')) { $id; continue }
            # On Windows get-devpath can report "unknown". Match the physical Samsung USB parent.
            if ($null -eq $parents) {
                $parents = @(Get-CimInstance Win32_PnPEntity -Filter "PNPDeviceID LIKE 'USB\\VID_04E8%' AND Present=TRUE")
            }
            if ($parents | Where-Object { $_.PNPDeviceID.EndsWith("\$id",[StringComparison]::OrdinalIgnoreCase) }) { $id }
        }
    })
    if (!$usb.Count) { throw 'No authorized Galaxy A90 on USB. Connect a data cable, unlock the phone and allow USB debugging for this PC.' }
    if ($usb.Count -gt 1) { throw "Choose the A90 with -Serial. Connected USB A90s: $($usb -join ', ')." }
    if ((Invoke-Adb @('-s',$usb[0],'shell','getprop','ro.product.model')) -notmatch '^SM-A908[A-Z0-9]{1,3}$') {
        throw 'The selected device did not confirm a Galaxy A90 model.'
    }
    return $usb[0]
}

function Get-Mapping {
    Invoke-Adb @('-s',$Serial,'forward','--list') | Where-Object { $_ -match "^\S+\s+tcp:$Port\s+" }
}

function Test-A90Page([string]$Base) {
    # Direct loopback HTTP, with redirects and system proxies disabled.
    try {
        foreach ($path in @('/internal/ready','/')) {
            $request = [Net.HttpWebRequest]::Create($Base + $path)
            $request.Proxy = $null
            $request.AllowAutoRedirect = $false
            $request.Timeout = 5000
            $request.ReadWriteTimeout = 5000
            $response = $request.GetResponse()
            try {
                if ([int]$response.StatusCode -ne 200) { throw 'Unexpected HTTP status' }
                $reader = New-Object IO.StreamReader($response.GetResponseStream())
                try { $body = $reader.ReadToEnd() } finally { $reader.Dispose() }
                if ($path -eq '/internal/ready' -and ($body | ConvertFrom-Json).status -ne 'UP') { throw 'Server not ready' }
                if ($path -eq '/' -and ($body -notmatch 'id="app"' -or $body -notmatch '/assets/index-[^"]+\.js')) { throw 'Catalog page missing' }
            } finally { $response.Close() }
        }
    } catch { throw 'The A90 catalog is not ready. Open TCG Hub on the phone, start its server, then run this command again.' }
}

function Open-A90 {
    $AdbPort = Get-AdbServerPort
    if ($AdbPort -lt 1 -or $AdbPort -gt 65535 -or $AdbPort -eq $Port) { throw 'Specify distinct valid ports for ADB and the catalog.' }
    $exe = Get-AdbExecutable
    $Serial = Select-UsbA90
    $match = '^' + [regex]::Escape($Serial) + "\s+tcp:$Port\s+tcp:8080$"
    $routes = @(Get-Mapping)
    if ($routes.Count -gt 1 -or ($routes.Count -eq 1 -and $routes[0] -cnotmatch $match)) {
        throw "PC port $Port already forwards elsewhere. Choose another with -Port."
    }
    $added = $false
    try {
        if (!$routes.Count) {
            if (Get-Listeners $Port) { throw "PC port $Port is already in use. Choose another with -Port." }
            $pidOfServer = (Get-Listeners $AdbPort | Select-Object -First 1).OwningProcess
            $daemon = Get-CimInstance Win32_Process -Filter "ProcessId=$pidOfServer"
            if (!$daemon.CommandLine -or $daemon.CommandLine -match '(?:^|\s)-a(?:\s|$)') {
                throw 'Use a local-only ADB server to create this forward.'
            }
            Invoke-Adb @('-s',$Serial,'forward','--no-rebind',"tcp:$Port",'tcp:8080') | Out-Null
            $added = $true
        }
        $rows = @(Get-Listeners $Port)
        $adbOwner = @(Get-Listeners $AdbPort | Select-Object -ExpandProperty OwningProcess -Unique)
        $routes = @(Get-Mapping)
        if ($routes.Count -ne 1 -or $routes[0] -cnotmatch $match -or $adbOwner.Count -ne 1 -or !$rows.Count -or
            @($rows | Where-Object { $_.LocalAddress -notin '127.0.0.1','::1' -or $_.OwningProcess -ne $adbOwner[0] }).Count) {
            throw 'The forward is not bound exclusively to the selected loopback ADB server.'
        }
        $base = if ($rows.LocalAddress -contains '127.0.0.1') { "http://127.0.0.1:$Port" } else { "http://[::1]:$Port" }
        Test-A90Page $base
    } catch {
        if ($added -and (@(Get-Mapping) -cmatch $match)) {
            Invoke-Adb @('-s',$Serial,'forward','--remove',"tcp:$Port") | Out-Null
        }
        throw
    }
    Write-Output "$base/"
    if (!$NoBrowser) { Start-Process "$base/" }
}

if ($MyInvocation.InvocationName -ne '.') { Open-A90 }
