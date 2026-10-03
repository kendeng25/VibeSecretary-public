param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("session-start", "pre-tool-use", "user-prompt-submit")]
    [string]$Hook
)

$ErrorActionPreference = "Stop"

try {
    if ([string]::IsNullOrWhiteSpace($env:PLUGIN_ROOT)) {
        throw "PLUGIN_ROOT is not set."
    }

    $runtimePath = Join-Path $env:PLUGIN_ROOT "runtime\runtime.json"
    $runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
    $pythonExecutable = [string]$runtime.python_executable
    if ([string]::IsNullOrWhiteSpace($pythonExecutable) -or
        -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "Configured Python executable does not exist: $pythonExecutable"
    }

    $hookScripts = @{
        "session-start" = "session_start.py"
        "pre-tool-use" = "pre_tool_use.py"
        "user-prompt-submit" = "user_prompt_submit.py"
    }
    $hookScript = Join-Path $env:PLUGIN_ROOT ("hooks\" + $hookScripts[$Hook])
    if (-not (Test-Path -LiteralPath $hookScript -PathType Leaf)) {
        throw "Hook script does not exist: $hookScript"
    }

    & $pythonExecutable $hookScript
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine("VibeSecretary Hook launcher failed: $($_.Exception.Message)")
    exit 1
}