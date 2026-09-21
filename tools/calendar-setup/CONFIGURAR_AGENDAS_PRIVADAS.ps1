param(
    [string]$Repo = "karlovitch/horarios-familia-2026-2027"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Configurar agendas privadas - Horarios Familia"

function Write-Title([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host ("  " + $Text) -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host ("[+] " + $Text) -ForegroundColor Green
}

function Get-GhPath {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $common = @(
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )
    foreach ($path in $common) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Ensure-GitHubCli {
    $gh = Get-GhPath
    if ($gh) { return $gh }

    Write-Step "GitHub CLI nao encontrado. A tentar instalar com winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Start-Process "https://cli.github.com/"
        throw "Nao encontrei o winget. Instala o GitHub CLI na pagina que foi aberta e volta a executar este script."
    }

    # Envia a saída do winget apenas para o ecrã. Assim, o texto da instalação
    # não entra no valor devolvido por esta função (que tem de ser apenas gh.exe).
    & winget install --id GitHub.cli -e --source winget --accept-source-agreements --accept-package-agreements | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "A instalacao automatica do GitHub CLI falhou."
    }

    $gh = Get-GhPath
    if (-not $gh) {
        $gh = "$env:ProgramFiles\GitHub CLI\gh.exe"
    }
    if (-not (Test-Path $gh)) {
        throw "O GitHub CLI foi instalado, mas nao consegui localizar gh.exe. Fecha esta janela e volta a executar o script."
    }
    return $gh
}

function Ensure-GitHubLogin([string]$Gh) {
    & $Gh auth status --hostname github.com *> $null
    if ($LASTEXITCODE -eq 0) { return }

    Write-Step "E necessario iniciar sessao no GitHub. O browser vai abrir."
    & $Gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel autenticar no GitHub."
    }
}

function Test-SecretIcalUrl([string]$Url) {
    if ([string]::IsNullOrWhiteSpace($Url)) { return $false }
    return ($Url -match '^https://calendar\.google\.com/calendar/ical/.+/private-.+/basic\.ics(?:\?.*)?$')
}

function Read-SecretIcalUrl([string]$Owner) {
    while ($true) {
        Write-Host ""
        Write-Host "Google Calendar -> Definicoes -> calendario de $Owner -> Integrar calendario" -ForegroundColor Yellow
        Write-Host "Copia o campo: Endereco secreto em formato iCal" -ForegroundColor Yellow
        $value = (Read-Host "Cola aqui o endereco secreto iCal de $Owner").Trim()

        if (Test-SecretIcalUrl $value) {
            Write-Host "Endereco de $Owner reconhecido." -ForegroundColor Green
            return $value
        }

        Write-Warning "O endereco nao parece ser um 'Endereco secreto em formato iCal' do Google Calendar."
        $retry = Read-Host "Queres tentar novamente? (S/n)"
        if ($retry -match '^[Nn]') {
            throw "Configuracao cancelada: falta o endereco iCal privado de $Owner."
        }
    }
}

function New-AgendaPassphrase {
    $bytes = New-Object byte[] 20
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Set-RepoSecret([string]$Gh, [string]$Name, [string]$Value) {
    $Value | & $Gh secret set $Name --repo $Repo
    if ($LASTEXITCODE -ne 0) {
        throw "Falhou a criacao/atualizacao do secret $Name."
    }
}

function Get-LatestSyncRun([string]$Gh) {
    $json = & $Gh run list --repo $Repo --workflow sync-personal-calendars.yml --limit 1 --json databaseId,status,conclusion,url,createdAt
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($json)) { return $null }
    return ($json | ConvertFrom-Json | Select-Object -First 1)
}

Write-Title "HORARIOS FAMILIA - CONFIGURAR AGENDAS PRIVADAS"

Write-Host "Este assistente vai:" -ForegroundColor White
Write-Host "  1. configurar o calendario pessoal de Carlos;" -ForegroundColor Gray
Write-Host "  2. configurar o calendario pessoal de Sandrinha;" -ForegroundColor Gray
Write-Host "  3. gerar um codigo privado forte;" -ForegroundColor Gray
Write-Host "  4. criar automaticamente os GitHub Actions Secrets;" -ForegroundColor Gray
Write-Host "  5. executar e validar a primeira sincronizacao." -ForegroundColor Gray
Write-Host ""
Write-Host "Os enderecos iCal e o codigo nao sao gravados pelo script no repositorio." -ForegroundColor Yellow

$Gh = Ensure-GitHubCli
Ensure-GitHubLogin $Gh

Write-Step "A confirmar acesso ao repositorio $Repo..."
& $Gh repo view $Repo --json nameWithOwner *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Nao tens acesso ao repositorio $Repo com a conta GitHub autenticada."
}

Write-Step "A abrir as definicoes do Google Calendar."
Start-Process "https://calendar.google.com/calendar/u/0/r/settings"

Write-Host ""
Write-Host "No Google Calendar, escolhe o calendario principal de Carlos e copia o endereco secreto iCal." -ForegroundColor Cyan
$carlosUrl = Read-SecretIcalUrl "Carlos"

Write-Host ""
Write-Host "Agora muda para a conta/calendario principal da Sandrinha e copia o respetivo endereco secreto iCal." -ForegroundColor Cyan
$openAgain = Read-Host "Premir ENTER para voltar a abrir as definicoes do Google Calendar"
Start-Process "https://calendar.google.com/calendar/u/0/r/settings"
$sandrinhaUrl = Read-SecretIcalUrl "Sandrinha"

Write-Step "A gerar um codigo privado para desencriptar a Agenda pessoal..."
$passphrase = New-AgendaPassphrase

Write-Step "A criar os tres GitHub Actions Secrets..."
Set-RepoSecret $Gh "CARLOS_CALENDAR_ICS_URL" $carlosUrl
Set-RepoSecret $Gh "SANDRINHA_CALENDAR_ICS_URL" $sandrinhaUrl
Set-RepoSecret $Gh "PERSONAL_CALENDAR_PASSPHRASE" $passphrase

Write-Step "A confirmar os nomes dos Secrets criados..."
$secretNames = & $Gh secret list --repo $Repo --json name --jq '.[].name'
$required = @(
    "CARLOS_CALENDAR_ICS_URL",
    "SANDRINHA_CALENDAR_ICS_URL",
    "PERSONAL_CALENDAR_PASSPHRASE"
)
foreach ($name in $required) {
    if ($secretNames -notcontains $name) {
        throw "O secret $name nao aparece na lista do repositorio."
    }
}
Write-Host "Os tres Secrets estao configurados." -ForegroundColor Green

Write-Step "A iniciar a primeira sincronizacao..."
$before = Get-LatestSyncRun $Gh
$beforeId = if ($before) { [string]$before.databaseId } else { "" }

& $Gh workflow run sync-personal-calendars.yml --repo $Repo --ref main
if ($LASTEXITCODE -ne 0) {
    throw "Nao foi possivel iniciar o workflow de sincronizacao."
}

$run = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    $candidate = Get-LatestSyncRun $Gh
    if ($candidate -and ([string]$candidate.databaseId -ne $beforeId)) {
        $run = $candidate
        break
    }
}

if (-not $run) {
    throw "O workflow foi iniciado, mas nao consegui identificar a nova execucao."
}

Write-Host ("Execucao GitHub Actions: " + $run.url) -ForegroundColor DarkGray
Write-Step "A acompanhar a sincronizacao ate ao fim..."
& $Gh run watch $run.databaseId --repo $Repo --exit-status
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "A sincronizacao terminou com erro. Abre a pagina abaixo para ver o detalhe:" -ForegroundColor Red
    Write-Host $run.url -ForegroundColor Yellow
    throw "Primeira sincronizacao falhou."
}

try {
    Set-Clipboard -Value $passphrase
    $clipboardMessage = "O codigo foi tambem copiado para a area de transferencia."
}
catch {
    $clipboardMessage = "Nao foi possivel copiar automaticamente o codigo."
}

Write-Title "CONFIGURACAO CONCLUIDA"
Write-Host "Sincronizacao das agendas: OK" -ForegroundColor Green
Write-Host ""
Write-Host "CODIGO DA AGENDA PESSOAL:" -ForegroundColor Yellow
Write-Host ""
Write-Host ("    " + $passphrase) -ForegroundColor White -BackgroundColor DarkBlue
Write-Host ""
Write-Host $clipboardMessage -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANTE:" -ForegroundColor Yellow
Write-Host "Guarda este codigo num local seguro. Vais introduzi-lo uma vez em cada dispositivo/app." -ForegroundColor Gray
Write-Host "Nao precisas de guardar nem voltar a usar os dois enderecos iCal." -ForegroundColor Gray
Write-Host ""
Write-Host "A abrir a app Horarios Familia..." -ForegroundColor Cyan
Start-Process "https://karlovitch.github.io/horarios-familia-2026-2027/"

Write-Host ""
Write-Host "Na app, toca em 'Agenda pessoal - Ligar' e cola o codigo acima." -ForegroundColor Green
Read-Host "Premir ENTER para fechar"
