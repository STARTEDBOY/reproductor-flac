@echo off
REM Genera un build portable de Windows con PyInstaller, incluyendo mpv.
REM Requisitos: Python 3. Descarga mpv automaticamente si no esta en .\mpv\
setlocal
cd /d "%~dp0"

if not exist "mpv\mpv.exe" (
  echo Descargando mpv portable...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $url='https://downloads.sourceforge.net/project/mpv-player-windows/release/mpv-0.39.0-x86_64.7z'; $out='mpv_download.7z'; Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; New-Item -ItemType Directory -Force -Path mpv | Out-Null; $seven=$null; foreach($p in @('7z','7z.exe','C:\\Program Files\\7-Zip\\7z.exe','C:\\Program Files (x86)\\7-Zip\\7z.exe')){ if(Get-Command $p -ErrorAction SilentlyContinue){ $seven=(Get-Command $p).Source; break }; if(Test-Path $p){ $seven=$p; break } }; if($seven){ & $seven x -y $out -ompv_extract | Out-Null } else { tar -xf $out -C .; if(Test-Path 'mpv_extract'){} else { New-Item -ItemType Directory -Force -Path mpv_extract | Out-Null; tar -xf $out -C mpv_extract } }; $exe=Get-ChildItem -Path mpv_extract -Recurse -Filter mpv.exe | Select-Object -First 1; if(-not $exe){ throw 'No se encontro mpv.exe en el archivo descargado' }; $root=$exe.DirectoryName; Copy-Item (Join-Path $root 'mpv.exe') mpv\ -Force; if(Test-Path (Join-Path $root 'mpv.com')){ Copy-Item (Join-Path $root 'mpv.com') mpv\ -Force }; Get-ChildItem -Path $root -Filter '*.dll' -ErrorAction SilentlyContinue | ForEach-Object { Copy-Item $_.FullName mpv\ -Force }; Remove-Item $out -Force -ErrorAction SilentlyContinue; Remove-Item mpv_extract -Recurse -Force -ErrorAction SilentlyContinue"
  if errorlevel 1 goto :err
)

py -3 -m pip install --upgrade pip
py -3 -m pip install PySide6 mutagen numpy pyinstaller
if errorlevel 1 goto :err

py -3 -m PyInstaller --noconfirm --clean reproductor-flac.spec
if errorlevel 1 goto :err

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
  echo Generando instalador...
  "%ISCC%" installer_windows.iss
  if errorlevel 1 goto :err
  echo Instalador: dist\ReproductorFLAC-windows-installer.exe
) else (
  echo Inno Setup no encontrado; se omitio el instalador. Solo se genero la carpeta portable.
)

echo.
echo Listo. Carpeta portable: dist\ReproductorFLAC
echo Comparte la carpeta completa (incluye mpv) o usa el instalador si se genero.
exit /b 0

:err
echo.
echo Error durante la compilacion.
exit /b 1

