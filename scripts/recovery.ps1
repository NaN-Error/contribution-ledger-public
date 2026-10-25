# Python must have the project cryptography dependency installed. No credentials in arguments.
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$ErrorActionPreference='Stop'
& python (Join-Path $PSScriptRoot 'recovery.py') @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Recovery did not complete. Do not remove source or partial recovery volumes.' }
