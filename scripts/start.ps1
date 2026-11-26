# Projeyi Podman Compose ile başlatır.
# Bu dosyayı compose.yaml / docker-compose.yml dosyanızın bulunduğu proje
# klasörüne koyun ve o klasörden çalıştırın.

$ErrorActionPreference = 'Stop'

function Invoke-PodmanCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $ComposeArgs
    )

    Write-Host "`n> podman-compose $($ComposeArgs -join ' ')" -ForegroundColor Cyan
    & podman-compose @ComposeArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Komut başarısız oldu (çıkış kodu: $LASTEXITCODE)."
    }
}

try {
    # Script hangi klasörden çağrılırsa çağrılsın proje dizininde çalış.
    Set-Location -LiteralPath $PSScriptRoot

    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw "'podman' komutu bulunamadı. Podman Desktop/Podman CLI kurulumunu ve PATH ayarını kontrol edin."
    }

    if (-not (Get-Command podman-compose -ErrorAction SilentlyContinue)) {
        throw "'podman-compose' komutu bulunamadı. podman-compose kurulumunu ve PATH ayarını kontrol edin."
    }

    $composeFiles = @('compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml')
    $composeFileExists = $false
    foreach ($file in $composeFiles) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot $file)) {
            $composeFileExists = $true
            break
        }
    }
    if (-not $composeFileExists) {
        throw "Proje klasöründe compose.yaml, compose.yml veya docker-compose.yml dosyası bulunamadı."
    }

    # Podman servisi/makinesi kapalıysa başlatmayı dene.
    Write-Host 'Podman bağlantısı kontrol ediliyor...' -ForegroundColor Yellow
    & podman info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Podman makinesi başlatılıyor...' -ForegroundColor Yellow
        & podman machine start
        if ($LASTEXITCODE -ne 0) {
            throw "Podman makinesi başlatılamadı. İlk kurulumsa önce 'podman machine init' komutunu çalıştırın."
        }
    }

    Write-Host "`nUygulama başlatılıyor..." -ForegroundColor Green

    Invoke-PodmanCompose -ComposeArgs @('build', 'app')
    Invoke-PodmanCompose -ComposeArgs @('up', '-d', 'postgres')
    Invoke-PodmanCompose -ComposeArgs @('run', '--rm', 'app', 'alembic', 'upgrade', 'head')
    Invoke-PodmanCompose -ComposeArgs @('up', '-d')

    Write-Host "`nSistem başarıyla başlatıldı." -ForegroundColor Green
    Invoke-PodmanCompose -ComposeArgs @('ps')
}
catch {
    Write-Host "`nHATA: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
