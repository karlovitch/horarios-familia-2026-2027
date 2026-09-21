param(
    [string]$Repo = "karlovitch/horarios-familia-2026-2027"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Emparelhar Agenda pessoal - Horarios Familia"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host ("[+] " + $Text) -ForegroundColor Green
}

function Get-PlainFromSecure([System.Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-AgendaKey {
    $dir = Join-Path $env:LOCALAPPDATA "HorariosFamilia"
    $dpapi = Join-Path $dir "agenda-key.dpapi"
    $key = $null

    if (Test-Path $dpapi) {
        try {
            $secure = Get-Content $dpapi -Raw | ConvertTo-SecureString
            $plain = Get-PlainFromSecure $secure
            if ($plain -and $plain.Length -ge 20) {
                Write-Host "Codigo da agenda recuperado da copia protegida do Windows." -ForegroundColor Cyan
                return $plain.Trim()
            }
        } catch {}
    }

    try {
        $clip = (Get-Clipboard -Raw -ErrorAction SilentlyContinue).Trim()
        if ($clip -match '^[A-Za-z0-9._~-]{20,128}$') {
            $use = Read-Host "Encontrei um possivel codigo da agenda na area de transferencia. Usar? (S/n)"
            if ($use -notmatch '^[Nn]') { $key = $clip }
        }
    } catch {}

    if (-not $key) {
        $secure = Read-Host "Cola/introduz o CODIGO DA AGENDA PESSOAL (so desta vez)" -AsSecureString
        $key = Get-PlainFromSecure $secure
    }

    if ([string]::IsNullOrWhiteSpace($key) -or $key.Trim().Length -lt 20) {
        throw "O codigo parece invalido ou demasiado curto."
    }

    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    try {
        ConvertTo-SecureString $key.Trim() -AsPlainText -Force |
            ConvertFrom-SecureString |
            Set-Content -Encoding UTF8 $dpapi
    } catch {}

    return $key.Trim()
}

function Get-Adb {
    $found = Get-Command adb -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:LOCALAPPDATA\HorariosFamilia\platform-tools\adb.exe"
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }

    $base = Join-Path $env:LOCALAPPDATA "HorariosFamilia"
    $zip = Join-Path $base "platform-tools.zip"
    $adbDir = Join-Path $base "platform-tools"
    New-Item -ItemType Directory -Force -Path $base | Out-Null

    Write-Step "ADB nao encontrado. A descarregar Android Platform Tools oficiais..."
    Invoke-WebRequest -UseBasicParsing "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
    if (Test-Path $adbDir) { Remove-Item -Recurse -Force $adbDir }
    Expand-Archive -Force $zip $base
    Remove-Item -Force $zip
    $adb = Join-Path $adbDir "adb.exe"
    if (-not (Test-Path $adb)) { throw "Nao foi possivel preparar o ADB." }
    return $adb
}

function Get-ConnectedDevices([string]$Adb) {
    $lines = & $Adb devices
    return @($lines | Select-Object -Skip 1 | ForEach-Object {
        if ($_ -match '^([^\s]+)\s+device$') { $Matches[1] }
    } | Where-Object { $_ })
}

$key = Get-AgendaKey
$escaped = [Uri]::EscapeDataString($key)
$pairUrl = "https://karlovitch.github.io/horarios-familia-2026-2027/#agendaKey=$escaped"

Write-Step "A emparelhar browser/PWA do Windows..."
Start-Process $pairUrl

$localDir = Join-Path $env:LOCALAPPDATA "HorariosFamilia"
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

Write-Step "A obter a versao Windows mais recente e a emparelhar..."
$exe = Join-Path $localDir "HorariosFamilia-Windows.exe"
$exeUrl = "https://github.com/$Repo/releases/download/windows-v1/HorariosFamilia-Windows.exe"
try {
    Invoke-WebRequest -UseBasicParsing $exeUrl -OutFile $exe
    Start-Process -FilePath $exe -ArgumentList @("--agenda-key=$key")

    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shortcutPath = Join-Path $desktop "Horarios Familia.lnk"
        $ws = New-Object -ComObject WScript.Shell
        $sc = $ws.CreateShortcut($shortcutPath)
        $sc.TargetPath = $exe
        $sc.WorkingDirectory = $localDir
        $sc.Save()
    } catch {}
} catch {
    Write-Warning "Nao consegui descarregar/emparelhar automaticamente a app Windows: $($_.Exception.Message)"
}

$doAndroid = Read-Host "Queres emparelhar tambem dispositivos Android/Android TV por ADB? (S/n)"
if ($doAndroid -notmatch '^[Nn]') {
    try {
        $adb = Get-Adb
        & $adb start-server | Out-Null

        $devices = Get-ConnectedDevices $adb
        if (-not $devices.Count) {
            Write-Host ""
            Write-Host "Nao ha dispositivos ADB ligados neste momento." -ForegroundColor Yellow
            Write-Host "Se usas ADB por Wi-Fi, podes indicar IP:porta agora. ENTER termina." -ForegroundColor Gray
            while ($true) {
                $target = (Read-Host "IP:porta ADB (ou ENTER)").Trim()
                if (-not $target) { break }
                & $adb connect $target | Out-Host
            }
            $devices = Get-ConnectedDevices $adb
        }

        if ($devices.Count) {
            $apk = Join-Path $localDir "HorariosFamilia-TV.apk"
            $apkUrl = "https://github.com/$Repo/releases/download/android-tv-v1/HorariosFamilia-TV.apk"
            try { Invoke-WebRequest -UseBasicParsing $apkUrl -OutFile $apk } catch { $apk = $null }

            foreach ($serial in $devices) {
                Write-Step "A configurar $serial..."
                $characteristics = (& $adb -s $serial shell getprop ro.build.characteristics 2>$null | Out-String).Trim().ToLowerInvariant()
                $isTv = $characteristics -match 'tv'

                if ($isTv) {
                    if ($apk -and (Test-Path $apk)) {
                        $install = (& $adb -s $serial install -r $apk 2>&1 | Out-String)
                        if ($LASTEXITCODE -ne 0) {
                            Write-Warning "Nao foi possivel atualizar automaticamente o APK em $serial. Mantive a instalacao atual."
                            Write-Host $install -ForegroundColor DarkGray
                        }
                    }
                    & $adb -s $serial shell am start -S -n pt.horariosfamilia.tv/.MainActivity --es agendaKey $key | Out-Host
                } else {
                    & $adb -s $serial shell am start -a android.intent.action.VIEW -d $pairUrl | Out-Host
                }
            }
        }
    } catch {
        Write-Warning "A parte Android/ADB nao ficou concluida: $($_.Exception.Message)"
    }
}

try {
    Set-Clipboard -Value $pairUrl
    Write-Host ""
    Write-Host "Ligacao de emparelhamento copiada para a area de transferencia." -ForegroundColor Cyan
    Write-Host "Se precisares de configurar outro browser/telemovel, abre essa ligacao apenas num dispositivo teu." -ForegroundColor Gray
} catch {}

Write-Host ""
Write-Host "Emparelhamento concluido no que foi possivel configurar automaticamente." -ForegroundColor Green
Write-Host "O codigo fica guardado no Windows apenas em formato protegido por DPAPI." -ForegroundColor Gray
Read-Host "Premir ENTER para fechar"
