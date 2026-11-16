@echo off
setlocal
cd /d "%~dp0"
echo CREAR EL PROGRAMA AccesIRC PARA COMPARTIR
echo Tarda unos minutos. No cierres esta ventana.
echo.

rem --- Elegir Python: 3.13 o 3.12 si estan instalados; si no, el que haya ---
set "PY="
py -3.13 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3.13"
if defined PY goto python_elegido
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3.12"
if defined PY goto python_elegido
py --version >nul 2>&1
if errorlevel 1 goto sin_python
set "PY=py"
:python_elegido
echo Se usara:
%PY% --version
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if not errorlevel 1 goto python_ok
echo.
echo ATENCION: ese Python es antiguo y el programa llevaria componentes de seguridad caducados.
echo Instala Python 3.13 desde python.org, el "Windows installer 64-bit", y vuelve a empezar.
echo Pulsa una tecla para seguir de todos modos, o cierra esta ventana para cancelar.
pause >nul
:python_ok
echo.

rem --- Componentes ---
echo Instalando los componentes necesarios...
%PY% -m pip install --user --no-warn-script-location --upgrade pyinstaller -r requirements.txt
if errorlevel 1 goto error

rem --- Version, leida de AccesIRC.py ---
%PY% -c "import re;print(re.search(r'^VERSION = .([^\x22]+)',open('AccesIRC.py',encoding='utf-8').read(),re.M).group(1))" > "%TEMP%\accesirc_version.txt"
if errorlevel 1 goto error
set /p VERSION=<"%TEMP%\accesirc_version.txt"
del "%TEMP%\accesirc_version.txt" >nul 2>&1
echo Version de AccesIRC: %VERSION%
echo.

rem --- Programa ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PY% -m PyInstaller --noconfirm --clean --windowed --onedir --name AccesIRC --collect-all accessible_output2 AccesIRC.py
if not exist "dist\AccesIRC\AccesIRC.exe" goto error
copy /y LEEME.txt "dist\AccesIRC\" >nul
copy /y LICENSE "dist\AccesIRC\" >nul

rem --- Version portatil en zip ---
echo.
echo Comprimiendo la version portatil...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\AccesIRC' -DestinationPath 'dist\AccesIRC-%VERSION%-portatil.zip'"

rem --- Instalador, si Inno Setup esta instalado ---
set "ISCC="
for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do set "ISCC=%%i"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC goto sin_inno
echo Creando el instalador...
"%ISCC%" /Q "/DMyVersion=%VERSION%" instalador.iss
if errorlevel 1 goto error_inno
echo.
echo LISTO. En la carpeta dist tienes:
echo   AccesIRC-%VERSION%-instalador.exe: lo que debes compartir. Quien lo reciba solo
echo     tiene que abrirlo y pulsar Siguiente. No necesita Python.
echo   AccesIRC-%VERSION%-portatil.zip: la misma version sin instalar, para llevar en un pendrive.
echo     Hay que descomprimirlo entero y abrir AccesIRC.exe.
goto fin

:sin_inno
echo.
echo El programa esta listo, pero falta Inno Setup para crear el instalador.
echo Para instalarlo, escribe en una ventana de cmd:
echo     winget install JRSoftware.InnoSetup
echo o descargalo de jrsoftware.org, y vuelve a ejecutar este archivo.
echo.
echo Mientras tanto, en dist tienes AccesIRC-%VERSION%-portatil.zip, que tambien funciona sin Python:
echo hay que descomprimirlo entero y abrir AccesIRC.exe.
goto fin

:error_inno
echo.
echo El programa esta listo, pero no se pudo crear el instalador.
echo Copia el texto de esta ventana y envialo para revisarlo.
goto fin

:sin_python
echo No se encuentra Python. Instala Python 3.13 desde python.org, el "Windows installer 64-bit",
echo marcando la casilla "Add python.exe to PATH", y vuelve a ejecutar este archivo.
goto fin

:error
echo.
echo No se pudo crear el programa. Copia el texto de esta ventana y envialo para revisarlo.
pause
exit /b 1

:fin
echo.
pause
