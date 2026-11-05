param([string]$PythonPath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING='utf-8'
$repositoryRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$candidates=[System.Collections.Generic.List[string]]::new()
if($PythonPath){$candidates.Add($PythonPath)}else{
    foreach($name in @('python','python3')){
        $command=Get-Command $name -ErrorAction SilentlyContinue
        if($command -and $command.Source -notmatch 'WindowsApps'){$candidates.Add($command.Source)}
    }
    foreach($key in @('HKCU:/Software/Python','HKLM:/Software/Python','HKLM:/Software/WOW6432Node/Python')){
        if(Test-Path -LiteralPath $key){
            Get-ChildItem -LiteralPath $key -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.PSChildName -eq 'InstallPath'} | ForEach-Object {
                $registration=Get-ItemProperty -LiteralPath $_.PSPath
                if($registration.ExecutablePath){$candidates.Add([string]$registration.ExecutablePath)}
                elseif($registration.'(default)'){$candidates.Add((Join-Path $registration.'(default)' 'python.exe'))}
            }
        }
    }
}
$selectedPython=$null
foreach($candidate in @($candidates | Select-Object -Unique)){
    if(-not (Test-Path -LiteralPath $candidate)){continue}
    $version=(& $candidate --version 2>&1 | Out-String).Trim()
    if($LASTEXITCODE -eq 0 -and $version -eq 'Python 3.14.2'){$selectedPython=$candidate;break}
}
if(-not $selectedPython){throw 'Python 3.14.2 is required for the recorded environment. Install it or pass -PythonPath with its executable.'}
$environmentRoot=Join-Path $repositoryRoot '.venv'
$environmentPython=Join-Path $environmentRoot 'Scripts/python.exe'
if(-not (Test-Path -LiteralPath $environmentRoot)){
    & $selectedPython -m venv $environmentRoot
    if($LASTEXITCODE -ne 0){throw 'Virtual environment creation failed.'}
}
if(-not (Test-Path -LiteralPath $environmentPython)){throw 'An incomplete .venv already exists. Preserve it and choose a clean project copy.'}
$environmentVersion=(& $environmentPython --version | Out-String).Trim()
if($environmentVersion -ne 'Python 3.14.2'){throw 'Existing .venv uses a different Python version; it was not replaced.'}
& $environmentPython -m pip install --index-url https://pypi.org/simple --disable-pip-version-check -r (Join-Path $repositoryRoot 'requirements.lock.txt')
if($LASTEXITCODE -ne 0){throw 'Pinned dependency installation failed.'}
& $environmentPython -m pip check
if($LASTEXITCODE -ne 0){throw 'Dependency consistency check failed.'}
Write-Output 'Ready. Run ./.venv/Scripts/python.exe tools/verify-reproduction.py --case all --output-dir runs/first-check'
