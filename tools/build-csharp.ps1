param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$MSBuildPath
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildOutputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $buildOutputRoot) { throw 'Output directory already exists; choose a new run directory.' }
if (-not $MSBuildPath) {
    $vswherePath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswherePath)) { throw 'Specify -MSBuildPath or install a .NET Framework 4.8 build toolchain.' }
    $MSBuildPath = @(& $vswherePath -latest -products '*' -find 'MSBuild/**/Bin/MSBuild.exe') | Select-Object -First 1
}
if (-not $MSBuildPath -or -not (Test-Path -LiteralPath $MSBuildPath)) { throw 'MSBuild executable was not found.' }
[void][System.IO.Directory]::CreateDirectory($buildOutputRoot)
$projectAudit = [System.IO.File]::ReadAllText((Join-Path $repositoryRoot 'provenance/csharp-project-audit.json'),[System.Text.Encoding]::UTF8) | ConvertFrom-Json
$results = [System.Collections.Generic.List[object]]::new()
$projectIndex = 0
foreach ($projectRecord in $projectAudit) {
    $projectIndex++
    $projectFile = Join-Path $repositoryRoot $projectRecord.project
    [xml]$projectXml = [System.IO.File]::ReadAllText($projectFile,[System.Text.Encoding]::UTF8)
    $missing = @($projectXml.SelectNodes('//*[local-name()="Compile"]') | Where-Object { -not (Test-Path -LiteralPath (Join-Path (Split-Path $projectFile -Parent) $_.Include)) } | ForEach-Object { $_.Include })
    if ($missing.Count -gt 0) {
        $results.Add([pscustomobject]@{project=$projectRecord.project;status='blocked-missing-source';missing_compile_items=$missing;exit_code=$null})
        Write-Output ('BLOCKED ' + $projectRecord.project)
        continue
    }
    $projectOutput = Join-Path $buildOutputRoot ('project-' + $projectIndex.ToString('00'))
    [void][System.IO.Directory]::CreateDirectory($projectOutput)
    $binaryOutput = (Join-Path $projectOutput 'bin') + [System.IO.Path]::DirectorySeparatorChar
    $intermediateOutput = (Join-Path $projectOutput 'obj') + [System.IO.Path]::DirectorySeparatorChar
    $buildArguments = @($projectFile,'/t:Build','/nologo','/verbosity:minimal','/p:Configuration=Release',('/p:OutputPath=' + $binaryOutput),('/p:BaseIntermediateOutputPath=' + $intermediateOutput),('/p:IntermediateOutputPath=' + $intermediateOutput))
    $buildLog = (& $MSBuildPath @buildArguments 2>&1 | Out-String)
    $buildExit = $LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $projectOutput 'build.log'),$buildLog,[System.Text.UTF8Encoding]::new($false))
    $status = if ($buildExit -eq 0) { 'pass' } else { 'failed' }
    $results.Add([pscustomobject]@{project=$projectRecord.project;status=$status;missing_compile_items=@();exit_code=$buildExit;project_sha256=(Get-FileHash -LiteralPath $projectFile -Algorithm SHA256).Hash.ToLowerInvariant();log=('project-' + $projectIndex.ToString('00') + '/build.log')})
    Write-Output ($status.ToUpperInvariant() + ' ' + $projectRecord.project)
}
$report = [pscustomobject]@{scope='Compilation only; research entrypoints were not executed';msbuild_version=((& $MSBuildPath -version -nologo | Out-String).Trim());projects=@($results.ToArray());passed=@($results | Where-Object {$_.status -eq 'pass'}).Count;failed=@($results | Where-Object {$_.status -eq 'failed'}).Count;blocked=@($results | Where-Object {$_.status -eq 'blocked-missing-source'}).Count}
[System.IO.File]::WriteAllText((Join-Path $buildOutputRoot 'build-results.json'),($report | ConvertTo-Json -Depth 8),[System.Text.UTF8Encoding]::new($false))
$report | Select-Object passed,failed,blocked,msbuild_version | ConvertTo-Json
if ($report.failed -gt 0) { exit 1 }
