@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0EMPARELHAR_AGENDA_TODAS_APPS.ps1"
if errorlevel 1 (
  echo.
  echo Ocorreu um erro. Le a mensagem acima antes de fechar esta janela.
  pause
)
endlocal
