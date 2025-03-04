#!/bin/bash

echo "==================================================="
echo "       자동 자막 생성기 자동 설치 스크립트"
echo "==================================================="
echo ""

# 파이썬 설치 확인
if ! command -v python3 &> /dev/null; then
    echo "파이썬이 설치되어 있지 않습니다."
    
    # OS 확인
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        echo "macOS에서는 다음 명령으로 설치할 수 있습니다:"
        echo "  brew install python"
        echo "또는 https://www.python.org/downloads/ 에서 다운로드"
        
        read -p "Homebrew를 사용하여 파이썬을 자동으로 설치할까요? (y/n): " INSTALL_PYTHON
        if [[ "$INSTALL_PYTHON" == "y" || "$INSTALL_PYTHON" == "Y" ]]; then
            # Homebrew 확인
            if ! command -v brew &> /dev/null; then
                echo "Homebrew가 설치되어 있지 않습니다. 설치합니다..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            
            # Python 설치
            brew install python
        else
            echo "파이썬을 수동으로 설치한 후 이 스크립트를 다시 실행해주세요."
            exit 1
        fi
    else
        # Linux (Debian/Ubuntu 기준)
        echo "Linux에서는 다음 명령으로 설치할 수 있습니다:"
        echo "  sudo apt-get update && sudo apt-get install python3 python3-pip python3-venv"
        echo "(Ubuntu/Debian 기준)"
        
        read -p "자동으로 파이썬을 설치할까요? (y/n): " INSTALL_PYTHON
        if [[ "$INSTALL_PYTHON" == "y" || "$INSTALL_PYTHON" == "Y" ]]; then
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv
        else
            echo "파이썬을 수동으로 설치한 후 이 스크립트를 다시 실행해주세요."
            exit 1
        fi
    fi
fi

# 파이썬 버전 확인
PYTHON_VERSION=$(python3 --version 2>&1)
echo "감지된 파이썬 버전: $PYTHON_VERSION"

# 가상환경 확인 및 생성
if [ ! -d "venv" ]; then
    echo "가상환경을 생성합니다..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "가상환경 생성에 실패했습니다."
        exit 1
    fi
fi

# 가상환경 활성화
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "가상환경 활성화에 실패했습니다."
    exit 1
fi

# pip 업그레이드
echo "pip를 최신 버전으로 업그레이드합니다..."
pip install --upgrade pip

# 필요한 패키지 설치
if [ ! -f "requirements_installed" ]; then
    echo "필요한 패키지를 설치합니다..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "패키지 설치에 실패했습니다."
        exit 1
    fi
    echo "패키지 설치가 완료되었습니다."
    touch requirements_installed
fi

# FFmpeg 확인
if ! command -v ffmpeg &> /dev/null; then
    echo "FFmpeg가 설치되어 있지 않습니다."
    
    read -p "FFmpeg를 자동으로 설치할까요? (y/n): " INSTALL_FFMPEG
    if [[ "$INSTALL_FFMPEG" == "y" || "$INSTALL_FFMPEG" == "Y" ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install ffmpeg
            else
                echo "Homebrew가 설치되어 있지 않습니다."
                echo "FFmpeg를 수동으로 설치해주세요: https://ffmpeg.org/download.html"
            fi
        else
            # Linux (Debian/Ubuntu 기준)
            sudo apt-get update
            sudo apt-get install -y ffmpeg
        fi
    else
        echo "FFmpeg 설치를 건너뜁니다."
        echo "일부 비디오 파일 처리 기능이 제한될 수 있습니다."
    fi
fi

# 실행 권한 확인 및 부여
if [ -f "2. run_mac_linux.sh" ]; then
    if [ ! -x "2. run_mac_linux.sh" ]; then
        echo "2. run_mac_linux.sh에 실행 권한을 부여합니다..."
        chmod +x "2. run_mac_linux.sh"
    fi
fi

# 앱 실행
echo "==================================================="
echo "           설치가 완료되었습니다!"
echo "==================================================="
echo ""
read -p "이제 자막 생성기를 실행하시겠습니까? (y/n): " RUN_APP

if [[ "$RUN_APP" == "y" || "$RUN_APP" == "Y" ]]; then
    echo "자막 생성기를 실행합니다..."
    ./2. run_mac_linux.sh
else
    echo "나중에 실행하려면 ./2. run_mac_linux.sh 명령을 사용하세요."
fi

exit 0

