@echo off
rem Startet das lokale Mandantenportal und oeffnet den Browser.
rem Doppelklick genuegt. Beenden: dieses Fenster schliessen oder Strg+C.
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python -m credit_readiness serve --open
if errorlevel 1 (
  echo.
  echo Das Portal konnte nicht gestartet werden. Ist Python installiert
  echo und laeuft das Portal vielleicht schon in einem anderen Fenster?
)
pause
