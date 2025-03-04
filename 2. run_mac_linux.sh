#!/bin/bash

echo "==================================================="
echo "       자동 자막 생성기를 시작합니다..."
echo "==================================================="

# 가상환경 활성화
source venv/bin/activate

# 웹 브라우저 열기 (백그라운드로)
if [[ "$OSTYPE" == "darwin"* ]]; then
    (sleep 3 && open http://localhost:8501) &
elif command -v xdg-open &> /dev/null; then
    (sleep 3 && xdg-open http://localhost:8501) &
fi

# Streamlit 앱 실행
echo "자막 생성기를 실행합니다..."
echo "잠시 후 브라우저가 자동으로 열립니다."
echo "브라우저가 열리지 않으면 http://localhost:8501 로 접속하세요."
echo ""
echo "종료하려면 Ctrl+C를 누르세요."
streamlit run app.py
