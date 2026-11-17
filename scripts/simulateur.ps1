<#
  Simulateur de trafic temps réel (sans Python local : tout tourne dans Docker).
  Envoie des transactions des 4 opérateurs (Vodacom, Airtel, Orange, Visa) à l'integration-layer :
  le tableau de bord http://localhost se remplit en direct.

  Usage (PowerShell, à la racine du projet, plateforme démarrée) :
    .\scripts\simulateur.ps1                      # trafic normal, 20 tx/s
    .\scripts\simulateur.ps1 -Mode Fraude         # épisodes de fraude (démo jury), 5 tx/s
    .\scripts\simulateur.ps1 -Mode Rapport        # rejoue 254 victimes et écrit ml/reports/realtime_replay.json
    .\scripts\simulateur.ps1 -Rate 50 -Count 5000 # 5000 transactions à 50/s puis arrêt
    .\scripts\simulateur.ps1 -Stop                # arrête le simulateur
#>
param(
    [ValidateSet("Trafic", "Fraude", "Rapport")][string]$Mode = "Trafic",
    [double]$Rate = 0,
    [int]$Count = 0,
    [switch]$Stop,
    [string]$Network = "detection2026_default"
)

$name = "sim_traffic"
$root = (Resolve-Path "$PSScriptRoot\..").Path

docker rm -f $name 2>$null | Out-Null
if ($Stop) { Write-Host "Simulateur arrêté."; return }

docker image inspect fraud-rdc/scoring-service:dev 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Image fraud-rdc/scoring-service:dev absente : lancer d'abord 'docker compose up -d --build'." }

switch ($Mode) {
    "Trafic"  { $args_ = @("--rate", $(if ($Rate -gt 0) { $Rate } else { 20 })) }
    "Fraude"  { $args_ = @("--only-fraud-episodes", "--rate", $(if ($Rate -gt 0) { $Rate } else { 5 })) }
    "Rapport" { $args_ = @("--only-fraud-episodes", "--fraud-users", "254", "--rate", $(if ($Rate -gt 0) { $Rate } else { 12 }), "--quiet", "--report") }
}
if ($Count -gt 0) { $args_ += @("--n", $Count) }

# le rapport doit pouvoir écrire dans ml/reports ; sinon le dossier est monté en lecture seule
$mount = if ($Mode -eq "Rapport") { "${root}:/work" } else { "${root}:/work:ro" }
$cmd = "pip install -q --user --no-warn-script-location httpx==0.27.0 && python scripts/simulate_transactions.py --url http://integration-layer:8002 " + ($args_ -join " ")

docker run -d --name $name --network $Network -v $mount -w /work --entrypoint sh fraud-rdc/scoring-service:dev -c $cmd | Out-Null
Write-Host "Simulateur démarré (mode $Mode). Tableau de bord : http://localhost"
Write-Host "Suivre : docker logs -f $name    |    Arrêter : .\scripts\simulateur.ps1 -Stop"
