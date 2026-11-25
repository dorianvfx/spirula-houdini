@echo off
set "HOUDINI_EXE=C:\Program Files\Side Effects Software\Houdini 22.0.368\bin\houdinifx.exe"
if not exist "%HOUDINI_EXE%" (
 echo Houdini 22.0.368 est introuvable.
 pause
 exit /b 1
)
start "" "%HOUDINI_EXE%" waitforui "%~dp0scripts\open_pipeline.py"
