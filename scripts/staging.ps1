param([Parameter(Mandatory=$true)][ValidateSet('init','prepare','drill','start','stop','status','setup-owner')][string]$Action,
[string]$Hostname='', [string]$BindAddress='127.0.0.1', [string]$ClientRanges='127.0.0.0/8', [string]$Confirm='')
$ErrorActionPreference='Stop'
$arguments=@((Join-Path $PSScriptRoot 'staging.py'),$Action,'--bind',$BindAddress,'--cidrs',$ClientRanges)
if ($Hostname) { $arguments+=@('--host',$Hostname) }
if ($Confirm) { $arguments+=@('--confirm',$Confirm) }
& python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Restricted staging command did not complete. No readiness claim was made.' }
