<#
Optional explicitly enabled Git sync for EDGEOPS dashboard source files.
Only works on a dedicated 'dashboard-live-edit' branch. The watcher is NOT
enabled by default; Ctrl+C stops it. It never stages secrets or other projects.
It only commits/pushes tracked frontend and backend code in this allowlist.
Never treat auto-push as a substitute for code review, tests, or CI.
#>
param([switch]$Watch, [int]$IntervalSeconds = 20)

$ErrorActionPreference = 'Stop'
$repo = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "Git checkout not found" }
$prefix = (& git -C $PSScriptRoot rev-parse --show-prefix).Trim()
if (-not $prefix) { throw "Dashboard not in Git repository" }
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'dashboard-live-edit') {
    throw "Safety check: switch to dedicated branch 'dashboard-live-edit' first. Current: '$branch'"
}
if ($IntervalSeconds -lt 10) { throw "Minimum sync interval is 10 seconds" }
$allowed = @(
    'index.html','styles.css','app.js','dashboard-auth.js',
    'signin.html','signin.css','signin.js',
    'server.py','requirements.txt','README.md',
    'tests/test_server.py','tests/test_structure.py'
)
$paths = @($allowed | ForEach-Object { $prefix + $_ })

function Sync-Allowed {
    $staged = @(& git -C $repo diff --cached --name-only)
    foreach ($file in $staged) {
        if ($file -and $file -notin $paths) {
            throw "Refusing to commit: unrelated staged file '$file'. Unstage it before sync."
        }
    }
    & git -C $repo add -- $paths
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }
    & git -C $repo diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) { throw "git diff failed" }
    & git -C $repo commit -m "chore(edgeops): sync reviewed dashboard workspace edits"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
    & git -C $repo push origin dashboard-live-edit
    if ($LASTEXITCODE -ne 0) { throw "Push failed; resolve remote divergence manually" }
    Write-Host "EDGEOPS dashboard source synced to origin/dashboard-live-edit"
}

if (-not $Watch) {
    Sync-Allowed
    exit
}
Write-Host "Opt-in dashboard source sync active (every $IntervalSeconds seconds)."
Write-Host "Only explicit source allowlist is committed, on dashboard-live-edit."
Write-Host "Do not store credentials in any source file. Ctrl+C stops the watcher."
while ($true) {
    Sync-Allowed
    Start-Sleep -Seconds $IntervalSeconds
}
