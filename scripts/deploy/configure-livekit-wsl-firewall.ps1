#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$WslCreatorId = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"

foreach ($Name in @("LuminousLiveKitTcp", "LuminousLiveKitUdp")) {
    $Existing = Get-NetFirewallHyperVRule -VMCreatorId $WslCreatorId -Name $Name -ErrorAction SilentlyContinue
    if ($null -ne $Existing) {
        Remove-NetFirewallHyperVRule -VMCreatorId $WslCreatorId -Name $Name
    }
}

New-NetFirewallHyperVRule `
    -Name "LuminousLiveKitTcp" `
    -DisplayName "Luminous LiveKit TCP" `
    -Direction Inbound `
    -VMCreatorId $WslCreatorId `
    -Protocol TCP `
    -LocalPorts 7880, 7881 `
    -Action Allow `
    -Enabled True

New-NetFirewallHyperVRule `
    -Name "LuminousLiveKitUdp" `
    -DisplayName "Luminous LiveKit UDP" `
    -Direction Inbound `
    -VMCreatorId $WslCreatorId `
    -Protocol UDP `
    -LocalPorts 7882 `
    -Action Allow `
    -Enabled True

Get-NetFirewallHyperVRule -VMCreatorId $WslCreatorId |
    Where-Object Name -Like "LuminousLiveKit*" |
    Select-Object Name, Enabled, Direction, Protocol, LocalPorts, Action
