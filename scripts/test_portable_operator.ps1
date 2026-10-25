# Read/execute function declarations only; no real installation, downloads or app startup.
$ErrorActionPreference='Stop'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'portable.ps1'),[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Portable operator syntax is invalid.' }
$functions=$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)
foreach ($function in $functions) {
    $definition=$function.Extent.Text.Replace('$PSScriptRoot',("'"+$PSScriptRoot.Replace("'","''")+"'"))
    Invoke-Expression $definition
}
$script:checks=0
$appRoot=Split-Path $PSScriptRoot -Parent
function Assert([bool]$Value,[string]$Message) { if (-not $Value) { throw $Message }; $script:checks++ }
$expectedNode='C:\synthetic-runtime\node.exe'
$script:fakeProcess=[PSCustomObject]@{Id=33001;StartTime=[DateTime]::UtcNow;Path=$null}
$record=Process-Record $script:fakeProcess $expectedNode
Assert ($record.path -eq $expectedNode) 'A launched process with an empty cached Path still needs an exact executable record.'
function Get-Process { param($Id,$ErrorAction); return $script:fakeProcess }
$script:fakeProcess.Path=$expectedNode
$record.path=$null
Assert ($null -ne (Owned-Process $record $expectedNode)) 'An older blank record requires the exact executable, PID and creation time.'
$record.start_ticks--
Assert ($null -eq (Owned-Process $record $expectedNode)) 'A reused PID must never be adopted.'
$record.start_ticks++
$script:fakeProcess.Path='C:\foreign\node.exe'
Assert ($null -eq (Owned-Process $record $expectedNode)) 'A foreign executable must not be stopped for a blank record.'
$script:fakeProcess.Path=$expectedNode;$record.path='C:\foreign\node.exe'
Assert ($null -eq (Owned-Process $record $expectedNode)) 'A nonempty mismatched record must not be adopted.'
try { Process-Record $script:fakeProcess 'C:\foreign\node.exe'; throw 'Mismatched launch was accepted.' } catch { Assert ($_.Exception.Message -like '*Unexpected launched executable*') 'Mismatched launches must be refused.' }
$script:fakeProcess=$null
Assert ($null -eq (Owned-Process $record $expectedNode)) 'A missing process must remain missing.'
Remove-Item Function:\Get-Process
$privateRoot=$appRoot
try { Protect-Data; throw 'The program directory was accepted as data.' } catch { Assert ($_.Exception.Message -like '*outside the program folder*') 'The program directory must never receive personal data.' }
$privateRoot=Join-Path $appRoot 'custom-data'
try { Protect-Data; throw 'A nested program directory was accepted as data.' } catch { Assert ($_.Exception.Message -like '*outside the program folder*') 'Nested program directories must be refused before file or ACL changes.' }
$foreign=Join-Path $env:TEMP ('ContributionLedgerOperatorCheck_'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $foreign | Out-Null
[IO.File]::WriteAllText((Join-Path $foreign 'unrelated.txt'),'Keep this existing file unchanged.')
$privateRoot=$foreign
$before=(Get-Acl -LiteralPath $foreign).Sddl
try { Protect-Data; throw 'An unrelated directory was adopted.' } catch { Assert ($_.Exception.Message -like '*unrelated files*') 'Unrelated data must be refused before permission changes.' }
Assert ((Get-Acl -LiteralPath $foreign).Sddl -eq $before) 'Unrelated directory permissions must remain unchanged.'
$privateRoot=[IO.Path]::GetPathRoot($foreign)
try { Protect-Data; throw 'A drive root was adopted.' } catch { Assert ($_.Exception.Message -like '*drive root*') 'Drive roots must be refused.' }
$testSettings=[PSCustomObject]@{url='https://aka.ms/vs/17/release/vc_redist.x64.exe';sha256=('a'*64)}
$script:downloads=0;$script:launches=0
$privateRoot='C:\synthetic-portable-operator'
function Windows-Runtime-Ready { return $false }
$NoBrowser=$true
try { Ensure-Windows-Runtime; throw 'Missing runtime was unexpectedly accepted.' } catch { Assert ($_.Exception.Message -like '*unattended checks never install*') 'Unattended mode must refuse a missing runtime.' }
function Windows-Runtime-Ready { return $true }
Ensure-Windows-Runtime;Assert ($script:downloads -eq 0) 'Present Windows runtime must not download.'
function Windows-Runtime-Ready { return $false }
$NoBrowser=$false
function Get-Content { return '{"optional_windows_prerequisite":{"url":"https://aka.ms/vs/17/release/vc_redist.x64.exe","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}' }
function Test-Path { return $true }
function Get-Item { return [PSCustomObject]@{Attributes=[IO.FileAttributes]::Normal} }
function Get-FileHash { return [PSCustomObject]@{Hash=('b'*64)} }
function Invoke-WebRequest { $script:downloads++ }
function Start-Process { $script:launches++;throw 'Installer must not execute in this check.' }
try { Ensure-Windows-Runtime; throw 'Tampered installer was unexpectedly accepted.' } catch { Assert ($_.Exception.Message -like '*checksum changed*') 'Checksum mismatch must refuse execution.' }
Assert ($script:launches -eq 0) 'Checksum mismatch must not launch an installer.'
function Get-FileHash { return [PSCustomObject]@{Hash=('a'*64)} }
function Get-AuthenticodeSignature { return [PSCustomObject]@{Status='NotSigned';SignerCertificate=$null} }
try { Ensure-Windows-Runtime; throw 'Unsigned installer was unexpectedly accepted.' } catch { Assert ($_.Exception.Message -like '*signature could not be verified*') 'Invalid signature must refuse execution.' }
Assert ($script:launches -eq 0) 'Invalid signature must not launch an installer.'
Write-Host ('PASS: '+$script:checks+' portable prerequisite safety checks; no installer or download executed.')
