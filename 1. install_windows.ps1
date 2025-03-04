# PowerShell 실행 정책 확인 및 우회
if ((Get-ExecutionPolicy) -ne 'Bypass') {
    Write-Host "경고: PowerShell 실행 정책이 스크립트 실행을 제한할 수 있습니다." -ForegroundColor Yellow
    Write-Host "이 스크립트를 실행하려면 다음 명령어로 PowerShell을 실행하세요:" -ForegroundColor Yellow
    Write-Host "powershell -ExecutionPolicy Bypass -File install.ps1" -ForegroundColor Cyan
    
    $continue = Read-Host "계속 진행하시겠습니까? (Y/N)"
    if ($continue -ne "Y") {
        exit
    }
}

# 헤더 출력
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "        자동 자막 생성기 설치 스크립트 (PowerShell)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# 필요 도구 확인 및 상태 리포트
$pythonInstalled = $false
$venvExists = $false
$packagesInstalled = $false
$ffmpegInstalled = $false
$vsToolsInstalled = $false

Write-Host "시스템 환경을 확인하는 중..." -ForegroundColor Yellow

# Python 확인
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+\.\d+\.\d+)") {
        Write-Host "✓ 파이썬 $($Matches[1])이(가) 설치되어 있습니다." -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    Write-Host "✗ 파이썬이 설치되어 있지 않거나 PATH에 등록되지 않았습니다." -ForegroundColor Red
}

# 가상환경 확인
if (Test-Path -Path "venv") {
    Write-Host "✓ 가상환경이 이미 존재합니다." -ForegroundColor Green
    $venvExists = $true
} else {
    Write-Host "✗ 가상환경이 설정되어 있지 않습니다." -ForegroundColor Red
}

# Microsoft Visual C++ 빌드 도구 확인
$vsInstallPath = $null

# VS 설치 위치 확인 방법 1 - vswhere 사용
try {
    if (Test-Path "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe") {
        $vsInstallPath = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    }
} catch {
    # 오류 무시
}

# VS 설치 위치 확인 방법 2 - 일반적인 경로 확인
if (-not $vsInstallPath) {
    $possiblePaths = @(
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2019\BuildTools",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2019\Community"
    )
    
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $vsInstallPath = $path
            break
        }
    }
}

if ($vsInstallPath) {
    Write-Host "✓ Microsoft Visual C++ 빌드 도구가 설치되어 있습니다." -ForegroundColor Green
    $vsToolsInstalled = $true
} else {
    Write-Host "✗ Microsoft Visual C++ 빌드 도구가 설치되어 있지 않습니다." -ForegroundColor Red
}

# FFmpeg 확인
try {
    $ffmpegVersion = ffmpeg -version 2>&1
    if ($ffmpegVersion -match "ffmpeg version") {
        Write-Host "✓ FFmpeg가 설치되어 있습니다." -ForegroundColor Green
        $ffmpegInstalled = $true
    }
} catch {
    Write-Host "✗ FFmpeg가 설치되어 있지 않거나 PATH에 등록되지 않았습니다." -ForegroundColor Red
}

# requirements.txt 확인
if (Test-Path -Path "requirements.txt") {
    Write-Host "✓ requirements.txt 파일이 존재합니다." -ForegroundColor Green
} else {
    Write-Host "✗ requirements.txt 파일이 없습니다. 설치를 진행할 수 없습니다." -ForegroundColor Red
    Read-Host "아무 키나 눌러 종료하세요..."
    exit
}

# 패키지 설치 확인
if (Test-Path -Path "requirements_installed") {
    Write-Host "✓ 필요한 패키지가 이미 설치되어 있습니다." -ForegroundColor Green
    $packagesInstalled = $true
} else {
    Write-Host "? 패키지 설치 상태를 확인할 수 없습니다." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "설치 상태 요약:" -ForegroundColor Yellow
Write-Host "---------------------------------------------------"
if ($pythonInstalled) {
    Write-Host "✓ 파이썬: 설치됨" -ForegroundColor Green
} else {
    Write-Host "✗ 파이썬: 설치되지 않음" -ForegroundColor Red
}

if ($venvExists) {
    Write-Host "✓ 가상환경: 설정됨" -ForegroundColor Green
} else {
    Write-Host "✗ 가상환경: 설정되지 않음" -ForegroundColor Red
}

if ($packagesInstalled) {
    Write-Host "✓ 패키지: 설치됨" -ForegroundColor Green
} else {
    Write-Host "? 패키지: 상태 확인 불가" -ForegroundColor Yellow
}

if ($vsToolsInstalled) {
    Write-Host "✓ Visual C++ 빌드 도구: 설치됨" -ForegroundColor Green
} else {
    Write-Host "✗ Visual C++ 빌드 도구: 설치되지 않음" -ForegroundColor Red
}

if ($ffmpegInstalled) {
    Write-Host "✓ FFmpeg: 설치됨" -ForegroundColor Green
} else {
    Write-Host "✗ FFmpeg: 설치되지 않음" -ForegroundColor Red
}
Write-Host "---------------------------------------------------"
Write-Host ""

# 모든 필요 조건이 충족되었는지 확인
if ($pythonInstalled -and $venvExists -and $packagesInstalled -and $ffmpegInstalled -and $vsToolsInstalled) {
    Write-Host "모든 필요 조건이 이미 설치되어 있습니다!" -ForegroundColor Green
    Write-Host "프로그램을 바로 실행할 수 있습니다." -ForegroundColor Green
    
    $runNow = Read-Host "자막 생성기를 지금 실행하시겠습니까? (Y/N)"
    if ($runNow -eq "Y" -or $runNow -eq "y") {
        Write-Host "2. run_windows.bat 실행 중..." -ForegroundColor Yellow
        & ".\2. run_windows.bat"
        exit
    } else {
        Write-Host "나중에 실행하려면 2. run_windows.bat 파일을 더블클릭하세요." -ForegroundColor Cyan
        Read-Host "아무 키나 눌러 종료하세요..."
        exit
    }
}

# 추가 설치 여부 확인
Write-Host "추가 설치가 필요합니다. 계속 진행하시겠습니까? (Y/N)" -ForegroundColor Yellow
$proceedInstall = Read-Host
if ($proceedInstall -ne "Y" -and $proceedInstall -ne "y") {
    Write-Host "설치를 취소합니다." -ForegroundColor Red
    Read-Host "아무 키나 눌러 종료하세요..."
    exit
}

Write-Host ""

# Python 설치 (필요한 경우)
if (-not $pythonInstalled) {
    Write-Host "파이썬이 설치되어 있지 않습니다." -ForegroundColor Yellow
    $installPython = Read-Host "자동으로 파이썬을 설치하시겠습니까? (Y/N)"
    
    if ($installPython -eq "Y" -or $installPython -eq "y") {
        Write-Host "파이썬을 다운로드하고 설치합니다..." -ForegroundColor Yellow
        
        # 임시 디렉토리 생성
        if (-not (Test-Path -Path "temp")) {
            New-Item -Path "temp" -ItemType Directory | Out-Null
        }
        
        # Python 설치 프로그램 다운로드
        Write-Host "파이썬 설치 프로그램 다운로드 중..." -ForegroundColor Yellow
        try {
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe" -OutFile "temp\python_installer.exe"
        } catch {
            Write-Host "파이썬 설치 프로그램 다운로드에 실패했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://www.python.org/downloads/" -ForegroundColor Red
            Read-Host "아무 키나 눌러 종료하세요..."
            exit
        }
        
        Write-Host "파이썬 설치 중... (잠시 기다려 주세요)" -ForegroundColor Yellow
        # 파이썬 설치 (자동 모드, PATH에 추가, pip 설치)
        Start-Process -FilePath "temp\python_installer.exe" -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "Include_pip=1" -Wait
        
        Write-Host "파이썬 설치가 완료되었습니다!" -ForegroundColor Green
        Write-Host "PowerShell을 재시작하여 환경 변수를 새로고침해야 합니다." -ForegroundColor Yellow
        Write-Host "PowerShell을 재시작한 후 이 스크립트를 다시 실행해주세요." -ForegroundColor Yellow
        Read-Host "아무 키나 눌러 종료하세요..."
        exit
    } else {
        Write-Host "파이썬 설치를 건너뜁니다." -ForegroundColor Yellow
        Write-Host "파이썬이 필요합니다. 수동으로 설치한 후 이 스크립트를 다시 실행해주세요." -ForegroundColor Yellow
        Write-Host "https://www.python.org/downloads/" -ForegroundColor Cyan
        Read-Host "아무 키나 눌러 종료하세요..."
        exit
    }
}

# Microsoft Visual C++ 빌드 도구 설치 (필요한 경우)
if (-not $vsToolsInstalled) {
    Write-Host "Microsoft Visual C++ 빌드 도구가 설치되어 있지 않습니다." -ForegroundColor Yellow
    $installVSTools = Read-Host "Microsoft Visual C++ 빌드 도구를 자동으로 설치하시겠습니까? (Y/N)"
    
    if ($installVSTools -eq "Y" -or $installVSTools -eq "y") {
        Write-Host "Microsoft Visual C++ 빌드 도구를 다운로드하고 설치합니다..." -ForegroundColor Yellow
        
        # 임시 디렉토리 생성
        if (-not (Test-Path -Path "temp")) {
            New-Item -Path "temp" -ItemType Directory | Out-Null
        }
        
        # Visual Studio 설치 프로그램 다운로드
        Write-Host "Visual Studio 설치 프로그램 다운로드 중..." -ForegroundColor Yellow
        $vsInstallerUrl = "https://aka.ms/vs/17/release/vs_buildtools.exe"
        try {
            Invoke-WebRequest -Uri $vsInstallerUrl -OutFile "temp\vs_buildtools.exe"
        } catch {
            Write-Host "Visual Studio 설치 프로그램 다운로드에 실패했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Red
            
            $proceedWithoutVSTools = Read-Host "Visual C++ 빌드 도구 없이 계속 진행하시겠습니까? (webrtcvad 모듈을 사용할 수 없음) (Y/N)"
            if ($proceedWithoutVSTools -ne "Y" -and $proceedWithoutVSTools -ne "y") {
                Read-Host "아무 키나 눌러 종료하세요..."
                exit
            }
        }
        
        # 설치 진행
        if (Test-Path "temp\vs_buildtools.exe") {
            Write-Host "Visual Studio 빌드 도구 설치 중... (새 창이 열릴 수 있습니다)" -ForegroundColor Yellow
            Write-Host "설치 중에는 'C++을 사용한 데스크톱 개발' 워크로드를 선택해주세요." -ForegroundColor Yellow
            
            # Visual Studio Build Tools 설치 (C++ 빌드 도구)
            Start-Process -FilePath "temp\vs_buildtools.exe" -ArgumentList "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --wait" -Wait
            
            Write-Host "Visual Studio 빌드 도구 설치가 완료되었습니다." -ForegroundColor Green
            $vsToolsInstalled = $true
        }
    } else {
        Write-Host "Visual C++ 빌드 도구 설치를 건너뜁니다." -ForegroundColor Yellow
        Write-Host "webrtcvad 모듈을 사용하려면 Visual C++ 빌드 도구가 필요합니다." -ForegroundColor Yellow
        
        $proceedWithoutVSTools = Read-Host "Visual C++ 빌드 도구 없이 계속 진행하시겠습니까? (webrtcvad 모듈을 사용할 수 없음) (Y/N)"
        if ($proceedWithoutVSTools -ne "Y" -and $proceedWithoutVSTools -ne "y") {
            Read-Host "아무 키나 눌러 종료하세요..."
            exit
        }
    }
}

# 가상환경 생성 (필요한 경우)
if (-not $venvExists) {
    Write-Host "가상환경을 생성합니다..." -ForegroundColor Yellow
    try {
        & python -m venv venv
        Write-Host "가상환경이 성공적으로 생성되었습니다." -ForegroundColor Green
    } catch {
        Write-Host "가상환경 생성에 실패했습니다." -ForegroundColor Red
        Read-Host "아무 키나 눌러 종료하세요..."
        exit
    }
}

# 가상환경 활성화
Write-Host "가상환경을 활성화합니다..." -ForegroundColor Yellow
try {
    & .\venv\Scripts\Activate.ps1
    Write-Host "가상환경이 활성화되었습니다." -ForegroundColor Green
} catch {
    Write-Host "가상환경 활성화에 실패했습니다." -ForegroundColor Red
    Write-Host "보안 설정으로 인해 스크립트 실행이 제한될 수 있습니다." -ForegroundColor Yellow
    Write-Host "다음 명령어로 실행 정책을 변경해보세요: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" -ForegroundColor Cyan
    
    # 대안으로 배치 파일을 통해 활성화 시도
    Write-Host "배치 파일을 통해 가상환경 활성화를 시도합니다..." -ForegroundColor Yellow
    & cmd /c "venv\Scripts\activate.bat && pip install --upgrade pip && pip install -r requirements.txt && echo. > requirements_installed"
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "가상환경 활성화에 실패했습니다." -ForegroundColor Red
        Read-Host "아무 키나 눌러 종료하세요..."
        exit
    }
    
    Write-Host "배치 파일을 통해 가상환경을 활성화했습니다." -ForegroundColor Green
    $packagesInstalled = $true
}

# pip 업그레이드 및 필요한 패키지 설치
if (-not $packagesInstalled) {
    # pip 업그레이드
    Write-Host "pip를 최신 버전으로 업그레이드합니다..." -ForegroundColor Yellow
    try {
        & python -m pip install --upgrade pip
    } catch {
        Write-Host "pip 업그레이드에 실패했습니다." -ForegroundColor Red
    }
    
    # 필요한 패키지 설치
    Write-Host "필요한 패키지를 설치합니다..." -ForegroundColor Yellow
    
    # webrtcvad 설치 처리
    if ($vsToolsInstalled) {
        # Visual C++ 빌드 도구가 있는 경우 모든 패키지 설치
        try {
            & pip install -r requirements.txt
            if ($LASTEXITCODE -eq 0) {
                Write-Host "모든 패키지 설치가 완료되었습니다." -ForegroundColor Green
                "All packages installed on $(Get-Date)" | Out-File -FilePath "requirements_installed"
            } else {
                Write-Host "패키지 설치에 실패했습니다." -ForegroundColor Red
                Read-Host "아무 키나 눌러 종료하세요..."
                exit
            }
        } catch {
            Write-Host "패키지 설치에 실패했습니다." -ForegroundColor Red
            Read-Host "아무 키나 눌러 종료하세요..."
            exit
        }
    } else {
        # Visual C++ 빌드 도구가 없는 경우 webrtcvad를 제외하고 설치
        Write-Host "Visual C++ 빌드 도구가 없어 webrtcvad를 제외하고 설치합니다." -ForegroundColor Yellow
        try {
            # requirements.txt 파일에서 webrtcvad를 제외한 패키지 목록 가져오기
            $packages = Get-Content -Path "requirements.txt" | Where-Object { $_ -notmatch "webrtcvad" }
            
            # 패키지 설치
            foreach ($package in $packages) {
                if ($package.Trim() -ne "") {
                    Write-Host "패키지 설치 중: $package" -ForegroundColor Yellow
                    & pip install $package
                }
            }
            
            Write-Host "webrtcvad를 제외한 패키지 설치가 완료되었습니다." -ForegroundColor Green
            "Packages installed without webrtcvad on $(Get-Date)" | Out-File -FilePath "requirements_installed"
            
            Write-Host "주의: VAD(Voice Activity Detection) 기능을 사용할 수 없습니다." -ForegroundColor Yellow
            Write-Host "앱 실행 시 VAD 옵션을 비활성화해주세요." -ForegroundColor Yellow
        } catch {
            Write-Host "패키지 설치에 실패했습니다." -ForegroundColor Red
            Read-Host "아무 키나 눌러 종료하세요..."
            exit
        }
    }
}

# FFmpeg 설치 (필요한 경우)
if (-not $ffmpegInstalled) {
    Write-Host "FFmpeg가 설치되어 있지 않습니다." -ForegroundColor Yellow
    $installFFmpeg = Read-Host "FFmpeg를 자동으로 설치하시겠습니까? (Y/N)"
    
    if ($installFFmpeg -eq "Y" -or $installFFmpeg -eq "y") {
        Write-Host "FFmpeg를 다운로드하고 설치합니다..." -ForegroundColor Yellow
        
        # 임시 디렉토리 생성
        if (-not (Test-Path -Path "temp")) {
            New-Item -Path "temp" -ItemType Directory | Out-Null
        }
        
        # FFmpeg 다운로드
        try {
            Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile "temp\ffmpeg.zip"
        } catch {
            Write-Host "FFmpeg 다운로드에 실패했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://ffmpeg.org/download.html" -ForegroundColor Red
        }
        
        # FFmpeg 압축 해제
        Write-Host "FFmpeg 압축 해제 중..." -ForegroundColor Yellow
        try {
            Expand-Archive -Path "temp\ffmpeg.zip" -DestinationPath "temp\ffmpeg" -Force
            
            # FFmpeg bin 폴더 경로
            $ffmpegDir = (Get-ChildItem -Path "temp\ffmpeg" -Directory)[0].FullName
            $ffmpegBin = Join-Path -Path $ffmpegDir -ChildPath "bin"
            
            # 현재 세션의 PATH에 FFmpeg 추가
            Write-Host "FFmpeg를 현재 세션의 PATH에 추가합니다..." -ForegroundColor Yellow
            $env:Path = "$((Get-Location).Path)\$ffmpegBin;$env:Path"
            
            # 시스템 PATH에 FFmpeg 추가
            $addToPath = Read-Host "FFmpeg를 시스템 PATH에 추가할까요? (Y/N)"
            if ($addToPath -eq "Y" -or $addToPath -eq "y") {
                Write-Host "FFmpeg를 시스템 PATH에 추가합니다..." -ForegroundColor Yellow
                try {
                    [Environment]::SetEnvironmentVariable("Path", "$((Get-Location).Path)\$ffmpegBin;$([Environment]::GetEnvironmentVariable('Path', 'Machine'))", "Machine")
                    Write-Host "FFmpeg가 시스템 PATH에 추가되었습니다." -ForegroundColor Green
                } catch {
                    Write-Host "시스템 PATH 업데이트에 실패했습니다. 관리자 권한이 필요할 수 있습니다." -ForegroundColor Red
                }
            }
            
            Write-Host "FFmpeg 설치가 완료되었습니다!" -ForegroundColor Green
        } catch {
            Write-Host "FFmpeg 압축 해제 및 설치에 실패했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://ffmpeg.org/download.html" -ForegroundColor Red
        }
    } else {
        Write-Host "FFmpeg 설치를 건너뜁니다." -ForegroundColor Yellow
        Write-Host "일부 비디오 파일 처리 기능이 제한될 수 있습니다." -ForegroundColor Yellow
    }
}

# 앱 실행
Write-Host "" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host "            설치가 완료되었습니다!" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""

$runApp = Read-Host "이제 자막 생성기를 실행하시겠습니까? (Y/N)"
if ($runApp -eq "Y" -or $runApp -eq "y") {
    Write-Host "자막 생성기를 실행합니다..." -ForegroundColor Yellow
    & ".\2. run_windows.bat"
} else {
    Write-Host "나중에 실행하려면 2. run_windows.bat 파일을 더블클릭하세요." -ForegroundColor Cyan
}

# 임시 파일 정리
if (Test-Path -Path "temp") {
    $cleanup = Read-Host "임시 파일을 정리하시겠습니까? (Y/N)"
    if ($cleanup -eq "Y" -or $cleanup -eq "y") {
        Write-Host "임시 파일을 정리합니다..." -ForegroundColor Yellow
        Remove-Item -Path "temp" -Recurse -Force
    }
}

Write-Host "설치 과정이 완료되었습니다." -ForegroundColor Green
Read-Host "아무 키나 눌러 종료하세요..."