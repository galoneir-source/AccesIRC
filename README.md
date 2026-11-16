# AccesIRC

Cliente de IRC para Windows pensado para usarse con lector de pantalla (NVDA, JAWS y otros).

- Los mensajes nuevos se leen solos con la voz del lector de pantalla.
- Todo se maneja con el teclado, y el historial se recorre con las flechas como un documento normal.
- Identificación automática del apodo: contraseña junto al apodo (Chat Hispano), NickServ, SASL o PASS.
  La contraseña se guarda cifrada con tu usuario de Windows.
- Conexión cifrada con verificación del certificado mediante el almacén de certificados de Windows.
- Envío y recepción de archivos por DCC, también en modo pasivo, con avisos para los archivos peligrosos.
- Sonidos configurables para cada evento (sirven los WAV de IRCap), respuestas automáticas,
  palabras de aviso, lista de ignorados y respuesta automática cuando estás ausente.

## Instalación

### Con el instalador (recomendado, no necesita Python)

1. Descarga `AccesIRC-…-instalador.exe` de la sección [Releases](../../releases).
2. Ábrelo. Si Windows muestra «Windows protegió su PC», pulsa «Más información» y
   «Ejecutar de todas formas»: aparece porque el programa no está firmado.
3. Pulsa Siguiente en cada paso. AccesIRC queda en el menú Inicio.

No pide permisos de administrador. Para actualizar, basta con abrir el instalador de la versión nueva.

También hay una versión portátil, `AccesIRC-…-portatil.zip`: se descomprime entera y se abre `AccesIRC.exe`.

### Con Python

1. Instala Python 3.13 desde [python.org](https://www.python.org/downloads/windows/)
   («Windows installer (64-bit)»), marcando «Add python.exe to PATH».
2. Descarga este proyecto (botón «Code», «Download ZIP») y descomprímelo.
3. Ejecuta `instalar.bat` y después abre `AccesIRC.bat`.

### Crear el instalador

Con Python 3.13 y [Inno Setup](https://jrsoftware.org/isinfo.php) instalados
(`winget install JRSoftware.InnoSetup`), ejecuta `crear_exe.bat`. El instalador y la versión
portátil aparecen en la carpeta `dist`.

## Uso

Todas las instrucciones, atajos de teclado y órdenes están en [LEEME.txt](LEEME.txt).
Dentro del programa, F1 muestra la lista completa de atajos.

| Atajo | Acción |
|---|---|
| F6 | Moverse entre el mensaje, el historial, las ventanas y los usuarios |
| Alt+1 … Alt+0 | Leer el último mensaje, el penúltimo… sin moverte |
| Ctrl+Avance/Retroceso de página | Cambiar de canal o de privado |
| Ctrl+O | Conectar |
| F2 | Silenciar o activar la voz |

## Datos y privacidad

La configuración se guarda en `%APPDATA%\AccesIRC\config.json`, con las contraseñas cifradas
con tu usuario de Windows. Las conversaciones se guardan en `%APPDATA%\AccesIRC\registros`
(se puede desactivar). Para enviar archivos, AccesIRC consulta tu IP pública en api.ipify.org
(también se puede desactivar).

## Requisitos

- Windows 10 u 11
- Python 3.12 o posterior (si no usas el ejecutable)
- [wxPython](https://wxpython.org/), [accessible_output2](https://pypi.org/project/accessible-output2/),
  [truststore](https://pypi.org/project/truststore/) y [certifi](https://pypi.org/project/certifi/),
  que instala `instalar.bat`

## Licencia

[MIT](LICENSE). © 2026 Daniel Villalón y José Ángel Ortiz.
