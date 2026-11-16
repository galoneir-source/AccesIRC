@echo off
cd /d "%~dp0"
echo Instalando los componentes de AccesIRC. Espera, puede tardar unos minutos...
echo.
py -m pip --version >nul 2>&1
if errorlevel 1 (
  echo Pip esta danado. Descargando el instalador oficial de pip...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing https://bootstrap.pypa.io/get-pip.py -OutFile \"$env:TEMP\get-pip.py\""
  if not exist "%TEMP%\get-pip.py" (
    echo.
    echo No se pudo descargar el instalador de pip. Comprueba la conexion a internet.
    pause
    exit /b 1
  )
  echo Reinstalando pip en tu carpeta de usuario...
  py "%TEMP%\get-pip.py" --user --no-warn-script-location
  del "%TEMP%\get-pip.py" >nul 2>&1
)
py -m pip --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo No se pudo reparar pip. Copia el texto de esta ventana y envialo para revisarlo.
  pause
  exit /b 1
)
echo Instalando wxPython y el soporte para lectores de pantalla...
py -m pip install --user --no-warn-script-location -r requirements.txt
if errorlevel 1 (
  echo.
  echo Hubo un error al instalar los componentes. Copia el texto de esta ventana
  echo y envialo para revisarlo.
  pause
  exit /b 1
)
echo.
echo Listo. Ya puedes abrir AccesIRC.bat
pause
