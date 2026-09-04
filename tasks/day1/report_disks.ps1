<#
.SYNOPSIS
  Отчёт по дискам и службам на списке серверов.
.DESCRIPTION
  Для каждого сервера из servers.txt собирает свободное место на
  логических дисках и состояние служб 1С и SQL Server. Результат
  пишется в CSV. Скрипт запускается по расписанию на msk-mon01.
.NOTES
  На сервере msk-app21 скрипт завершается с ошибкой. Найти причину.
#>

param(
    [string]$ServerList = "$PSScriptRoot\servers.txt",
    [string]$OutFile    = "$PSScriptRoot\disks_report.csv",
    [int]$WarnPercent   = 15
)

$ErrorActionPreference = "Stop"
$services = @("1C:Enterprise 8.3 Server Agent (x86-64)", "MSSQLSERVER", "SQLSERVERAGENT")
$rows = @()

$servers = Get-Content -Path $ServerList | Where-Object { $_ -and -not $_.StartsWith("#") }

foreach ($srv in $servers) {
    Write-Host "== $srv =="
    $disks = Get-CimInstance -ClassName Win32_LogicalDisk -ComputerName $srv -Filter "DriveType = 3"
    foreach ($d in $disks) {
        $freeGb  = [math]::Round($d.FreeSpace / 1GB, 1)
        $sizeGb  = [math]::Round($d.Size / 1GB, 1)
        $freePct = [math]::Round($d.FreeSpace * 100 / $d.Size, 1)
        $status  = if ($freePct -lt $WarnPercent) { "WARN" } else { "OK" }
        $rows += [pscustomobject]@{
            Server  = $srv
            Drive   = $d.DeviceID
            SizeGB  = $sizeGb
            FreeGB  = $freeGb
            FreePct = $freePct
            Status  = $status
        }
    }

    foreach ($name in $services) {
        $svc = Get-Service -ComputerName $srv -Name $name -ErrorAction SilentlyContinue
        $state = if ($svc) { $svc.Status } else { "not installed" }
        $rows += [pscustomobject]@{
            Server  = $srv
            Drive   = "svc:$name"
            SizeGB  = $null
            FreeGB  = $null
            FreePct = $null
            Status  = $state
        }
    }
}

$rows | Export-Csv -Path $OutFile -NoTypeInformation -Encoding UTF8
Write-Host "Готово: $OutFile ($($rows.Count) строк)"
