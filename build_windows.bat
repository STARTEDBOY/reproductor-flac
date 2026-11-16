@echo off
REM Genera un build portable de Windows con PyInstaller.
REM Requisitos: Python 3 y mpv instalados (mpv debe estar en PATH para ejecutarlo).
setlocal
cd /d "%~dp0"

py -3 -m pip install --upgrade pip
py -3 -m pip install PySide6 mutagen numpy pyinstaller
if errorlevel 1 goto :err

py -3 -m PyInstaller --noconfirm --clean reproductor-flac.spec
if errorlevel 1 goto :err

echo.
echo Listo. Carpeta portable: dist\ReproductorFLAC
echo Comparte la carpeta completa. El equipo destino necesita mpv en el PATH.
echo Puedes comprimirla en un .zip para enviarla.
exit /b 0

:err
echo.
echo Error durante la compilacion.
exit /b 1
