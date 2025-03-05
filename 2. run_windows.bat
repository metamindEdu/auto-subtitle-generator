@echo off
chcp 65001 > nul

echo ===================================================
echo       자동 자막 생성기를 시작합니다...
echo ===================================================

:: 가상환경 활성화
call venv\Scripts\activate.bat

:: Streamlit 앱 실행
echo 자막 생성기를 실행합니다...
echo 잠시 후 브라우저가 자동으로 열립니다.
echo 브라우저가 열리지 않으면 http://localhost:8501 로 접속하세요.

:: 추가 매개변수가 있으면 전달
if "%*"=="" (
    streamlit run app.py
) else (
    streamlit run app.py %*
)

pause
