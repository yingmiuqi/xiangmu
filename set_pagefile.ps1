# Run as admin: pin pagefile to D: 8192-16384 MB and clear force-C: switches
$ErrorActionPreference = 'Continue'
$out = @()
$key = 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management'

$out += '--- reg add PagingFiles ---'
$out += (reg add $key /v PagingFiles /t REG_MULTI_SZ /d "D:\pagefile.sys 8192 16384" /f 2>&1 | Out-String).Trim()
$out += '--- reg add TempPageFile ---'
$out += (reg add $key /v TempPageFile /t REG_DWORD /d 0 /f 2>&1 | Out-String).Trim()
$out += '--- reg add PagefileOnOsVolume ---'
$out += (reg add $key /v PagefileOnOsVolume /t REG_DWORD /d 0 /f 2>&1 | Out-String).Trim()
$out += '--- wmic auto-manage ---'
$out += (wmic computersystem set AutomaticManagedPagefile=False 2>&1 | Out-String).Trim()
$out += '--- wmic cleanup ---'
wmic pagefileset where "name='C:\\pagefile.sys'" delete 2>&1 | Out-Null
wmic pagefileset where "name='D:\\pagefile.sys'" delete 2>&1 | Out-Null
$out += '--- wmic create D: ---'
$out += (wmic pagefileset create name="D:\pagefile.sys" 2>&1 | Out-String).Trim()
$out += '--- wmic set sizes ---'
$out += (wmic pagefileset where "name='D:\\pagefile.sys'" set InitialSize=8192,MaximumSize=16384 2>&1 | Out-String).Trim()

$out -join "`r`n" | Out-File -FilePath 'D:\pagefile_set_result.txt' -Encoding utf8
