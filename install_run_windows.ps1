# 관리자 권한으로 자기 자신을 다시 실행하는 스크립트
param([switch]$Elevated, [string]$OriginalPath)

function Test-Admin {
    $currentUser = New-Object Security.Principal.WindowsPrincipal $([Security.Principal.WindowsIdentity]::GetCurrent())
    $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Microsoft Visual C++ Build Tools 설치 (webrtcvad 모듈 설치 전에 필요)
function Install-BuildTools {
    Write-Host "Microsoft Visual C++ Build Tools 설치가 필요합니다 (webrtcvad 모듈 설치를 위해)" -ForegroundColor Yellow
    $installBuildTools = Read-Host "Visual C++ Build Tools를 자동으로 설치하시겠습니까? (y/n)"
    
    if ($installBuildTools -eq "y" -or $installBuildTools -eq "Y") {
        Write-Host "Visual C++ Build Tools 다운로드 중..." -ForegroundColor Yellow
        
        # 임시 디렉토리 생성
        if (-not (Test-Path -Path "temp")) {
            New-Item -Path "temp" -ItemType Directory | Out-Null
        }
        
        # Build Tools 다운로드
        try {
            Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vs_BuildTools.exe" -OutFile "temp\vs_BuildTools.exe"
        } catch {
            Write-Host "Visual C++ Build Tools 다운로드에 실패했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Red
            return $false
        }
        
        # 설치 실행
        Write-Host "Visual C++ Build Tools 설치 중... (이 과정은 다소 시간이 걸릴 수 있습니다)" -ForegroundColor Yellow
        try {
            # C++ 빌드 도구 설치 (자동 모드)
            Start-Process -FilePath "temp\vs_BuildTools.exe" -ArgumentList "--quiet", "--wait", "--norestart", "--nocache", `
                "--installPath `"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`"", `
                "--add Microsoft.VisualStudio.Workload.VCTools", `
                "--includeRecommended" -Wait
            
            Write-Host "Visual C++ Build Tools 설치가 완료되었습니다!" -ForegroundColor Green
            return $true
        } catch {
            Write-Host "Visual C++ Build Tools 설치 중 오류가 발생했습니다." -ForegroundColor Red
            Write-Host "수동으로 설치해주세요: https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "Visual C++ Build Tools 설치를 건너뜁니다." -ForegroundColor Yellow
        Write-Host "webrtcvad 모듈 설치 시 오류가 발생할 수 있으며, VAD 기능을 사용할 수 없게 됩니다." -ForegroundColor Yellow
        return $false
    }
}

# 관리자 권한으로 실행 시 원래 디렉토리로 이동
if ($OriginalPath) {
    try {
        Set-Location -Path $OriginalPath
        Write-Host "작업 디렉토리를 '$OriginalPath'로 설정했습니다." -ForegroundColor Green
    } catch {
        Write-Host "작업 디렉토리 변경 중 오류가 발생했습니다: $_" -ForegroundColor Red
        Write-Host "스크립트가 있는 디렉토리에서 실행하는 것이 좋습니다." -ForegroundColor Yellow
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
$installationCompleted = $false

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

if ($ffmpegInstalled) {
    Write-Host "✓ FFmpeg: 설치됨" -ForegroundColor Green
} else {
    Write-Host "✗ FFmpeg: 설치되지 않음" -ForegroundColor Red
}

Write-Host "---------------------------------------------------"
Write-Host ""

# 모든 필요 조건이 충족되었는지 확인
if ($pythonInstalled -and $venvExists -and $packagesInstalled -and $ffmpegInstalled) {
    $installationCompleted = $true
    Write-Host "모든 필요 조건이 이미 설치되어 있습니다!" -ForegroundColor Green
    Write-Host "프로그램을 바로 실행할 수 있습니다." -ForegroundColor Green
    
    # 별도의 창에서 직접 파이썬으로 streamlit 모듈 실행
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd `"$((Get-Location).Path)`" && call venv\Scripts\activate.bat && echo 자막 생성기를 실행하는 중입니다... && python -m streamlit run app.py" -PassThru
    
    Write-Host "프로그램이 별도의 창에서 실행 중입니다." -ForegroundColor Green
    Write-Host "스트림릿이 웹 브라우저에서 열릴 때까지 기다려 주세요." -ForegroundColor Yellow
    Write-Host "이 창은 닫으셔도 됩니다." -ForegroundColor Yellow
}

# 설치가 필요하면 관리자 권한 확인
if (-not $installationCompleted) {
    # 관리자 권한 필요 - 권한 확인 및 재실행
    if ((Test-Admin) -eq $false) {
        if ($elevated) {
            Write-Host "관리자 권한으로 실행을 시도했으나 실패했습니다." -ForegroundColor Red
        } else {
            Write-Host "설치를 위해 관리자 권한으로 스크립트를 다시 실행합니다..." -ForegroundColor Yellow
            
            # 현재 스크립트의 전체 경로 가져오기
            $scriptPath = $MyInvocation.MyCommand.Definition
            # 현재 작업 디렉토리 경로 저장
            $currentPath = (Get-Location).Path
            
            # 관리자 권한으로 동일한 스크립트 실행 (현재 경로 전달)
            Start-Process PowerShell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Elevated -OriginalPath `"$currentPath`"" -Verb RunAs
        }
        exit
    }

    # Python 설치 (필요한 경우)
    if (-not $pythonInstalled) {
        Write-Host "파이썬이 설치되어 있지 않습니다." -ForegroundColor Yellow
        Write-Host "파이썬을 자동으로 설치합니다..." -ForegroundColor Yellow
        
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
        Write-Host "환경 변수를 갱신하고 스크립트를 다시 실행합니다..." -ForegroundColor Yellow
        
        # 환경 변수 갱신
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        # 현재 스크립트 경로와 작업 디렉토리 가져오기
        $scriptPath = $MyInvocation.MyCommand.Definition
        $currentPath = (Get-Location).Path
        
        # 스크립트 재실행
        Start-Process PowerShell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Elevated -OriginalPath `"$currentPath`"" -Verb RunAs -Wait
        
        # 현재 프로세스 종료
        exit
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
        Write-Host "배치 파일을 통해 가상환경 활성화를 시도합니다..." -ForegroundColor Yellow
        & cmd /c "venv\Scripts\activate.bat && pip install --upgrade pip && pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121 && pip install --no-cache-dir -r requirements.txt && echo. > requirements_installed"
        
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
        # Visual C++ Build Tools 설치 확인 (webrtcvad에 필요)
        $buildToolsInstalled = Install-BuildTools
        
        # pip 업그레이드
        Write-Host "pip를 최신 버전으로 업그레이드합니다..." -ForegroundColor Yellow
        try {
            & python -m pip install --upgrade pip
        } catch {
            Write-Host "pip 업그레이드에 실패했습니다." -ForegroundColor Red
        }
        
        # 필요한 패키지 설치
        Write-Host "필요한 패키지를 설치합니다..." -ForegroundColor Yellow
        try {
            # webrtcvad 설치 여부 결정
            $installCommand = ""
            if ($buildToolsInstalled) {
                # 모든 패키지 설치 (webrtcvad 포함)
                $installCommand = "pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121 && pip install -r requirements.txt"
            } else {
                # webrtcvad를 제외하고 설치
                $tempReqFile = "temp_requirements.txt"
                Get-Content -Path "requirements.txt" | Where-Object { $_ -notmatch "webrtcvad" } | Set-Content -Path $tempReqFile
                $installCommand = "pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121 && pip install -r $tempReqFile"
            }
            
            & cmd /c "$installCommand"
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "패키지 설치가 완료되었습니다." -ForegroundColor Green
                "Packages installed on $(Get-Date)" | Out-File -FilePath "requirements_installed"
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
    }

    # FFmpeg 설치 (필요한 경우)
    if (-not $ffmpegInstalled) {
        Write-Host "FFmpeg가 설치되어 있지 않습니다. 자동으로 설치합니다..." -ForegroundColor Yellow
        
        # Chocolatey 설치 확인
        if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
            Write-Host "Chocolatey가 설치되어 있지 않습니다. 설치를 시작합니다..." -ForegroundColor Yellow
            
            try {
                # Chocolatey 설치
                Write-Host "Chocolatey 설치 중..." -ForegroundColor Yellow
                Set-ExecutionPolicy Bypass -Scope Process -Force
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
                
                # 설치 확인
                if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
                    Write-Host "Chocolatey 설치에 실패했습니다. 대체 방식으로 FFmpeg 설치를 시도합니다." -ForegroundColor Red
                    # 직접 다운로드 방식으로 전환
                    $installMethod = "direct"
                } else {
                    Write-Host "Chocolatey 설치가 완료되었습니다." -ForegroundColor Green
                    $installMethod = "choco"
                }
            }
            catch {
                Write-Host "Chocolatey 설치 중 오류가 발생했습니다: $_" -ForegroundColor Red
                Write-Host "대체 방식으로 FFmpeg 설치를 시도합니다." -ForegroundColor Yellow
                $installMethod = "direct"
            }
        } else {
            Write-Host "Chocolatey가 이미 설치되어 있습니다." -ForegroundColor Green
            $installMethod = "choco"
        }
        
        # Chocolatey로 FFmpeg 설치
        if ($installMethod -eq "choco") {
            try {
                Write-Host "Chocolatey를 통해 FFmpeg를 설치합니다..." -ForegroundColor Yellow
                choco install ffmpeg -y
                
                # 환경 변수 갱신
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
                
                # 설치 확인
                if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
                    $ffmpegVersion = (ffmpeg -version 2>&1) | Select-Object -First 1
                    Write-Host "FFmpeg 설치가 완료되었습니다!" -ForegroundColor Green
                    Write-Host "설치된 버전: $ffmpegVersion" -ForegroundColor Green
                    $ffmpegInstalled = $true
                } else {
                    Write-Host "FFmpeg가 설치되었지만 PATH에 등록되지 않았습니다. 대체 방식으로 설치를 시도합니다." -ForegroundColor Yellow
                    $installMethod = "direct"
                }
            }
            catch {
                Write-Host "Chocolatey를 통한 FFmpeg 설치 중 오류가 발생했습니다. 대체 방식으로 설치를 시도합니다." -ForegroundColor Red
                $installMethod = "direct"
            }
        }
        
        # 직접 다운로드 방식으로 FFmpeg 설치
        if ($installMethod -eq "direct") {
            Write-Host "FFmpeg를 직접 다운로드하여 설치합니다..." -ForegroundColor Yellow
            
            # 임시 디렉토리 생성
            if (-not (Test-Path -Path "temp")) {
                New-Item -Path "temp" -ItemType Directory | Out-Null
            }
            
            # FFmpeg 다운로드
            try {
                Write-Host "FFmpeg 다운로드 중..." -ForegroundColor Yellow
                Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile "temp\ffmpeg.zip"
            } catch {
                Write-Host "FFmpeg 다운로드에 실패했습니다." -ForegroundColor Red
                Write-Host "수동으로 설치해주세요: https://ffmpeg.org/download.html" -ForegroundColor Red
                Read-Host "아무 키나 눌러 종료하세요..."
                exit
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
                Write-Host "FFmpeg를 시스템 PATH에 추가합니다..." -ForegroundColor Yellow
                try {
                    [Environment]::SetEnvironmentVariable("Path", "$((Get-Location).Path)\$ffmpegBin;$([Environment]::GetEnvironmentVariable('Path', 'Machine'))", "Machine")
                    Write-Host "FFmpeg가 시스템 PATH에 추가되었습니다." -ForegroundColor Green
                } catch {
                    Write-Host "시스템 PATH 업데이트에 실패했습니다. 현재 세션에서만 FFmpeg를 사용할 수 있습니다." -ForegroundColor Red
                }
                
                # 설치 확인
                if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
                    Write-Host "FFmpeg 설치가 완료되었습니다!" -ForegroundColor Green
                    $ffmpegInstalled = $true
                } else {
                    Write-Host "FFmpeg 설치 후에도 PATH에 등록되지 않았습니다." -ForegroundColor Yellow
                    Write-Host "PowerShell을 재시작하거나 컴퓨터를 재부팅한 후 FFmpeg를 사용할 수 있습니다." -ForegroundColor Yellow
                }
            } catch {
                Write-Host "FFmpeg 압축 해제 및 설치에 실패했습니다." -ForegroundColor Red
                Write-Host "수동으로 설치해주세요: https://ffmpeg.org/download.html" -ForegroundColor Red
                Read-Host "아무 키나 눌러 종료하세요..."
                exit
            }
        }
    }

    # 앱 실행
    Write-Host "" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host "            설치가 완료되었습니다!" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "자막 생성기를 실행합니다..." -ForegroundColor Yellow

    # 별도의 창에서 직접 파이썬으로 streamlit 모듈 실행
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd `"$((Get-Location).Path)`" && call venv\Scripts\activate.bat && echo 자막 생성기를 실행하는 중입니다... && python -m streamlit run app.py" -PassThru

    # 임시 파일 정리
    if (Test-Path -Path "temp") {
        Write-Host "임시 파일을 정리합니다..." -ForegroundColor Yellow
        try {
            Remove-Item -Path "temp" -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "임시 파일 정리가 완료되었습니다." -ForegroundColor Green
        } catch {
            Write-Host "일부 임시 파일을 삭제할 수 없습니다. 나중에 수동으로 temp 폴더를 삭제해주세요." -ForegroundColor Yellow
        }
    }

    Write-Host "설치 과정이 완료되었습니다." -ForegroundColor Green
    Write-Host "프로그램이 별도의 창에서 실행 중입니다." -ForegroundColor Green
    Write-Host "스트림릿이 웹 브라우저에서 열릴 때까지 기다려 주세요." -ForegroundColor Yellow
    Write-Host "이 창은 닫으셔도 됩니다." -ForegroundColor Yellow

    # 사용자가 직접 창을 닫도록 함
    Read-Host "아무 키나 눌러 종료하세요..."
}