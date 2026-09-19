param(
    [string]$Sala,
    [string]$Cozinha,
    [string]$Quarto
)

$ErrorActionPreference = "Stop"
$Package = "pt.horariosfamilia.tv"
$Activity = "$Package/.MainActivity"
$ReleaseApk = "https://github.com/karlovitch/horarios-familia-2026-2027/releases/latest/download/HorariosFamilia-TV.apk"
$Work = Join-Path $env:TEMP "HorariosFamiliaTV"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

function Get-Adb {
    $cmd = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $zip = Join-Path $Work "platform-tools.zip"
    $dir = Join-Path $Work "platform-tools"
    if (-not (Test-Path (Join-Path $dir "adb.exe"))) {
        Write-Host "A descarregar Android Platform Tools..."
        Invoke-WebRequest "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
        Expand-Archive $zip -DestinationPath $Work -Force
    }
    return (Join-Path $dir "adb.exe")
}

$adb = Get-Adb

function Connect-IfNeeded([string]$Address) {
    if ([string]::IsNullOrWhiteSpace($Address)) { return }
    Write-Host "A ligar a $Address..."
    & $adb connect $Address | Out-Host
}

Connect-IfNeeded $Sala
Connect-IfNeeded $Cozinha
Connect-IfNeeded $Quarto

$apk = Join-Path $Work "HorariosFamilia-TV.apk"
Write-Host "A obter a versão mais recente do APK TV..."
Invoke-WebRequest $ReleaseApk -OutFile $apk

$lines = & $adb devices
$devices = @()
foreach ($line in $lines) {
    if ($line -match "^([^\s]+)\s+device$") { $devices += $Matches[1] }
}
if (-not $devices.Count) {
    throw "Nenhuma box ADB autorizada. Ativa a depuração de rede/ADB e autoriza este PC uma vez."
}

function Profile-For([string]$Serial) {
    if ($Sala -and $Serial -eq $Sala) { return "sala40" }
    if ($Cozinha -and $Serial -eq $Cozinha) { return "cozinha-auto" }
    if ($Quarto -and $Serial -eq $Quarto) { return "quarto49" }

    $model = ((& $adb -s $Serial shell getprop ro.product.model) -join "").Trim()
    if ($model -match "R2A") { return "quarto49" }

    Write-Host ""
    Write-Host "Dispositivo: $Serial  Modelo: $model"
    Write-Host "1 - Sala (Xiaomi TV Box S 3rd Gen / TV 40 polegadas)"
    Write-Host "2 - Cozinha (Xiaomi TV Box S 2nd Gen)"
    Write-Host "3 - Quarto (DIGI R2A / TV 49 polegadas)"
    $choice = Read-Host "Escolhe a divisão"
    switch ($choice) {
        "1" { return "sala40" }
        "2" { return "cozinha-auto" }
        "3" { return "quarto49" }
        default { return "auto" }
    }
}

foreach ($serial in $devices) {
    $profile = Profile-For $serial
    Write-Host ""
    Write-Host "=== $serial -> $profile ==="
    $install = (& $adb -s $serial install -r $apk 2>&1) -join [Environment]::NewLine
    if ($install -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE") {
        Write-Host "Assinatura anterior diferente; a reinstalar o invólucro TV..."
        & $adb -s $serial uninstall $Package | Out-Host
        & $adb -s $serial install $apk | Out-Host
    } elseif ($LASTEXITCODE -ne 0 -or $install -notmatch "Success") {
        Write-Host $install
        throw "Falhou a instalação em $serial"
    } else {
        Write-Host $install
    }

    & $adb -s $serial shell am force-stop $Package | Out-Null
    & $adb -s $serial shell am start -n $Activity --es profile $profile | Out-Host
}

Write-Host ""
Write-Host "Instalação concluída. A APP aparece no launcher das boxes como 'Horários Família'."
Write-Host "As atualizações do site são recebidas automaticamente; não é necessário reinstalar o APK."
