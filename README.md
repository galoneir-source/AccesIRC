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

### Con Python

1. Instala Python 3.12 o posterior desde [python.org](https://www.python.org/downloads/).
   En el instalador, marca la casilla «Add python.exe to PATH».
2. Descarga este proyecto (botón «Code», «Download ZIP») y descomprímelo.
3. Ejecuta `instalar.bat` y espera a que diga «Listo».
4. Abre `AccesIRC.bat`.

### Programa ejecutable

En la sección [Releases](../../releases) puede haber un zip con `AccesIRC.exe`, que no necesita Python.
Hay que descomprimir el zip entero: el exe solo no funciona sin la carpeta `_internal` que lo acompaña.

Para crear el ejecutable tú mismo, ejecuta `crear_exe.bat` después de `instalar.bat`.

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
