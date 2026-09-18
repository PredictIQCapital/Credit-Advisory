@echo off
rem Startet Website und Portal mit fiktiven Demo-Unternehmen und oeffnet den Browser.
rem Demo-Zugaenge stehen auf der Anmeldeseite. Beenden: Fenster schliessen oder Strg+C.
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python -m credit_readiness serve --demo --open --port 8766
if errorlevel 1 (
  echo.
  echo Start fehlgeschlagen. Laeuft die Demo schon in einem anderen Fenster?
)
pause
