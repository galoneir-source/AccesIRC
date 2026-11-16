@echo off
cd /d "%~dp0"
echo Creando AccesIRC.exe. Tarda unos minutos...
echo.
py -m pip install --user --no-warn-script-location pyinstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
py -m PyInstaller --noconfirm --clean --windowed --onedir --name AccesIRC --collect-all accessible_output2 AccesIRC.py
if not exist "dist\AccesIRC\AccesIRC.exe" (
  echo.
  echo No se pudo crear el programa. Copia el texto de esta ventana y envialo para revisarlo.
  pause
  exit /b 1
)
copy /y LEEME.txt "dist\AccesIRC\" >nul
echo Comprimiendo para compartir...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\AccesIRC' -DestinationPath 'dist\AccesIRC-para-compartir.zip'"
echo.
echo Listo. En la carpeta dist tienes:
echo   AccesIRC: la carpeta del programa. Se abre con AccesIRC.exe que hay dentro.
echo   AccesIRC-para-compartir.zip: la misma carpeta comprimida, para enviarla.
echo Quien lo reciba debe descomprimir el zip entero y abrir AccesIRC.exe.
echo No basta con copiar solo el exe: necesita la carpeta _internal que hay a su lado.
pause
