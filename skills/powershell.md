---
name: powershell
description: PowerShell-скрипты для Windows Server — отчёты, службы, диски, журналы событий, удалённое выполнение
triggers: PowerShell, .ps1, Get-Service, Get-CimInstance, Get-WinEvent, Invoke-Command, Windows Server, служба, журнал событий
combines_with: debug-loop, markdown, sqlite
---

# PowerShell — правила написания и проверки скриптов

## Цикл выполнения

1. Написать минимальный скрипт в файл `.ps1` (UTF-8 с BOM для кириллицы
   в Windows PowerShell 5.1; UTF-8 без BOM для PowerShell 7).
2. Запустить: `powershell -NoProfile -ExecutionPolicy Bypass -File script.ps1`
   (или `pwsh -File`). На macOS/Linux — `pwsh`.
3. Прочитать вывод и ошибки. Исправить. Повторить. Максимум 5 итераций.
4. Скрипт, который не запускался, пользователю не отдаётся.

## Версии

- Windows PowerShell 5.1 — предустановлен на всех Windows Server.
  Параметр `-ComputerName` есть у `Get-Service`, `Get-EventLog`.
- PowerShell 7 (`pwsh`) — `-ComputerName` у `Get-Service` удалён; для
  удалённых вызовов `Invoke-Command -ComputerName` или `Get-CimInstance
  -ComputerName`.
- Если версия не оговорена — писать код, работающий в обеих:
  `Get-CimInstance` вместо `Get-WmiObject`, `Invoke-Command` вместо
  `-ComputerName` у команд, где его нет в 7.

## Ошибки

- `$ErrorActionPreference = "Stop"` в начале скрипта, `try/catch` вокруг
  каждого удалённого вызова. В `catch` — имя сервера и текст ошибки,
  продолжить цикл по серверам.
- Значения `$null` и `0` проверять до деления и до `[math]::Round`.
- Не глушить ошибки `-ErrorAction SilentlyContinue` без последующей
  проверки результата.

## Типовые задачи

Диски:
```powershell
Get-CimInstance Win32_LogicalDisk -Filter "DriveType = 3" |
  Where-Object { $_.Size } |
  Select-Object DeviceID,
    @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}},
    @{n='FreeGB';e={[math]::Round($_.FreeSpace/1GB,1)}},
    @{n='FreePct';e={[math]::Round($_.FreeSpace*100/$_.Size,1)}}
```

Службы 1С и SQL:
```powershell
Get-Service | Where-Object { $_.Name -match '^(1C|MSSQL|SQLSERVERAGENT)' } |
  Select-Object Name, Status, StartType
```

Журнал событий за сутки, только ошибки:
```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddDays(-1)} |
  Select-Object TimeCreated, Id, ProviderName, Message -First 50
```

Проверка порта:
```powershell
Test-NetConnection msk-app20 -Port 1541 | Select-Object ComputerName, RemotePort, TcpTestSucceeded
```

## Вывод

- Результаты — объектами (`[pscustomobject]`), не строками. Экспорт:
  `Export-Csv -NoTypeInformation -Encoding UTF8`.
- В консоль — `Write-Host` только для хода выполнения; данные — через
  конвейер.

## Безопасность

- Команды удаления (`Remove-Item`, `Stop-Service`, `Restart-Computer`,
  правка реестра) — только после явного подтверждения пользователя и с
  `-WhatIf` в первом прогоне.
- Пароли и учётные данные не в скрипте: `Get-Credential` или
  переменные окружения.
