#requires -Version 5.1
<#
Collects a one-session GPU/VRAM baseline for Stream TTS Studio.
Does not start/stop Studio, call TTS, modify configuration, or inspect command-line arguments.
Run with Studio closed, then follow the prompts.
#>

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $PSScriptRoot ("gpu_baseline_{0}.txt" -f $timestamp)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$script:LogWriter = New-Object System.IO.StreamWriter($logPath, $false, $utf8)
$script:LogWriter.AutoFlush = $true

function Write-Log {
    param([string]$Message = "")
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $script:LogWriter.WriteLine($line)
    Write-Host $Message
}

function Write-Section {
    param([string]$Title)
    Write-Log ""
    Write-Log ("=" * 72)
    Write-Log $Title
    Write-Log ("=" * 72)
}

function Get-NvidiaSmiPath {
    $cmd = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidate = Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    if (Test-Path $candidate) { return $candidate }
    return $null
}

$script:NvidiaSmi = Get-NvidiaSmiPath

function Capture-Snapshot {
    param([string]$Label)

    Write-Section ("SNAPSHOT: " + $Label)

    if (-not $script:NvidiaSmi) {
        Write-Log "ERROR: nvidia-smi.exe not found."
    }
    else {
        Write-Log "GPU query:"
        $gpu = & $script:NvidiaSmi --query-gpu=timestamp,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits 2>&1
        foreach ($line in $gpu) { Write-Log ([string]$line) }

        Write-Log "Compute process query (may be unavailable in WDDM mode):"
        $procs = & $script:NvidiaSmi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log ("Process query unavailable; nvidia-smi exit code: " + $LASTEXITCODE)
            foreach ($line in $procs) { Write-Log ([string]$line) }
        }
        elseif (-not $procs) {
            Write-Log "No compute processes reported by nvidia-smi."
        }
        else {
            foreach ($line in $procs) { Write-Log ([string]$line) }
        }
    }

    Write-Log "Relevant Windows processes (name, PID, working set MB):"
    try {
        $items = Get-Process -ErrorAction Stop |
            Where-Object { $_.ProcessName -match "python|studio|stream|obs|chrome|msedge" } |
            Sort-Object ProcessName, Id
        if ($items) {
            foreach ($p in $items) {
                $mb = [math]::Round(($p.WorkingSet64 / 1MB), 1)
                Write-Log ("{0}, PID={1}, RAM={2} MB" -f $p.ProcessName, $p.Id, $mb)
            }
        }
        else {
            Write-Log "No matching processes found."
        }
    }
    catch {
        Write-Log ("Process enumeration failed: " + $_.Exception.Message)
    }
}

function Wait-ForCheckpoint {
    param(
        [string]$Prompt,
        [string]$Label
    )
    Write-Host ""
    Write-Host $Prompt -ForegroundColor Cyan
    [void](Read-Host "Нажми Enter, когда этап завершён")
    Capture-Snapshot -Label $Label
}

function Run-IdleSampling {
    param([int]$Minutes, [int[]]$Milestones)

    Write-Section ("IDLE SAMPLING: {0} minutes" -f $Minutes)
    Write-Log "No TTS requests should be running during this interval."
    $start = Get-Date
    $end = $start.AddMinutes($Minutes)
    $nextSample = $start.AddSeconds(15)
    $captured = @{}

    while ((Get-Date) -lt $end) {
        $now = Get-Date
        $elapsedMinutes = ($now - $start).TotalMinutes

        foreach ($mark in $Milestones) {
            if (-not $captured.ContainsKey([string]$mark) -and $elapsedMinutes -ge $mark) {
                Capture-Snapshot -Label ("Idle {0} min" -f $mark)
                $captured[[string]$mark] = $true
            }
        }

        if ($now -ge $nextSample) {
            $remaining = [math]::Max(0, [int][math]::Ceiling(($end - $now).TotalSeconds))
            Write-Log ("Idle heartbeat: elapsed {0:N1} min; remaining {1} sec" -f $elapsedMinutes, $remaining)
            $nextSample = $now.AddSeconds(15)
        }

        Start-Sleep -Seconds 2
    }

    foreach ($mark in $Milestones) {
        if (-not $captured.ContainsKey([string]$mark)) {
            Capture-Snapshot -Label ("Idle {0} min (end)" -f $mark)
            $captured[[string]$mark] = $true
        }
    }
}

try {
    Write-Section "STREAM TTS STUDIO - GPU BASELINE COLLECTION"
    Write-Log ("Log file: " + $logPath)
    Write-Log ("Computer: " + $env:COMPUTERNAME)
    Write-Log ("User: " + $env:USERNAME)
    Write-Log ("OS: " + (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Caption))
    Write-Log ("PowerShell: " + $PSVersionTable.PSVersion.ToString())
    Write-Log ("nvidia-smi: " + $(if ($script:NvidiaSmi) { $script:NvidiaSmi } else { "NOT FOUND" }))

    if ($script:NvidiaSmi) {
        Write-Log "nvidia-smi driver / CUDA header:"
        $header = & $script:NvidiaSmi 2>&1 | Select-Object -First 4
        foreach ($line in $header) { Write-Log ([string]$line) }
    }

    Write-Host ""
    Write-Host "Перед началом полностью закрой Stream TTS Studio." -ForegroundColor Yellow
    Write-Host "Не запускай другие тяжёлые GPU-задачи на время замера."
    [void](Read-Host "Когда Studio закрыта, нажми Enter для исходного замера")
    Capture-Snapshot -Label "Before Studio start"

    Wait-ForCheckpoint -Prompt "Теперь запусти Studio обычным способом. Дождись сообщения об успешной загрузке CosyVoice. Генерацию пока НЕ запускай." -Label "Model loaded, before first generation"
    Wait-ForCheckpoint -Prompt "Выполни первую прогревающую генерацию и дождись её завершения." -Label "After warm-up generation 1"
    Wait-ForCheckpoint -Prompt "Выполни вторую прогревающую генерацию и дождись её завершения." -Label "After warm-up generation 2"
    Wait-ForCheckpoint -Prompt "Выполни одну обычную генерацию (не прогревочную) и дождись завершения." -Label "After ordinary generation"

    Write-Host ""
    Write-Host "Начинается 15 минут простоя. Не отправляй TTS-запросы и не закрывай Studio." -ForegroundColor Yellow
    Run-IdleSampling -Minutes 15 -Milestones @(5, 15)

    Write-Host ""
    Write-Host "Теперь выполни серию из 5-10 обычных генераций подряд. После последней дождись завершения." -ForegroundColor Cyan
    [void](Read-Host "Нажми Enter после завершения серии")
    Capture-Snapshot -Label "Immediately after 5-10 generation batch"

    Write-Host ""
    Write-Host "Оставь Studio без запросов ещё на 5 минут." -ForegroundColor Yellow
    Run-IdleSampling -Minutes 5 -Milestones @(5)

    Capture-Snapshot -Label "Final snapshot"
    Write-Section "COLLECTION COMPLETE"
    Write-Log ("Report saved to: " + $logPath)
    Write-Host ""
    Write-Host ("Готово. Отчёт: " + $logPath) -ForegroundColor Green
}
catch {
    Write-Log ("FATAL ERROR: " + $_.Exception.Message)
    Write-Log $_.ScriptStackTrace
    Write-Host ("Сбор прерван. Частичный отчёт: " + $logPath) -ForegroundColor Red
}
finally {
    if ($script:LogWriter) {
        $script:LogWriter.Flush()
        $script:LogWriter.Dispose()
    }
}

Read-Host "Нажми Enter для закрытия окна"
