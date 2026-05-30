[CmdletBinding()]
param (
    [Parameter(Mandatory=$false)]
    [string]$TargetFolder = ".",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile = "repo_context.txt"
)

$RootPath = $pwd.Path
$TargetFolderInfo = Resolve-Path $TargetFolder -ErrorAction Stop

# Dynamiczne generowanie nazwy pliku wyjsciowego
if ($TargetFolderInfo.Path -eq $RootPath) {
    $ActualOutputFile = $OutputFile
} else {
    $LeafFolder = Split-Path $TargetFolderInfo.Path -Leaf
    $Base = [System.IO.Path]::GetFileNameWithoutExtension($OutputFile)
    $Ext = [System.IO.Path]::GetExtension($OutputFile)
    $ActualOutputFile = "${Base}_${LeafFolder}${Ext}"
}

$OutputFullPath = Join-Path $RootPath $ActualOutputFile

$ExcludePattern = '(?i)backup|working|\d{4}[-_]?\d{2}[-_]?\d{2}'
$ExcludeExtensions = @(
    '.exe', '.dll', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz', '.7z',
    '.pyc', '.pyd', '.log', '.key', '.cert', '.crt', '.pem', '.pfx', '.db', 
    '.sqlite', '.sqlite3', '.bak', '.env', '.lock', '.csv', '.xlsx'
)

if (Test-Path $OutputFullPath) {
    Remove-Item $OutputFullPath -Force
}

$files = Get-ChildItem -Path $TargetFolderInfo.Path -File -Recurse -Force | Where-Object {
    $relativePath = $_.FullName.Substring($TargetFolderInfo.Path.Length)
    
    # Odrzuc sam plik wynikowy w obu wariantach nazwy
    if ($_.Name -eq $OutputFile -or $_.Name -eq $ActualOutputFile) { return $false }
    if ($relativePath -match '\\\.git\\|\\__pycache__\\|\\venv\\|\\\.venv\\') { return $false }
    if ($ExcludeExtensions -contains $_.Extension) { return $false }
    if ($_.Name -match $ExcludePattern) { return $false }

    return $true
}

$stream = [System.IO.StreamWriter]::new($OutputFullPath, $false, [System.Text.Encoding]::UTF8)

try {
    # 1. Szukanie docker-compose na roocie
    if ($TargetFolderInfo.Path -ne $RootPath) {
        $composeFiles = Get-ChildItem -Path $RootPath -Filter "docker-compose.y*ml" -File -ErrorAction SilentlyContinue
        
        if ($null -ne $composeFiles -and $composeFiles.Count -gt 0) {
            $composeFile = $composeFiles[0].FullName
            $composeName = $composeFiles[0].Name
            
            $stream.WriteLine("`n`n================================================================")
            $stream.WriteLine("FILE: [ROOT_DIR]\$composeName")
            $stream.WriteLine("INFO: Ten plik znajduje sie w glownym katalogu projektu. Pozostale pliki pochodza z podkatalogu: $TargetFolder")
            $stream.WriteLine("================================================================")
            
            try {
                $content = Get-Content -Path $composeFile -Raw -ErrorAction Stop
                if ($null -ne $content) {
                    $stream.WriteLine($content)
                }
            } catch {
                $stream.WriteLine("[BLAD ODCZYTU PLIKU DOCKER-COMPOSE: $($_.Exception.Message)]")
            }
        }
    }

    # 2. Przetwarzanie docelowego katalogu
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($TargetFolderInfo.Path.Length).TrimStart('\')
        $stream.WriteLine("`n`n================================================================")
        $stream.WriteLine("FILE: $relativePath")
        $stream.WriteLine("================================================================")
        
        try {
            $content = Get-Content -Path $file.FullName -Raw -ErrorAction Stop
            if ($null -ne $content) {
                $stream.WriteLine($content)
            }
        } catch {
            $stream.WriteLine("[BLAD ODCZYTU PLIKU: $($_.Exception.Message)]")
        }
    }
} finally {
    $stream.Dispose()
}

Write-Host "[OK] Wygenerowano bezpieczny kontekst dla '$TargetFolder' w: $OutputFullPath" -ForegroundColor Green