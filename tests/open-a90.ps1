# No ADB, device, port bindings or browser are used by these fixtures.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../deploy/open-a90.ps1')
$NoBrowser = $true
$Port = 18085
$AdbPort = 5037

function Get-Listeners([int]$Number) {
    if ($Number -eq 5037 -and $scenario -ne 'custom-server') { return [pscustomobject]@{LocalAddress='127.0.0.1';OwningProcess=11} }
    if ($Number -eq 7777 -and $scenario -eq 'custom-server') { return [pscustomobject]@{LocalAddress='127.0.0.1';OwningProcess=11} }
    if ($Number -eq $Port -and ($taken -or $state.routes)) {
        $address = if ($scenario -eq 'wildcard') { '0.0.0.0' } else { '127.0.0.1' }
        $owner = if ($taken) { 99 } else { 11 }
        return [pscustomobject]@{LocalAddress=$address;OwningProcess=$owner}
    }
}
function Get-Process([int]$Id) { [pscustomobject]@{ProcessName='adb';Path='C:\active-sdk\adb.exe'} }
function Get-CimInstance($ClassName,$Filter) {
    if ($ClassName -eq 'Win32_PnPEntity') {
        if ($scenario -eq 'two-physical') {
            foreach ($id in 'SERIAL1','SERIAL2') { [pscustomobject]@{PNPDeviceID="USB\VID_04E8&PID_6860\$id"} }
        }
    } elseif ($scenario -eq 'custom-server') { [pscustomobject]@{ProcessId=11;CommandLine='adb.exe -L tcp:7777 fork-server server'} }
    else { [pscustomobject]@{ProcessId=11;CommandLine='adb.exe -L tcp:5037 fork-server server'} }
}
function Invoke-Adb([string[]]$Command,[switch]$Optional) {
    if ($exe -ne 'C:\active-sdk\adb.exe') { throw 'Unexpected ADB binary' }
    $verb = $Command -join ' '
    if ($verb -eq 'devices -l') {
        if ($scenario -eq 'offline') { return 'SERIAL1 unauthorized' }
        if ($scenario -eq 'network') { return '10.0.0.5:5555 device model:SM_A908N transport_id:3' }
        'SERIAL1 device product:r3qks model:SM_A908N device:r3q transport_id:1'
        if ($scenario -eq 'two-physical') { 'SERIAL2 device model:SM_A908B transport_id:2' }
    } elseif ($verb -eq '-d get-serialno') {
        if ($scenario -ne 'two-physical') { 'SERIAL1' }
    } elseif ($verb -match ' get-devpath$') { 'unknown' }
    elseif ($verb -match ' shell getprop ro.product.model$') { 'SM-A908N' }
    elseif ($verb -match ' forward --list$') { $state.routes }
    elseif ($verb -match '^-s (SERIAL[12]) forward --no-rebind tcp:18085 tcp:8080$') {
        $state.adds++
        if ($scenario -eq 'raced') { throw 'Simulated --no-rebind refusal' }
        $state.routes = "$($Matches[1]) tcp:18085 tcp:8080"
    } elseif ($verb -match ' forward --remove tcp:18085$') { $state.removes++; $state.routes='' }
    else { throw "Unexpected mock command $verb" }
}
function Test-A90Page([string]$Base) {
    $state.http++
    if ($scenario -eq 'down') { throw 'Catalog down' }
}
function Start-Process([string]$FilePath) {
    if ($scenario -ne 'browser' -or $FilePath -ne 'http://127.0.0.1:18085/') { throw 'Unexpected browser launch' }
    $state.browser++
}

function Test-Case($scenario,$route,$taken,$Serial,$failure,$add,$remove,$http) {
    $NoBrowser = $scenario -ne 'browser'
    $state = @{routes=$route;adds=0;removes=0;http=0;browser=0}
    $failed = $false
    try {
        $url = Open-A90
    } catch {
        if (!$failure -or $_.Exception.Message -notlike "*$failure*") { throw }
        $failed = $true
    }
    if ($failed -ne [bool]$failure -or $state.adds -ne $add -or $state.removes -ne $remove -or $state.http -ne $http) {
        throw "Incorrect connect/cleanup result for $scenario"
    }
    if (!$failure -and $url -ne 'http://127.0.0.1:18085/') { throw 'Incorrect browser URL' }
    if ($state.browser -ne [int](!$NoBrowser)) { throw 'Incorrect browser handoff' }
    Write-Output "Pass $scenario"
}
Test-Case offline '' $false '' 'No authorized' 0 0 0
Test-Case network '' $false '' 'No authorized' 0 0 0
Test-Case two-physical '' $false '' 'Choose the A90' 0 0 0
Test-Case two-physical '' $false 'SERIAL2' '' 1 0 1
Test-Case occupied '' $true '' 'already in use' 0 0 0
Test-Case other-device 'SERIAL2 tcp:18085 tcp:8080' $false '' 'forwards elsewhere' 0 0 0
Test-Case other-target 'SERIAL1 tcp:18085 tcp:9000' $false '' 'forwards elsewhere' 0 0 0
Test-Case reused 'SERIAL1 tcp:18085 tcp:8080' $false '' '' 0 0 1
Test-Case browser 'SERIAL1 tcp:18085 tcp:8080' $false '' '' 0 0 1
Test-Case created '' $false '' '' 1 0 1
Test-Case raced '' $false '' 'no-rebind refusal' 1 0 0
Test-Case wildcard '' $false '' 'not bound exclusively' 1 1 0
Test-Case wildcard 'SERIAL1 tcp:18085 tcp:8080' $false '' 'not bound exclusively' 0 0 0
Test-Case down '' $false '' 'Catalog down' 1 1 1
Test-Case down 'SERIAL1 tcp:18085 tcp:8080' $false '' 'Catalog down' 0 0 1

function Test-CustomPort {
    $scenario = 'custom-server'
    $AdbPort = $null
    $previousSocket = $env:ADB_SERVER_SOCKET
    $previousPort = $env:ANDROID_ADB_SERVER_PORT
    try {
        $env:ANDROID_ADB_SERVER_PORT = $null
        $env:ADB_SERVER_SOCKET = $null
        if ((Get-AdbServerPort) -ne 7777) { throw 'Failed to discover running non-default ADB port' }
        $env:ADB_SERVER_SOCKET = 'tcp:localhost:8888'
        if ((Get-AdbServerPort) -ne 8888) { throw 'Failed to use configured loopback ADB port' }
    } finally {
        $env:ADB_SERVER_SOCKET = $previousSocket
        $env:ANDROID_ADB_SERVER_PORT = $previousPort
    }
    Write-Output 'Pass custom ADB port discovery and configuration'
}
Test-CustomPort
