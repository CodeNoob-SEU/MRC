# Resets a wedged capture device without rebooting.
#
# A process stuck in an uncancellable kernel I/O of the capture driver
# cannot be killed by taskkill. Disabling and re-enabling the device forces
# the driver to cancel its outstanding I/O, which lets the stuck thread
# return and the pending process termination complete — the zombie
# disappears within seconds.
#
# Usage (run PowerShell as Administrator):
#   .\reset_capture_device_windows.ps1                       # list candidate devices
#   .\reset_capture_device_windows.ps1 -NameLike "*Video*"   # reset matching device(s)
#
#Requires -RunAsAdministrator
param(
  [string]$NameLike = "",
  [switch]$ListOnly
)

$ErrorActionPreference = "Stop"

$classes = @("Camera", "Image", "MEDIA", "USB")
$devices = Get-PnpDevice -PresentOnly | Where-Object { $classes -contains $_.Class }
if ($NameLike) {
  $devices = @($devices | Where-Object { $_.FriendlyName -like $NameLike })
}

if ($ListOnly -or -not $NameLike) {
  Write-Host "候选设备（用 -NameLike '*名称*' 选择要复位的设备）:" -ForegroundColor Cyan
  $devices | Sort-Object Class, FriendlyName | Format-Table Class, Status, FriendlyName -AutoSize
  Write-Host "示例: .\reset_capture_device_windows.ps1 -NameLike '*USB Video*'"
  exit 0
}

if ($devices.Count -eq 0) {
  throw "没有匹配 '$NameLike' 的设备。先不带参数运行本脚本查看设备列表。"
}

foreach ($device in $devices) {
  Write-Host "复位设备: $($device.FriendlyName) [$($device.InstanceId)]" -ForegroundColor Cyan
  Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
  Start-Sleep -Seconds 2
  Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
  Write-Host "  已禁用并重新启用。"
}

Write-Host ""
Write-Host "完成。之前卡死的进程应随驱动复位在几秒内自行消失，" -ForegroundColor Green
Write-Host "确认任务管理器里僵尸进程不在了之后，重新打开软件即可。" -ForegroundColor Green
