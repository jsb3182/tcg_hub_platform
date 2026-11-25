param(
    [string]$Sdk = $env:ANDROID_SDK_ROOT,
    [string]$Jdk = $env:JAVA_HOME,
    [string]$SigningDirectory = (Join-Path $env:LOCALAPPDATA 'TCG-Hub\signing'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\dist')
)
$ErrorActionPreference = 'Stop'
if (-not $Sdk -or -not $Jdk) { throw 'Set ANDROID_SDK_ROOT and JAVA_HOME (JDK 17).' }
$tools = Join-Path $Sdk 'build-tools\35.0.0'
$platform = Join-Path $Sdk 'platforms\android-35\android.jar'
$compiler = Join-Path $Jdk 'bin\javac.exe'
$jar = Join-Path $Jdk 'bin\jar.exe'
$keytool = Join-Path $Jdk 'bin\keytool.exe'
$env:JAVA_HOME = $Jdk
function Run([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Tool failed ($LASTEXITCODE): $Command" }
}
if (-not (Test-Path -LiteralPath $platform)) { throw 'Install platforms;android-35 first.' }
$out = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$private = [IO.Path]::GetFullPath($SigningDirectory)
if ($private -eq $repo -or $private.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a signing directory outside the source repository.'
}
if ($private.TrimEnd('\') -eq [IO.Path]::GetPathRoot($private).TrimEnd('\') -or
    ((Test-Path -LiteralPath $private) -and
        @(Get-ChildItem -Force -LiteralPath $private | Where-Object { $_.Name -notin @('tcg-control.p12','password.dpapi') }).Count)) {
    throw 'Choose a dedicated, empty signing directory or the directory containing this signing key.'
}
[void][IO.Directory]::CreateDirectory($private)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $private -AclObject $acl
$store = Join-Path $private 'tcg-control.p12'
$vault = Join-Path $private 'password.dpapi'
if ((Test-Path $store) -and -not (Test-Path $vault)) { throw 'Existing signing key needs its original protected password.' }
if (-not (Test-Path $vault)) {
    $bytes = New-Object byte[] 36
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $secret = ConvertTo-SecureString ([Convert]::ToBase64String($bytes)) -AsPlainText -Force
    $secret | ConvertFrom-SecureString | Set-Content -NoNewline -LiteralPath $vault
}
$secret = Get-Content -Raw -LiteralPath $vault | ConvertTo-SecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
# The temporary environment entry goes only to local signing tools. It is removed before compilation.
try {
    $env:TCG_SIGN_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    if (-not (Test-Path $store)) {
        Run $keytool @('-genkeypair','-storetype','PKCS12','-alias','tcg-control','-keyalg','RSA','-keysize','3072',
            '-validity','10000','-dname','CN=TCG Hub Android Control','-keystore',$store,'-storepass:env','TCG_SIGN_SECRET')
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:TCG_SIGN_SECRET -ErrorAction SilentlyContinue
}
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$work = [IO.Directory]::CreateDirectory((Join-Path $tempRoot ('tcg-android-' + [guid]::NewGuid().ToString('N')))).FullName
try {
    $classes = [IO.Directory]::CreateDirectory((Join-Path $work 'classes')).FullName
    $dex = [IO.Directory]::CreateDirectory((Join-Path $work 'dex')).FullName
    $manifest = Join-Path $PSScriptRoot 'AndroidManifest.xml'
    $resources = Join-Path $work 'resources.zip'
    $unsigned = Join-Path $work 'unsigned.apk'
    $aligned = Join-Path $work 'aligned.apk'
    $signed = Join-Path $work 'tcg-server-control.apk'
    Run "$tools\aapt2.exe" @('compile','--dir',(Join-Path $PSScriptRoot 'res'),'-o',$resources)
    Run "$tools\aapt2.exe" @('link','-I',$platform,'--manifest',$manifest,'-o',$unsigned,$resources)
    $source = (Get-ChildItem -Recurse -File -Filter '*.java' (Join-Path $PSScriptRoot 'src')).FullName
    Run $compiler (@('-encoding','UTF-8','--release','8','-classpath',$platform,'-d',$classes) + @($source))
    $bytecode = Join-Path $work 'classes.jar'
    Run $jar @('cf',$bytecode,'-C',$classes,'.')
    Run "$tools\d8.bat" @('--lib',$platform,'--min-api','28','--output',$dex,$bytecode)
    Run $jar @('uf',$unsigned,'-C',$dex,'classes.dex')
    Run "$tools\zipalign.exe" @('-f','4',$unsigned,$aligned)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $env:TCG_SIGN_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        Run "$tools\apksigner.bat" @('sign','--ks',$store,'--ks-key-alias','tcg-control','--ks-pass','env:TCG_SIGN_SECRET','--out',$signed,$aligned)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        Remove-Item Env:TCG_SIGN_SECRET -ErrorAction SilentlyContinue
    }
    Run "$tools\apksigner.bat" @('verify','--verbose','--print-certs',$signed)
    $apk = Join-Path $out 'tcg-server-control.apk'
    Copy-Item -LiteralPath $signed -Destination $apk -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $apk).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$apk.sha256", "$hash  tcg-server-control.apk`n", [Text.Encoding]::ASCII)
    Write-Output "$apk SHA-256 $hash"
} finally {
    if ([IO.Path]::GetDirectoryName($work).TrimEnd('\') -eq $tempRoot.TrimEnd('\') -and
            [IO.Path]::GetFileName($work) -match '^tcg-android-[a-f0-9]{32}$') {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
