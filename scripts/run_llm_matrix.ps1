param(
  [string]$OutputPrefix = "outputs/exp_matrix",
  [int]$TotalSteps = 1600,
  [int]$Seed = 11,
  [double]$SelfishShare = 0.35,
  [string]$ExperimentGroup = "default",
  [switch]$Offline,
  [switch]$SkipSummary
)

$ErrorActionPreference = "Stop"

function Set-BaseEnv {
  $env:SANDBOX_TOTAL_STEPS = "$TotalSteps"
  $env:SANDBOX_RANDOM_SEED = "$Seed"
  $env:SANDBOX_NUM_MINERS = "9"
  $env:SANDBOX_NUM_FULL_NODES = "12"

  $env:SANDBOX_TOPOLOGY_TYPE = "random"
  $env:SANDBOX_EDGE_PROB = "0.24"
  $env:SANDBOX_MIN_LATENCY = "2.0"
  $env:SANDBOX_MAX_LATENCY = "5.0"
  $env:SANDBOX_MIN_RELIABILITY = "0.96"
  $env:SANDBOX_MAX_RELIABILITY = "1.0"
  $env:SANDBOX_BLOCK_DISCOVERY_CHANCE = "0.05"
  $env:SANDBOX_MAX_HOPS = "5"

  $env:SANDBOX_SELFISH_HASH_POWER_SHARE = "$SelfishShare"

  $env:SANDBOX_ENABLE_FORUM = "0"
  $env:SANDBOX_ENABLE_ATTACK_JAMMING = "0"
  $env:SANDBOX_SNAPSHOT_INTERVAL_BLOCKS = "20"
  $env:SANDBOX_PROGRESS_INTERVAL_STEPS = "100"
  $env:SANDBOX_SHOW_SNAPSHOTS = "0"
  $env:SANDBOX_LIVE_WINDOW_SUMMARY = "0"
  $env:SANDBOX_SAVE_ARTIFACTS = "1"
  $env:SANDBOX_EXPORT_PROMPTS = "1"

  if ($Offline) {
    $env:SANDBOX_LLM_OFFLINE = "1"
    $env:SANDBOX_PREFLIGHT_LLM = "0"
  }
  else {
    $env:SANDBOX_LLM_OFFLINE = "0"
    $env:SANDBOX_PREFLIGHT_LLM = "1"
  }
  $env:SANDBOX_PREFLIGHT_STRICT = "0"
  $env:SANDBOX_LLM_MAX_WORKERS = "1"

  $env:SANDBOX_PERSONA_DEVIATION_LEVEL = "medium"
  $env:SANDBOX_PERSONA_ACTION_SET = "extended"
  $env:SANDBOX_STRATEGY_CONSTRAINT_STRICTNESS = "safe"
  $env:SANDBOX_EXPERIMENT_GROUP = "$ExperimentGroup"
}

function Clear-EconAndDs {
  Remove-Item Env:SANDBOX_ECON_PRICE_MODEL -ErrorAction SilentlyContinue
  Remove-Item Env:SANDBOX_ECON_STATIC_TOKEN_PRICE -ErrorAction SilentlyContinue
  Remove-Item Env:SANDBOX_ECON_PRICE_FROM_ORPHAN -ErrorAction SilentlyContinue
  Remove-Item Env:SANDBOX_DS_TARGET_CONFIRMATIONS -ErrorAction SilentlyContinue
  Remove-Item Env:SANDBOX_DS_PAYMENT_AMOUNT -ErrorAction SilentlyContinue
  Remove-Item Env:SANDBOX_DS_ATTACK_INTERVAL_BLOCKS -ErrorAction SilentlyContinue
}

$strategies = @("classic", "stubborn", "intermittent_epoch", "social", "stubborn_ds")
$modes = @("strategy_first", "persona_first", "high_persona")

Set-BaseEnv

$runCount = 0
$total = $strategies.Count * $modes.Count

foreach ($s in $strategies) {
  foreach ($m in $modes) {
    $runCount += 1
    Write-Host "[$runCount/$total] strategy=$s mode=$m"

    $env:SANDBOX_SELFISH_STRATEGY = $s
    $env:SANDBOX_LLM_DECISION_MODE = $m

    Clear-EconAndDs

    if ($s -in @("social", "stubborn_ds")) {
      $env:SANDBOX_ECONOMY_ENABLED = "1"
      $env:SANDBOX_ECON_PRICE_MODEL = "static"
      $env:SANDBOX_ECON_STATIC_TOKEN_PRICE = "100"
      $env:SANDBOX_ECON_PRICE_FROM_ORPHAN = "0"
    }
    else {
      $env:SANDBOX_ECONOMY_ENABLED = "0"
    }

    if ($s -eq "stubborn_ds") {
      $env:SANDBOX_DS_TARGET_CONFIRMATIONS = "1"
      $env:SANDBOX_DS_PAYMENT_AMOUNT = "3.0"
      $env:SANDBOX_DS_ATTACK_INTERVAL_BLOCKS = "12"
    }

    $env:SANDBOX_OUTPUT_ROOT = "${OutputPrefix}_${s}_${m}_a035"

    python -m experiments.run_llm_sandbox
    if ($LASTEXITCODE -ne 0) {
      throw "Run failed for strategy=$s mode=$m"
    }
  }
}

Write-Host "All matrix runs completed."
if (-not $SkipSummary) {
  $summaryOut = "${OutputPrefix}_summary.csv"
  python scripts/summarize_llm_matrix.py --prefix $OutputPrefix --group $ExperimentGroup --out $summaryOut
  if ($LASTEXITCODE -ne 0) {
    throw "Summary generation failed"
  }
  Write-Host "Summary saved: $summaryOut"
}
else {
  Write-Host "Tip: python scripts/summarize_llm_matrix.py --prefix $OutputPrefix --group $ExperimentGroup"
}
