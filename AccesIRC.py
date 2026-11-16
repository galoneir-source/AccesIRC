# -*- coding: utf-8 -*-
"""
AccesIRC - Cliente IRC accesible para Windows y lectores de pantalla (NVDA, JAWS).

Usa controles nativos de Windows (wxPython), de modo que NVDA puede leer todo
con las flechas, y habla los mensajes entrantes a través del propio lector de
pantalla.
"""

import base64
import copy
import datetime
import hashlib
import ipaddress
import json
import os
import platform
import queue
import random
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
import webbrowser

import wx

try:
    import winsound
except ImportError:  # fuera de Windows
    winsound = None

NOMBRE_APP = "AccesIRC"
VERSION = "1.6.0"
DIR_DATOS = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), NOMBRE_APP)
RUTA_CONFIG = os.path.join(DIR_DATOS, "config.json")
DIR_REGISTROS = os.path.join(DIR_DATOS, "registros")
DIR_SONIDOS = os.path.join(DIR_DATOS, "sonidos")
RUTA_ERRORES = os.path.join(DIR_DATOS, "errores.log")
DESCARGAS_DEFECTO = os.path.join(os.path.expanduser("~"), "Downloads", NOMBRE_APP)
REPO_GITHUB = "galoneir-source/AccesIRC"
URL_ULTIMA_VERSION = "https://api.github.com/repos/%s/releases/latest" % REPO_GITHUB
URL_DESCARGAS = "https://github.com/%s/releases/latest" % REPO_GITHUB
DIR_ACTUALIZACION = os.path.join(tempfile.gettempdir(), NOMBRE_APP + "-actualizacion")
# Como mucho una comprobación automática cada 20 horas.
INTERVALO_ACTUALIZACION = 20 * 3600
MAX_LINEAS = 1500
# Límite para archivos recibidos cuando el emisor no dice el tamaño.
MAX_DCC_SIN_TAMANO = 1024 * 1024 * 1024
# Extensiones que pueden ejecutar código al abrirlas.
EXTENSIONES_PELIGROSAS = {
    ".exe", ".com", ".bat", ".cmd", ".scr", ".pif", ".msi", ".msp", ".lnk", ".url", ".js", ".jse",
    ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1", ".hta", ".cpl", ".jar", ".reg", ".dll", ".appx",
    ".msix", ".application", ".iso", ".img", ".vhd", ".vhdx", ".chm", ".inf", ".scf", ".docm", ".xlsm",
    ".pptm",
}
NOMBRES_RESERVADOS = {"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(10)} | {"lpt%d" % i for i in range(10)}

# Datos que se guardan por separado para cada red.
CAMPOS_RED = ("servidor", "puerto", "ssl", "verificar_cert", "apodo", "apodo_alt", "nombre_real",
              "metodo_ident", "clave", "canales", "ordenes", "reconectar", "huella", "nombre_cert")

CONFIG_DEFECTO = {
    "red": "Libera.Chat",
    "servidor": "irc.libera.chat",
    "puerto": 6697,
    "ssl": True,
    "verificar_cert": True,
    "apodo": "",
    "apodo_alt": "",
    "nombre_real": "Usuario de AccesIRC",
    "metodo_ident": "ninguno",
    "clave": "",
    "canales": "",
    "ordenes": "",
    "reconectar": True,
    "huella": "",
    "nombre_cert": "",
    "redes": {},
    "voz": True,
    "leer_propios": True,
    "leer_todo": False,
    "anunciar_entradas": False,
    "sonidos": True,
    "mostrar_hora": False,
    "guardar_registros": True,
    "sonidos_eventos": {},
    "rejoin": False,
    "respuesta_ausente": True,
    "palabras_aviso": "",
    "ignorados": "",
    "respuestas": "",
    "carpeta_descargas": "",
    "dcc_ip": "",
    "dcc_ip_auto": True,
    "dcc_puertos": "5000-5010",
    "dcc_pasivo": False,
    "buscar_actualizaciones": True,
    "ultima_comprobacion": 0,
    "version_omitida": "",
}

REDES_PREDEFINIDAS = {
    "Chat Hispano": {"servidor": "ssl.chathispano.com", "puerto": 6697, "ssl": True, "metodo_ident": "apodo",
                     "nombre_cert": "chatmovil.chathispano.com"},
    "Libera.Chat": {"servidor": "irc.libera.chat", "puerto": 6697, "ssl": True, "metodo_ident": "sasl"},
}

METODOS_IDENT = [
    ("ninguno", "Ninguna"),
    ("apodo", "Contraseña junto al apodo, apodo:contraseña (Chat Hispano)"),
    ("nickserv", "Mensaje a NickServ (IDENTIFY)"),
    ("sasl", "SASL (Libera.Chat y otras redes modernas)"),
    ("pass", "Contraseña del servidor (PASS)"),
]

# clave, descripción, sonido de Windows por defecto (None = sin sonido)
EVENTOS_SONIDO = [
    ("conectar", "Conectado al servidor", None),
    ("desconectar", "Desconectado del servidor", None),
    ("privado", "Mensaje privado", "SystemAsterisk"),
    ("mencion", "Te nombran o aparece una palabra de aviso", "SystemExclamation"),
    ("mensaje", "Mensaje en un canal", None),
    ("entrada", "Alguien entra en un canal", None),
    ("salida", "Alguien sale de un canal o se desconecta", None),
    ("aviso", "Aviso (notice) de un usuario", None),
    ("op", "Te dan operador", None),
    ("expulsion", "Te expulsan de un canal", "SystemHand"),
    ("invitacion", "Te invitan a un canal", "SystemQuestion"),
    ("dcc", "Alguien quiere enviarte un archivo", "SystemQuestion"),
    ("dcc_fin", "Transferencia de archivo terminada", "SystemAsterisk"),
]

RANGOS = "~&@%+"
NOMBRE_RANGO = {
    "~": "fundador",
    "&": "administrador",
    "@": "operador",
    "%": "semioperador",
    "+": "con voz",
}

NUMERICOS_SILENCIOSOS = {
    "002", "003", "004", "005", "250", "251", "252", "253", "254", "255",
    "265", "266", "372", "375", "376", "396", "422", "900",
}
NUMERICOS_WHOIS = {"301", "307", "311", "312", "313", "317", "319", "320", "330", "338", "378", "671"}

TEXTO_AYUDA = """ATAJOS DE TECLADO

F6 / Mayúsculas+F6: moverse entre el campo de mensaje, el historial, la lista de ventanas y la lista de usuarios.
Alt+M: ir al campo de mensaje.  Alt+H: ir al historial.  Alt+V: ir a la lista de ventanas.  Alt+U: ir a la lista de usuarios.
Escape: volver al campo de mensaje.
Ctrl+Avance de página / Ctrl+Retroceso de página: ventana siguiente / anterior.
Ctrl+1 a Ctrl+9: ir directamente a la ventana 1 a 9.
Alt+1 a Alt+9 y Alt+0: leer el último mensaje, el penúltimo... hasta el décimo, sin moverte del sitio.
Flecha arriba / abajo en el campo de mensaje: recuperar lo que escribiste antes.
Intro en la lista de usuarios: abrir conversación privada. Tecla de aplicaciones: más opciones, como enviar un archivo.

Ctrl+O: conectar.  Ctrl+D: desconectar.  Ctrl+J: unirse a un canal.  Ctrl+P: conversación privada.
Ctrl+W: cerrar la ventana actual.  Ctrl+T: leer el tema del canal.  Ctrl+E: estado de la conexión.
Ctrl+Mayúsculas+E: enviar un archivo.  Ctrl+Mayúsculas+T: ver las transferencias de archivos.
F2: activar o silenciar la voz.  Ctrl+Mayúsculas+V: probar la voz.
F3: leer también los mensajes de las demás ventanas.
F4: anunciar quién entra y sale.  F5: activar o desactivar los sonidos.  F1: esta ayuda.

IDENTIFICACIÓN AUTOMÁTICA DEL APODO

En el diálogo de conexión (Ctrl+O), elige la red, escribe tu apodo y tu contraseña, y elige el método de identificación.
En Chat Hispano es "Contraseña junto al apodo": AccesIRC envía apodo:contraseña al conectar, igual que /nick apodo:contraseña.
Cada red guarda sus propios datos. La contraseña se guarda cifrada con tu usuario de Windows.

ÓRDENES (se escriben en el campo de mensaje)

/join #canal          Entrar en un canal (también /j).
/part [motivo]        Salir del canal actual.
/msg apodo texto      Mensaje privado.
/query apodo          Abrir una ventana privada con alguien.
/me texto             Acción, por ejemplo: /me saluda a todos.
/nick nuevoapodo      Cambiar de apodo.
/topic [texto]        Leer o cambiar el tema del canal.
/whois apodo          Información sobre un usuario.
/names                Lista de usuarios del canal.
/away [motivo]        Marcarte como ausente (sin motivo, vuelves).
/notice apodo texto   Enviar un aviso.
/dcc send apodo [archivo]  Enviar un archivo. Sin archivo, se abre el diálogo para elegirlo.
/dcc                  Ver las transferencias de archivos.
/ignore apodo         Ignorar a alguien.  /unignore apodo: dejar de ignorarle.
/clear                Borrar el historial de la ventana.
/close                Cerrar la ventana actual.
/server               Abrir el diálogo de conexión.
/quit [mensaje]       Desconectar.
/raw orden            Enviar una orden IRC tal cual.
Cualquier otra orden se envía directamente al servidor.
Para enviar un texto que empiece por barra, escribe dos barras: //texto.

SONIDOS Y AUTOMATIZACIONES (menú Opciones)

Configurar sonidos: asigna un archivo WAV a cada evento, por ejemplo los sonidos de IRCap.
Automatizaciones: respuestas automáticas, palabras que te avisan, apodos ignorados,
volver a entrar si te expulsan y respuesta automática cuando estás ausente.
En las respuestas y en las órdenes al conectar puedes usar $nick (quien escribe), $canal y $yo (tu apodo).
"""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def registrar_error(texto):
    try:
        os.makedirs(DIR_DATOS, exist_ok=True)
        with open(RUTA_ERRORES, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().isoformat() + "\n" + texto + "\n")
    except OSError:
        pass


def _dpapi(datos, proteger):
    """Cifra o descifra con la cuenta de Windows del usuario (DPAPI)."""
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    bufer = ctypes.create_string_buffer(datos, len(datos))
    entrada = BLOB(len(datos), ctypes.cast(bufer, ctypes.POINTER(ctypes.c_char)))
    salida = BLOB()
    crypt32 = ctypes.windll.crypt32
    funcion = crypt32.CryptProtectData if proteger else crypt32.CryptUnprotectData
    if not funcion(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida)):
        raise OSError("DPAPI no disponible")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def proteger_clave(texto):
    if not texto or sys.platform != "win32":
        return texto
    try:
        return "dpapi:" + base64.b64encode(_dpapi(texto.encode("utf-8"), True)).decode("ascii")
    except Exception:
        registrar_error("No se pudo cifrar la contraseña con Windows: se guarda sin cifrar.\n"
                        + traceback.format_exc())
        return texto


def desproteger_clave(texto):
    if not isinstance(texto, str):
        return ""
    if not texto.startswith("dpapi:"):
        return texto
    try:
        return _dpapi(base64.b64decode(texto[6:]), False).decode("utf-8")
    except Exception:
        registrar_error("No se pudo descifrar una contraseña guardada.")
        return ""


def cargar_config():
    cfg = copy.deepcopy(CONFIG_DEFECTO)
    datos = {}
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        pass
    if isinstance(datos, dict):
        cfg.update(datos)
        if "red" not in datos:
            cfg["red"] = cfg["servidor"]
    # Configuración de versiones anteriores
    antigua = cfg.pop("clave_nickserv", "")
    if antigua and not cfg.get("clave"):
        cfg["clave"] = antigua
        cfg["metodo_ident"] = "nickserv"
    for clave in ("redes", "sonidos_eventos"):
        if not isinstance(cfg.get(clave), dict):
            cfg[clave] = {}
    cfg["clave"] = desproteger_clave(cfg.get("clave", ""))
    for nombre, red in list(cfg["redes"].items()):
        if isinstance(red, dict):
            red["clave"] = desproteger_clave(red.get("clave", ""))
        else:
            del cfg["redes"][nombre]
    if not cfg["redes"] and cfg.get("apodo"):
        cfg["redes"][cfg["red"]] = {k: cfg[k] for k in CAMPOS_RED}
    # La 1.4 conectaba a chatmovil.chathispano.com, que no admite IRC cifrado.
    for datos_red in [cfg] + list(cfg["redes"].values()):
        if str(datos_red.get("servidor", "")).lower() == "chatmovil.chathispano.com":
            datos_red["servidor"] = "ssl.chathispano.com"
            datos_red["nombre_cert"] = "chatmovil.chathispano.com"
    return cfg


def guardar_config(cfg):
    copia = copy.deepcopy(cfg)
    copia["clave"] = proteger_clave(copia.get("clave", ""))
    for red in copia["redes"].values():
        red["clave"] = proteger_clave(red.get("clave", ""))
    try:
        os.makedirs(DIR_DATOS, exist_ok=True)
        temporal = RUTA_CONFIG + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(copia, f, ensure_ascii=False, indent=2)
        os.replace(temporal, RUTA_CONFIG)
    except OSError:
        registrar_error("No se pudo guardar la configuración:\n" + traceback.format_exc())


RE_FORMATO = re.compile(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?|\x04[0-9a-fA-F]{0,6}|[\x02\x0f\x11\x16\x1d\x1e\x1f]")


def limpiar_formato(texto):
    """Quita colores, negritas y demás códigos de formato de mIRC."""
    return RE_FORMATO.sub("", texto)


def parsear(linea):
    """Devuelve (prefijo, apodo, orden, parámetros) de una línea IRC."""
    if linea.startswith("@"):
        _, _, linea = linea.partition(" ")
    prefijo = ""
    if linea.startswith(":"):
        prefijo, _, linea = linea[1:].partition(" ")
    if linea.startswith(":"):
        params = [linea[1:]]
    elif " :" in linea:
        cabeza, _, final = linea.partition(" :")
        params = cabeza.split() + [final]
    else:
        params = linea.split()
    orden = params.pop(0).upper() if params else ""
    apodo = prefijo.split("!", 1)[0]
    return prefijo, apodo, orden, params


def es_canal(nombre):
    return bool(nombre) and nombre[0] in "#&+!"


def dividir_texto(texto, limite=400):
    """Parte un texto largo en trozos que el servidor acepte, cortando en espacios."""
    partes = []
    while len(texto.encode("utf-8")) > limite:
        trozo = texto.encode("utf-8")[:limite].decode("utf-8", "ignore")
        espacio = trozo.rfind(" ")
        if espacio > len(trozo) // 2:
            trozo = trozo[:espacio]
        partes.append(trozo)
        texto = texto[len(trozo):].lstrip()
    if texto:
        partes.append(texto)
    return partes


def nombre_seguro(texto):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto) or "_"


def lista_comas(texto):
    return [x.strip() for x in re.split(r"[,\s]+", texto or "") if x.strip()]


def lista_canales(texto):
    """Canales al entrar, separados por comas, cada uno con su clave opcional detrás:
    «#ciegos, #privado miclave». Devuelve [(canal, clave), ...].
    Por compatibilidad, «#a #b» (separados por espacio) siguen siendo dos canales."""
    resultado = []
    for entrada in (texto or "").split(","):
        palabras = entrada.split()
        while palabras:
            canal = palabras.pop(0)
            clave = ""
            if palabras and not es_canal(palabras[0]):
                clave = palabras.pop(0)
            resultado.append((canal, clave))
    return resultado


class CertificadoCambiado(Exception):
    """El servidor presenta un certificado distinto del que el usuario decidió aceptar."""

    def __init__(self, huella):
        super().__init__("certificado cambiado")
        self.huella = huella


def describir_error(e):
    if isinstance(e, CertificadoCambiado):
        return "el certificado del servidor ha cambiado desde que decidiste confiar en él"
    if isinstance(e, ssl.SSLCertVerificationError):
        return "no se pudo comprobar el certificado de seguridad del servidor"
    if isinstance(e, ssl.SSLError):
        return "el servidor no acepta conexión cifrada en este puerto"
    if isinstance(e, socket.gaierror):
        return "no se encuentra el servidor; revisa la dirección"
    if isinstance(e, ConnectionRefusedError):
        return "el servidor rechazó la conexión; revisa el puerto"
    if isinstance(e, TimeoutError):
        return "el servidor no responde"
    if isinstance(e, ConnectionResetError):
        return "el servidor cortó la conexión"
    return str(e) or e.__class__.__name__


# ---------------------------------------------------------------------------
# Certificados TLS
# ---------------------------------------------------------------------------

MOTIVOS_CERTIFICADO = [
    ("unable to get local issuer", "Falta un certificado intermedio, o la autoridad que firmó el certificado "
                                   "no es de confianza en este equipo."),
    ("self-signed", "El certificado está firmado por el propio servidor (autofirmado)."),
    ("self signed", "El certificado está firmado por el propio servidor (autofirmado)."),
    ("expired", "El certificado ha caducado."),
    ("hostname mismatch", "El certificado no corresponde al nombre de este servidor."),
    ("not valid for", "El certificado no corresponde al nombre de este servidor."),
    ("not trusted", "Windows no confía en la autoridad que firmó el certificado."),
    ("revocation", "No se pudo comprobar si el certificado ha sido revocado."),
]


def traducir_motivo(mensaje):
    bajo = (mensaje or "").lower()
    for clave, texto in MOTIVOS_CERTIFICADO:
        if clave in bajo:
            return texto
    return ""


def contexto_tls(verificar):
    """Contexto TLS. Si se verifica, usa el almacén de certificados de Windows (truststore),
    que además descarga los certificados intermedios que el servidor no envíe."""
    if not verificar:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except Exception:
            pass
        return ctx


def huella_de(der):
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def envolver_tls(sock, host, verificar, huella="", nombre_cert=""):
    """nombre_cert: nombre con el que se verifica el certificado, si el servidor
    presenta uno válido emitido para otro nombre de la misma red."""
    host = nombre_cert or host
    try:
        if huella:
            # El usuario aceptó un certificado concreto: solo vale exactamente ese.
            tls = contexto_tls(False).wrap_socket(sock, server_hostname=host)
            actual = huella_de(tls.getpeercert(binary_form=True))
            if actual != huella:
                tls.close()
                raise CertificadoCambiado(actual)
            return tls
        return contexto_tls(verificar).wrap_socket(sock, server_hostname=host)
    except Exception:
        sock.close()
        raise


def conectar_verificado(host, puerto, nombre_cert=""):
    """Abre una conexión TLS con verificación completa. Devuelve el socket o None si no se verifica.
    Sirve para saber si un certificado recordado se ha renovado por uno válido."""
    sock = None
    try:
        sock = socket.create_connection((host, puerto), timeout=20)
        return contexto_tls(True).wrap_socket(sock, server_hostname=nombre_cert or host)
    except Exception:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        return None


def obtener_certificado(host, puerto):
    with socket.create_connection((host, puerto), timeout=15) as s:
        with contexto_tls(False).wrap_socket(s, server_hostname=host) as tls:
            return tls.getpeercert(binary_form=True)


def leer_certificado(der):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(ssl.DER_cert_to_PEM_cert(der))
        ruta = f.name
    try:
        return ssl._ssl._test_decode_cert(ruta)
    finally:
        os.remove(ruta)


def nombres_certificado(der):
    """Nombres de servidor concretos (sin comodines) que cubre el certificado."""
    try:
        info = leer_certificado(der)
    except Exception:
        return []
    return [v for k, v in info.get("subjectAltName", ()) if k == "DNS" and "*" not in v]


def describir_certificado(der):
    lineas = []
    try:
        info = leer_certificado(der)

        def nombre(campos):
            return ", ".join("%s=%s" % par for rdn in campos for par in rdn)
        lineas.append("Emitido para: " + nombre(info.get("subject", ())))
        lineas.append("Emitido por: " + nombre(info.get("issuer", ())))
        if info.get("subject") == info.get("issuer"):
            lineas.append("Es un certificado autofirmado.")
        dns = [v for k, v in info.get("subjectAltName", ()) if k == "DNS"]
        if dns:
            lineas.append("Nombres que cubre: " + ", ".join(dns))
        lineas.append("Válido desde: %s" % info.get("notBefore"))
        lineas.append("Válido hasta: %s" % info.get("notAfter"))
        if ssl.cert_time_to_seconds(info["notAfter"]) < time.time():
            lineas.append("Atención: el certificado ha caducado.")
    except Exception:
        lineas.append("No se pudieron leer los detalles del certificado.")
    lineas.append("Huella SHA-256: " + huella_de(der))
    return "\n".join(lineas)


def analizar_certificado(host, puerto, error):
    """Reúne el motivo exacto del fallo y los datos del certificado. Se ejecuta en un hilo."""
    if isinstance(error, CertificadoCambiado):
        mensaje = "el certificado no coincide con el que aceptaste"
    else:
        mensaje = getattr(error, "verify_message", None) or str(error)
    info = {"mensaje": mensaje, "motivo": traducir_motivo(mensaje), "huella": None, "detalles": "",
            "alternativa": None}
    try:
        der = obtener_certificado(host, puerto)
        info["huella"] = huella_de(der)
        info["detalles"] = describir_certificado(der)
        info["alternativa"] = alternativa_verificable(host, puerto, der)
    except Exception as e:
        info["detalles"] = "No se pudo obtener el certificado: " + describir_error(e)
    return info


def mismo_dominio(host, nombre):
    """True si 'nombre' pertenece al mismo dominio que 'host'. Ejemplo: desde ssl.chathispano.com
    se admite chatmovil.chathispano.com, pero nunca un dominio ajeno como atacante.com: un
    certificado válido de otro dominio no prueba que el servidor sea quien dice ser."""
    host = host.lower().rstrip(".")
    nombre = nombre.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    etiquetas = host.split(".")
    if len(etiquetas) < 2:
        return False
    # Dominio padre: se quita la primera etiqueta si quedan al menos dos (irc.libera.chat -> libera.chat).
    padre = ".".join(etiquetas[1:]) if len(etiquetas) >= 3 else host
    if not dominio_propio(padre):
        return False
    return nombre == padre or nombre.endswith("." + padre)


# Segundos niveles genéricos bajo un dominio de país: com.ar, com.mx, co.uk, gob.es...
SEGUNDOS_NIVELES = {"com", "net", "org", "edu", "gob", "gov", "mil", "int", "co", "ac", "nom", "ltd",
                    "plc", "info", "biz", "web", "or", "ne", "go", "es"}
# Dominios donde cualquiera puede tener un subdominio propio con certificado válido.
DOMINIOS_COMPARTIDOS = {
    "duckdns.org", "dyndns.org", "dynu.net", "no-ip.org", "no-ip.com", "noip.me", "ddns.net", "hopto.org",
    "zapto.org", "sytes.net", "freedns.org", "afraid.org", "mooo.com", "github.io", "gitlab.io",
    "herokuapp.com", "netlify.app", "vercel.app", "pages.dev", "workers.dev", "web.app", "firebaseapp.com",
    "azurewebsites.net", "cloudfront.net", "amazonaws.com", "appspot.com", "ngrok.io", "ngrok-free.app",
    "blogspot.com", "glitch.me", "repl.co", "fly.dev", "onrender.com", "trycloudflare.com",
}


def dominio_propio(dominio):
    """True si 'dominio' parece un dominio registrado por una sola entidad, y no un sufijo público
    como com.ar o co.uk, ni un servicio donde cualquiera puede crear subdominios (duckdns.org...).
    Sin esta comprobación, desde chatlatino.com.ar se aceptaría un certificado de atacante.com.ar."""
    etiquetas = dominio.split(".")
    if len(etiquetas) < 2:
        return False
    if len(etiquetas) == 2 and len(etiquetas[1]) == 2 and etiquetas[0] in SEGUNDOS_NIVELES:
        return False
    for compartido in DOMINIOS_COMPARTIDOS:
        if dominio == compartido or dominio.endswith("." + compartido):
            return False
    return True


def alternativa_verificable(host, puerto, der):
    """Si el certificado es válido pero emitido para otro nombre del mismo dominio, devuelve
    ese nombre cuando, conectando al mismo servidor, el certificado se verifica del todo con él.
    Se ejecuta en un hilo."""
    for nombre in nombres_certificado(der):
        if nombre.lower() == host.lower() or not mismo_dominio(host, nombre):
            continue
        try:
            with socket.create_connection((host, puerto), timeout=15) as s:
                with contexto_tls(True).wrap_socket(s, server_hostname=nombre):
                    return nombre
        except Exception:
            continue
    return None


def diagnosticar_tls(host, puerto, nombre_cert=""):
    """Prueba la verificación con cada almacén de certificados y devuelve un informe en texto."""
    lineas = ["Diagnóstico de la conexión cifrada con %s, puerto %d" % (host, puerto),
              "AccesIRC %s, Python %s, %s" % (VERSION, platform.python_version(), ssl.OPENSSL_VERSION), ""]
    if nombre_cert:
        try:
            with socket.create_connection((host, puerto), timeout=15) as s:
                with contexto_tls(True).wrap_socket(s, server_hostname=nombre_cert):
                    pass
            lineas.append("RESULTADO CON TU CONFIGURACIÓN: verificado correctamente con el nombre del "
                          "certificado %s. La conexión es segura y no hay nada que corregir." % nombre_cert)
        except Exception as e:
            lineas.append("RESULTADO CON TU CONFIGURACIÓN: FALLA con el nombre del certificado %s: %s" % (
                nombre_cert, getattr(e, "verify_message", None) or describir_error(e)))
        lineas.append("")
        lineas.append("Pruebas con el nombre del servidor, sin el nombre del certificado:")
    metodos = []
    try:
        import truststore
        metodos.append(("Almacén de certificados de Windows (truststore)",
                        lambda: truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
    except Exception:
        lineas.append("El paquete truststore no está instalado: ejecuta instalar.bat de nuevo.")
    metodos.append(("Certificados de OpenSSL de Python", ssl.create_default_context))
    try:
        import certifi
        metodos.append(("Paquete certifi", lambda: ssl.create_default_context(cafile=certifi.where())))
    except Exception:
        lineas.append("El paquete certifi no está instalado.")
    for nombre, crear in metodos:
        try:
            with socket.create_connection((host, puerto), timeout=15) as s:
                with crear().wrap_socket(s, server_hostname=host):
                    pass
            lineas.append("%s: verificado correctamente." % nombre)
        except ssl.SSLCertVerificationError as e:
            mensaje = e.verify_message or str(e)
            lineas.append("%s: FALLA. Mensaje exacto: %s (código %s). %s" % (
                nombre, mensaje, e.verify_code, traducir_motivo(mensaje)))
        except Exception as e:
            lineas.append("%s: error de conexión: %s (%s)" % (nombre, describir_error(e), e))
    lineas.append("")
    try:
        der = obtener_certificado(host, puerto)
        lineas.append(describir_certificado(der))
        if any("FALLA" in x for x in lineas) and not nombre_cert:
            alternativa = alternativa_verificable(host, puerto, der)
            if alternativa:
                lineas.append("")
                lineas.append("SOLUCIÓN: el certificado se verifica correctamente con el nombre %s. "
                              "Escríbelo en el campo «Nombre del certificado» del diálogo de conexión, "
                              "manteniendo el servidor %s." % (alternativa, host))
    except Exception as e:
        lineas.append("No se pudo obtener el certificado: " + describir_error(e))
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# DCC: utilidades de transferencia de archivos
# ---------------------------------------------------------------------------

RE_DCC_SEND = re.compile(r'^SEND\s+(?:"([^"]*)"|(\S+))\s+(\S+)\s+(\d+)(?:\s+(\d+))?(?:\s+(\S+))?\s*$', re.IGNORECASE)


def parsear_dcc_send(texto):
    """Interpreta 'SEND archivo ip puerto tamaño [token]'. Devuelve un dict o None."""
    m = RE_DCC_SEND.match(texto.strip())
    if not m:
        return None
    nombre = m.group(1) if m.group(1) is not None else m.group(2)
    ip = m.group(3)
    try:
        if ip.isdigit():
            ip = socket.inet_ntoa(struct.pack("!I", int(ip)))
        elif ":" in ip:
            socket.inet_pton(socket.AF_INET6, ip)
        else:
            socket.inet_aton(ip)
    except (OSError, struct.error, ValueError):
        return None
    puerto = int(m.group(4))
    if puerto > 65535:
        return None
    return {"nombre": nombre, "ip": ip, "puerto": puerto,
            "tamano": int(m.group(5) or 0), "token": m.group(6)}


def ip_para_dcc(ip):
    """Las IPv4 se anuncian como número entero, como hace mIRC."""
    try:
        return str(struct.unpack("!I", socket.inet_aton(ip))[0])
    except OSError:
        return ip


def tamano_legible(n):
    if n < 1024:
        return "%d bytes" % n
    for unidad in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unidad == "TB":
            return ("%.1f %s" % (n, unidad)).replace(".", ",")


def nombre_archivo_limpio(nombre):
    """Nombre seguro para guardar un archivo recibido en Windows.

    Quita carpetas, caracteres invisibles o de control (como el que invierte el texto y hace
    que «fotogpj.exe» parezca «fotoexe.jpg»), espacios repetidos que esconden la extensión,
    puntos y espacios finales, y evita los nombres reservados de Windows (CON, NUL, COM1...).
    """
    nombre = os.path.basename((nombre or "").replace("\\", "/"))
    nombre = "".join(c for c in nombre if unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"))
    nombre = re.sub(r"\s+", " ", nombre).strip().lstrip(".").rstrip(". ")
    nombre = re.sub(r"\s+\.", ".", nombre)
    nombre = nombre_seguro(nombre) if nombre else "archivo"
    if nombre.split(".", 1)[0].strip().lower() in NOMBRES_RESERVADOS:
        nombre = "_" + nombre
    return nombre[:200]


def es_peligroso(nombre):
    return os.path.splitext(nombre)[1].lower() in EXTENSIONES_PELIGROSAS


def marcar_como_descargado(ruta):
    """Añade la marca de «descargado de internet» (Mark of the Web) para que Windows
    SmartScreen y Office avisen al abrir el archivo."""
    if sys.platform != "win32":
        return
    try:
        with open(ruta + ":Zone.Identifier", "w", encoding="ascii") as f:
            f.write("[ZoneTransfer]\r\nZoneId=3\r\n")
    except OSError:
        registrar_error("No se pudo marcar como descargado: " + ruta)


def ruta_libre(carpeta, nombre):
    """Ruta dentro de 'carpeta' para 'nombre' que no pise ningún archivo existente."""
    nombre = nombre_archivo_limpio(nombre)
    base, ext = os.path.splitext(nombre)
    ruta = os.path.join(carpeta, nombre)
    n = 1
    while os.path.exists(ruta):
        ruta = os.path.join(carpeta, "%s (%d)%s" % (base, n, ext))
        n += 1
    return ruta


def abrir_puerto(rango):
    """Abre un socket a la escucha en el primer puerto libre del rango 'inicio-fin'."""
    m = re.match(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$", rango or "")
    if m:
        ini, fin = int(m.group(1)), int(m.group(2) or m.group(1))
        puertos = list(range(min(ini, fin), max(ini, fin) + 1))[:500]
    else:
        puertos = [0]
    for puerto in puertos:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("", puerto))
            s.listen(1)
            return s
        except OSError:
            s.close()
    raise OSError("todos los puertos de DCC (%s) están ocupados" % rango)


def ip_publica():
    with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
        ip = r.read(64).decode("ascii").strip()
    socket.inet_aton(ip)
    return ip


# ---------------------------------------------------------------------------
# Actualizaciones
# ---------------------------------------------------------------------------

def version_tupla(texto):
    """'v1.10.2' -> (1, 10, 2), para comparar versiones como números y no como texto."""
    numeros = re.findall(r"\d+", str(texto or ""))[:4]
    return tuple(int(n) for n in numeros) if numeros else (0,)


def abrir_url(url, timeout):
    """Abre una dirección HTTPS comprobando el certificado con el almacén de Windows."""
    peticion = urllib.request.Request(url, headers={
        "User-Agent": "%s/%s" % (NOMBRE_APP, VERSION),
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(peticion, timeout=timeout, context=contexto_tls(True))


def consultar_ultima_version():
    """Pregunta a GitHub por la última versión publicada. Se ejecuta en un hilo."""
    with abrir_url(URL_ULTIMA_VERSION, 15) as r:
        datos = json.loads(r.read(2 * 1024 * 1024).decode("utf-8"))
    etiqueta = str(datos.get("tag_name") or "")
    instalador = None
    prefijo = "https://github.com/%s/releases/download/" % REPO_GITHUB
    for archivo in datos.get("assets") or []:
        nombre = str(archivo.get("name") or "")
        url = str(archivo.get("browser_download_url") or "")
        # Solo se acepta el instalador publicado en el propio repositorio de AccesIRC.
        if nombre.lower().endswith("-instalador.exe") and url.lower().startswith(prefijo.lower()):
            instalador = {"nombre": nombre, "url": url, "tamano": int(archivo.get("size") or 0),
                          "digest": str(archivo.get("digest") or "")}
            break
    return {
        "version": etiqueta.lstrip("vV") or "?",
        "tupla": version_tupla(etiqueta),
        "notas": str(datos.get("body") or "").replace("\r\n", "\n").strip(),
        "pagina": str(datos.get("html_url") or URL_DESCARGAS),
        "instalador": instalador,
    }


def es_version_instalada():
    """True si este AccesIRC es el ejecutable que puso el instalador (tiene desinstalador al lado).
    La versión portátil y la de Python no se actualizan solas: se avisa y se abre la página."""
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    carpeta = os.path.dirname(os.path.abspath(sys.executable))
    try:
        return any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(carpeta))
    except OSError:
        return False


def descargar_instalador(instalador, progreso, cancelado):
    """Descarga el instalador, comprueba tamaño y huella SHA-256, y devuelve su ruta.
    progreso(hecho, total) se llama desde este hilo; cancelado() devuelve True para parar."""
    os.makedirs(DIR_ACTUALIZACION, exist_ok=True)
    destino = os.path.join(DIR_ACTUALIZACION, nombre_archivo_limpio(instalador["nombre"]))
    temporal = destino + ".descarga"
    resumen = hashlib.sha256()
    hecho = 0
    try:
        with abrir_url(instalador["url"], 30) as r, open(temporal, "wb") as f:
            total = instalador["tamano"] or int(r.headers.get("Content-Length") or 0)
            while True:
                if cancelado():
                    raise OSError("descarga cancelada")
                bloque = r.read(65536)
                if not bloque:
                    break
                f.write(bloque)
                resumen.update(bloque)
                hecho += len(bloque)
                if hecho > 300 * 1024 * 1024:
                    raise OSError("el archivo es demasiado grande")
                progreso(hecho, total)
        if instalador["tamano"] and hecho != instalador["tamano"]:
            raise OSError("la descarga está incompleta")
        digest = instalador["digest"]
        if digest.lower().startswith("sha256:") and digest[7:].lower() != resumen.hexdigest():
            raise OSError("el archivo descargado no coincide con el publicado")
        os.replace(temporal, destino)
        return destino
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise


def limpiar_actualizaciones_antiguas():
    """Borra los instaladores descargados en actualizaciones anteriores."""
    try:
        for nombre in os.listdir(DIR_ACTUALIZACION):
            try:
                os.remove(os.path.join(DIR_ACTUALIZACION, nombre))
            except OSError:
                pass
    except OSError:
        pass


class Transferencia:
    contador = 0

    def __init__(self, tipo, apodo, nombre, ruta, tamano):
        Transferencia.contador += 1
        self.id = Transferencia.contador
        self.tipo = tipo            # "recibir" o "enviar"
        self.apodo = apodo
        self.nombre = nombre
        self.ruta = ruta
        self.tamano = tamano
        self.hecho = 0
        self.confirmado = -1
        self.buf_ack = b""
        self.estado = "esperando"   # esperando, en_curso, completada, fallida, cancelada
        self.detalle = ""
        self.sock = None
        self.cancelada = False
        self.token = None
        self.al_avanzar = None
        self._cuarto = 0

    def activa(self):
        return self.estado in ("esperando", "en_curso")

    def porcentaje(self):
        return int(self.hecho * 100 / self.tamano) if self.tamano else 0

    def cancelar(self):
        self.cancelada = True
        sock = self.sock
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    def notificar_avance(self):
        if self.al_avanzar and self.tamano >= 5 * 1024 * 1024:
            cuarto = self.hecho * 4 // self.tamano
            if 0 < cuarto < 4 and cuarto > self._cuarto:
                self._cuarto = cuarto
                self.al_avanzar(self, cuarto * 25)

    def descripcion(self):
        base = "%s %s %s" % (self.nombre, "para" if self.tipo == "enviar" else "de", self.apodo)
        if self.estado == "en_curso":
            texto = "%s: %d%%, %s de %s" % (base, self.porcentaje(), tamano_legible(self.hecho),
                                            tamano_legible(self.tamano))
        else:
            estados = {"esperando": "esperando a la otra persona", "completada": "completada",
                       "cancelada": "cancelada", "fallida": "falló"}
            texto = "%s: %s" % (base, estados.get(self.estado, self.estado))
        if self.detalle and self.estado != "en_curso":
            texto += ". " + self.detalle
        return texto


def _procesar_acks(t, datos):
    t.buf_ack += datos
    while len(t.buf_ack) >= 4:
        t.confirmado = struct.unpack("!I", t.buf_ack[:4])[0]
        t.buf_ack = t.buf_ack[4:]


def recibir_dcc(sock, f, t):
    """Recibe el archivo por el socket, confirmando cada bloque como exige DCC."""
    sock.settimeout(120)
    while not t.cancelada:
        if t.tamano and t.hecho >= t.tamano:
            break
        datos = sock.recv(65536)
        if not datos:
            break
        if t.tamano:
            # No escribir más de lo anunciado.
            datos = datos[:t.tamano - t.hecho]
        elif t.hecho + len(datos) > MAX_DCC_SIN_TAMANO:
            raise OSError("el archivo no indicaba su tamaño y ya supera %s; se ha detenido"
                          % tamano_legible(MAX_DCC_SIN_TAMANO))
        f.write(datos)
        t.hecho += len(datos)
        sock.sendall(struct.pack("!I", t.hecho & 0xFFFFFFFF))
        t.notificar_avance()


def enviar_dcc(sock, f, t):
    """Envía el archivo por el socket y espera la confirmación final."""
    sock.settimeout(120)
    while not t.cancelada:
        bloque = f.read(65536)
        if not bloque:
            break
        sock.sendall(bloque)
        t.hecho += len(bloque)
        t.notificar_avance()
        # Leer las confirmaciones pendientes sin esperar, para no llenar el búfer.
        try:
            sock.settimeout(0)
            while True:
                datos = sock.recv(4096)
                if not datos:
                    break
                _procesar_acks(t, datos)
        except (BlockingIOError, InterruptedError):
            pass
        finally:
            sock.settimeout(120)
    if t.cancelada or not t.tamano:
        return
    objetivo = t.tamano & 0xFFFFFFFF
    sock.settimeout(30)
    try:
        while not t.cancelada and t.confirmado != objetivo:
            datos = sock.recv(4096)
            if not datos:
                break
            _procesar_acks(t, datos)
    except (socket.timeout, OSError):
        pass


# ---------------------------------------------------------------------------
# Voz
# ---------------------------------------------------------------------------

def _carpetas_bibliotecas():
    """Carpetas donde puede estar nvdaControllerClient, con o sin empaquetar en .exe."""
    carpetas = []
    base_exe = getattr(sys, "_MEIPASS", None)
    if base_exe:
        carpetas.append(os.path.join(base_exe, "accessible_output2", "lib"))
        carpetas.append(base_exe)
    dir_programa = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    carpetas.append(os.path.join(dir_programa, "_internal", "accessible_output2", "lib"))
    carpetas.append(os.path.join(dir_programa, "accessible_output2", "lib"))
    carpetas.append(dir_programa)
    try:
        import importlib.util
        spec = importlib.util.find_spec("accessible_output2")
        if spec and spec.submodule_search_locations:
            for ruta in spec.submodule_search_locations:
                carpetas.append(os.path.join(ruta, "lib"))
    except Exception:
        pass
    return carpetas


class Voz:
    """Habla a través de NVDA directamente; si no está, prueba otros lectores."""

    def __init__(self):
        self.activa = True
        self.nvda = None
        self.otros = []
        self._cargar_nvda()
        self._cargar_otros()

    def _cargar_nvda(self):
        if sys.platform != "win32":
            return
        import ctypes
        nombre = "nvdaControllerClient64.dll" if struct.calcsize("P") == 8 else "nvdaControllerClient32.dll"
        errores = []
        for carpeta in _carpetas_bibliotecas():
            ruta = os.path.join(carpeta, nombre)
            if not os.path.exists(ruta):
                continue
            try:
                lib = ctypes.WinDLL(ruta)
                lib.nvdaController_speakText.argtypes = (ctypes.c_wchar_p,)
                self.nvda = lib
                return
            except Exception as e:
                errores.append("%s: %s" % (ruta, e))
        registrar_error("No se encontró %s.\n%s" % (nombre, "\n".join(errores)))

    def _cargar_otros(self):
        # Otros lectores (JAWS, Dolphin...) y SAPI, cada uno por separado
        # para que un fallo en uno no anule a los demás.
        try:
            import accessible_output2
            for clase in accessible_output2.get_output_classes():
                if clase.__name__ == "NVDA":
                    continue
                try:
                    self.otros.append(clase())
                except Exception:
                    pass
        except Exception:
            registrar_error("accessible_output2 no disponible:\n" + traceback.format_exc())

    def _nvda_activo(self):
        try:
            return self.nvda is not None and self.nvda.nvdaController_testIfRunning() == 0
        except Exception:
            return False

    def motor(self):
        if self._nvda_activo():
            return "NVDA"
        for salida in self.otros:
            try:
                if salida.is_active():
                    return getattr(salida, "name", salida.__class__.__name__)
            except Exception:
                pass
        return None

    def decir(self, texto, interrumpir=False, forzar=False):
        if not texto or not (self.activa or forzar):
            return
        if self._nvda_activo():
            try:
                if interrumpir:
                    self.nvda.nvdaController_cancelSpeech()
                self.nvda.nvdaController_speakText(texto)
                return
            except Exception:
                pass
        for salida in self.otros:
            try:
                if salida.is_active():
                    salida.speak(texto, interrupt=interrumpir)
                    return
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Conexión de red
# ---------------------------------------------------------------------------

class ConexionIRC:
    """Mantiene el socket en un hilo aparte y entrega cada línea al hilo de la interfaz."""

    def __init__(self, host, puerto, usar_ssl, verificar, al_recibir, al_estado, huella="", nombre_cert="",
                 al_fase=None):
        self.huella = huella
        self.nombre_cert = nombre_cert
        self.al_fase = al_fase
        self.info_cert = None
        self.host = host
        self.puerto = puerto
        self.usar_ssl = usar_ssl
        self.verificar = verificar
        self.al_recibir = al_recibir
        self.al_estado = al_estado
        self.sock = None
        self.lock = threading.Lock()
        self.activa = False
        self.huella_obsoleta = False
        self.cola = queue.Queue()

    # Control de ritmo: unas pocas líneas seguidas sin espera y después una cada 2 segundos,
    # para que el servidor no te desconecte por "Excess Flood".
    COSTE_LINEA = 2.0
    RAFAGA = 8.0
    # Órdenes que no esperan en la cola: el registro, la identificación y PING/PONG.
    URGENTES = {"PONG", "PING", "QUIT", "PASS", "NICK", "USER", "CAP", "AUTHENTICATE"}

    def iniciar(self):
        self.activa = True
        threading.Thread(target=self._bucle, daemon=True).start()
        threading.Thread(target=self._emisor, daemon=True).start()

    def _emisor(self):
        credito = time.monotonic()
        while True:
            linea = self.cola.get()
            if linea is None or not self.activa:
                return
            ahora = time.monotonic()
            credito = max(credito, ahora)
            espera = credito - ahora - self.RAFAGA
            if espera > 0:
                time.sleep(espera)
                if not self.activa:
                    return
            credito += self.COSTE_LINEA
            self._enviar_ya(linea)

    def _bucle(self):
        error = None
        tipo_error = None
        try:
            sock = socket.create_connection((self.host, self.puerto), timeout=20)
            if self.usar_ssl:
                if self.al_fase:
                    wx.CallAfter(self.al_fase, self, "Servidor encontrado. Negociando el cifrado...")
                try:
                    sock = envolver_tls(sock, self.host, self.verificar, self.huella, self.nombre_cert)
                except (ssl.SSLCertVerificationError, CertificadoCambiado) as e:
                    renovado = None
                    if isinstance(e, CertificadoCambiado):
                        # El certificado recordado ha cambiado. Si el nuevo se verifica por
                        # completo (renovación normal), se usa y se olvida el antiguo.
                        renovado = conectar_verificado(self.host, self.puerto, self.nombre_cert)
                    if renovado is None:
                        if self.activa:
                            self.info_cert = analizar_certificado(self.host, self.puerto, e)
                        raise e
                    sock = renovado
                    self.huella_obsoleta = True
            sock.settimeout(240)
            self.sock = sock
            wx.CallAfter(self.al_estado, self, "conectado", None)
            buf = b""
            esperando_respuesta = False
            while self.activa:
                try:
                    datos = sock.recv(4096)
                except socket.timeout:
                    if esperando_respuesta:
                        raise ConnectionError("El servidor no responde")
                    esperando_respuesta = True
                    self.enviar("PING :" + self.host)
                    continue
                if not datos:
                    break
                esperando_respuesta = False
                buf += datos
                *lineas, buf = buf.split(b"\n")
                if len(buf) > 65536:
                    raise ConnectionError("el servidor envía datos sin sentido")
                for cruda in lineas:
                    cruda = cruda.rstrip(b"\r")
                    if not cruda:
                        continue
                    try:
                        linea = cruda.decode("utf-8")
                    except UnicodeDecodeError:
                        linea = cruda.decode("latin-1")
                    if linea.startswith("PING"):
                        self.enviar("PONG" + linea[4:])
                        continue
                    wx.CallAfter(self.al_recibir, self, linea)
        except Exception as e:
            if self.activa:
                error = describir_error(e)
                if self.sock is None:
                    if isinstance(e, CertificadoCambiado):
                        tipo_error = "huella"
                    elif isinstance(e, ssl.SSLCertVerificationError):
                        tipo_error = "certificado"
                    elif isinstance(e, ssl.SSLError):
                        tipo_error = "ssl"
        finally:
            self._cerrar_socket()
            wx.CallAfter(self.al_estado, self, "desconectado", error, tipo_error)

    def enviar(self, linea, urgente=False):
        """Envía una línea. Las normales pasan por la cola con control de ritmo."""
        if not self.sock:
            return False
        orden = linea.split(" ", 1)[0].upper()
        if urgente or orden in self.URGENTES:
            return self._enviar_ya(linea)
        self.cola.put(linea)
        return True

    def _enviar_ya(self, linea):
        sock = self.sock
        if not sock:
            return False
        datos = (linea.replace("\r", " ").replace("\n", " ") + "\r\n").encode("utf-8")
        try:
            with self.lock:
                sock.sendall(datos)
            return True
        except OSError:
            return False

    def ip_local(self):
        try:
            return self.sock.getsockname()[0]
        except (OSError, AttributeError):
            return "127.0.0.1"

    def cerrar(self, mensaje=None):
        if mensaje:
            self.enviar("QUIT :" + mensaje, urgente=True)
        self.activa = False
        self._cerrar_socket()

    def _cerrar_socket(self):
        self.cola.put(None)  # detiene el hilo emisor
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Modelo de ventanas (servidor, canales y privados)
# ---------------------------------------------------------------------------

class Ventana:
    def __init__(self, nombre, tipo):
        self.nombre = nombre
        self.tipo = tipo            # "servidor", "canal" o "privado"
        self.lineas = []            # lista de (momento, texto)
        self.usuarios = {}          # apodo en minúsculas -> [rango, apodo]
        self.sin_leer = 0
        self.tema = ""
        self.unido = False
        self.reunir = False         # volver a entrar al reconectar

    def etiqueta(self):
        if self.tipo == "servidor":
            texto = "Servidor " + self.nombre
        elif self.tipo == "privado":
            texto = "Privado con " + self.nombre
        else:
            texto = self.nombre
            if not self.unido:
                texto += " (fuera del canal)"
        if self.sin_leer:
            texto += ", %d sin leer" % self.sin_leer
        return texto


# ---------------------------------------------------------------------------
# Diálogos
# ---------------------------------------------------------------------------

def _botones_aceptar(dialogo, texto_ok="&Aceptar"):
    botones = wx.StdDialogButtonSizer()
    ok = wx.Button(dialogo, wx.ID_OK, texto_ok)
    ok.SetDefault()
    botones.AddButton(ok)
    botones.AddButton(wx.Button(dialogo, wx.ID_CANCEL, "Cancelar"))
    botones.Realize()
    return botones, ok


class DialogoConexion(wx.Dialog):
    def __init__(self, padre, cfg):
        super().__init__(padre, title="Conectar a un servidor IRC")
        self.cfg = cfg
        self.campos = {}
        principal = wx.BoxSizer(wx.VERTICAL)
        rejilla = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        rejilla.AddGrowableCol(1)

        rejilla.Add(wx.StaticText(self, label="&Red:"), 0, wx.ALIGN_CENTER_VERTICAL)
        nombres = sorted(set(REDES_PREDEFINIDAS) | set(cfg["redes"]), key=str.lower)
        self.combo_red = wx.ComboBox(self, value=cfg.get("red", ""), choices=nombres,
                                     style=wx.CB_DROPDOWN, size=(320, -1))
        self.combo_red.Bind(wx.EVT_COMBOBOX, self.al_elegir_red)
        rejilla.Add(self.combo_red, 1, wx.EXPAND)

        def campo(etiqueta, clave, estilo=0):
            rejilla.Add(wx.StaticText(self, label=etiqueta), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(self, style=estilo, size=(320, -1))
            rejilla.Add(ctrl, 1, wx.EXPAND)
            self.campos[clave] = ctrl

        campo("&Servidor:", "servidor")
        campo("&Puerto:", "puerto")
        campo("&Apodo:", "apodo")
        campo("Apodo a&lternativo:", "apodo_alt")
        campo("&Nombre real:", "nombre_real")
        rejilla.Add(wx.StaticText(self, label="Método de i&dentificación del apodo:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.metodo = wx.Choice(self, choices=[texto for _, texto in METODOS_IDENT])
        rejilla.Add(self.metodo, 1, wx.EXPAND)
        campo("C&ontraseña del apodo:", "clave", wx.TE_PASSWORD)
        campo("Canales al &entrar, separados por comas (con clave: #canal clave):", "canales")
        campo("Nombre del certi&ficado (normalmente vacío):", "nombre_cert")
        principal.Add(rejilla, 0, wx.EXPAND | wx.ALL, 10)

        principal.Add(wx.StaticText(self, label="Órdenes automá&ticas al conectar, una por línea:"),
                      0, wx.LEFT | wx.RIGHT, 10)
        self.ordenes = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 70))
        principal.Add(self.ordenes, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.chk_ssl = wx.CheckBox(self, label="Usar conexión c&ifrada (SSL/TLS)")
        self.chk_ssl.Bind(wx.EVT_CHECKBOX, self.al_cambiar_ssl)
        self.chk_verificar = wx.CheckBox(self, label="&Verificar el certificado del servidor")
        self.chk_reconectar = wx.CheckBox(self, label="Reconectar a&utomáticamente si se corta")
        for chk in (self.chk_ssl, self.chk_verificar, self.chk_reconectar):
            principal.Add(chk, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        botones, ok = _botones_aceptar(self, "&Conectar")
        principal.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        ok.Bind(wx.EVT_BUTTON, self.al_aceptar)

        self.cargar_valores(cfg)
        self.SetSizerAndFit(principal)
        self.CentreOnParent()
        (self.combo_red if cfg.get("apodo") else self.campos["apodo"]).SetFocus()

    def cargar_valores(self, datos):
        for clave, ctrl in self.campos.items():
            ctrl.SetValue(str(datos.get(clave, "")))
        claves = [c for c, _ in METODOS_IDENT]
        metodo = datos.get("metodo_ident", "ninguno")
        self.metodo.SetSelection(claves.index(metodo) if metodo in claves else 0)
        self.ordenes.SetValue(datos.get("ordenes", ""))
        self.chk_ssl.SetValue(bool(datos.get("ssl")))
        self.chk_verificar.SetValue(bool(datos.get("verificar_cert", True)))
        self.chk_reconectar.SetValue(bool(datos.get("reconectar", True)))

    def al_elegir_red(self, ev):
        nombre = self.combo_red.GetValue()
        datos = {k: CONFIG_DEFECTO[k] for k in CAMPOS_RED}
        datos.update(REDES_PREDEFINIDAS.get(nombre, {}))
        datos.update(self.cfg["redes"].get(nombre, {}))
        if not datos.get("apodo"):
            datos["apodo"] = self.campos["apodo"].GetValue()
        self.cargar_valores(datos)

    def al_cambiar_ssl(self, ev):
        cifrado = self.chk_ssl.GetValue()
        puerto = self.campos["puerto"]
        servidor = self.campos["servidor"]
        if cifrado and puerto.GetValue().strip() == "6667":
            puerto.SetValue("6697")
        elif not cifrado and puerto.GetValue().strip() == "6697":
            puerto.SetValue("6667")
        # Chat Hispano usa un servidor distinto para la conexión cifrada.
        host = servidor.GetValue().strip().lower()
        nombre_cert = self.campos["nombre_cert"]
        if cifrado and host in ("irc.chathispano.com", "ssl.chathispano.com", "chatmovil.chathispano.com"):
            servidor.SetValue("ssl.chathispano.com")
            nombre_cert.SetValue("chatmovil.chathispano.com")
        elif not cifrado and host in ("ssl.chathispano.com", "chatmovil.chathispano.com"):
            servidor.SetValue("irc.chathispano.com")
            nombre_cert.SetValue("")

    def _error(self, mensaje, ctrl):
        wx.MessageBox(mensaje, "Revisa los datos", wx.OK | wx.ICON_WARNING, self)
        ctrl.SetFocus()

    def al_aceptar(self, ev):
        v = {clave: ctrl.GetValue().strip() for clave, ctrl in self.campos.items()}
        if not v["servidor"]:
            return self._error("Escribe la dirección del servidor.", self.campos["servidor"])
        if not v["puerto"].isdigit() or not 0 < int(v["puerto"]) < 65536:
            return self._error("El puerto debe ser un número, por ejemplo 6697.", self.campos["puerto"])
        if not v["apodo"] or " " in v["apodo"] or ":" in v["apodo"]:
            return self._error("Escribe un apodo sin espacios ni dos puntos. La contraseña va en su propio campo.",
                               self.campos["apodo"])
        if " " in v["apodo_alt"]:
            return self._error("El apodo alternativo no puede tener espacios.", self.campos["apodo_alt"])
        if self.metodo.GetSelection() > 0 and not self.campos["clave"].GetValue():
            return self._error("Has elegido un método de identificación, pero falta la contraseña. "
                               "Escríbela o elige el método Ninguna.", self.campos["clave"])
        if self.metodo.GetSelection() > 0 and not (self.chk_ssl.GetValue() and self.chk_verificar.GetValue()):
            if not self.chk_ssl.GetValue():
                motivo = ("La conexión no va cifrada: tu contraseña viajará a la vista de cualquiera "
                          "que comparta tu red, por ejemplo en una wifi pública.")
            else:
                motivo = ("No se va a verificar el certificado del servidor: alguien podría hacerse pasar "
                          "por él y quedarse con tu contraseña.")
            dlg = wx.MessageDialog(self, motivo + "\n\n¿Quieres conectar y enviar la contraseña de todos modos?",
                                   "Tu contraseña no va protegida",
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            dlg.SetYesNoLabels("&Conectar de todos modos", "&Volver")
            seguir = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if not seguir:
                (self.chk_ssl if not self.chk_ssl.GetValue() else self.chk_verificar).SetFocus()
                return
        self.EndModal(wx.ID_OK)

    def valores(self):
        v = {clave: ctrl.GetValue().strip() for clave, ctrl in self.campos.items()}
        v["clave"] = self.campos["clave"].GetValue()
        v["puerto"] = int(v["puerto"])
        v["metodo_ident"] = METODOS_IDENT[max(0, self.metodo.GetSelection())][0]
        v["ordenes"] = self.ordenes.GetValue().strip()
        v["ssl"] = self.chk_ssl.GetValue()
        v["verificar_cert"] = self.chk_verificar.GetValue()
        v["reconectar"] = self.chk_reconectar.GetValue()
        v["red"] = self.combo_red.GetValue().strip() or v["servidor"]
        return v


class DialogoTexto(wx.Dialog):
    def __init__(self, padre, titulo, texto):
        super().__init__(padre, title=titulo, size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        s = wx.BoxSizer(wx.VERTICAL)
        ctrl = wx.TextCtrl(self, value=texto, style=wx.TE_MULTILINE | wx.TE_READONLY)
        s.Add(ctrl, 1, wx.EXPAND | wx.ALL, 8)
        boton = wx.Button(self, wx.ID_CLOSE, "&Cerrar")
        boton.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        s.Add(boton, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetEscapeId(wx.ID_CLOSE)
        self.SetSizer(s)
        self.CentreOnParent()
        ctrl.SetFocus()
        ctrl.SetInsertionPoint(0)


class DialogoCertificado(wx.Dialog):
    def __init__(self, padre, servidor, info, tipo):
        super().__init__(padre, title="Certificado no verificado", size=(640, 480),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        alternativa = info.get("alternativa")
        if alternativa:
            intro = ("El certificado de %s es auténtico y válido, pero está emitido para el nombre %s. "
                     "Comprobándolo con ese nombre, la verificación es completa y no hace falta aceptar nada. "
                     "Pulsa «Verificar con %s» para guardarlo y conectar." % (servidor, alternativa, alternativa))
        elif tipo == "huella":
            intro = ("¡Atención! El certificado de %s ha cambiado desde que decidiste confiar en él. "
                     "Puede ser una renovación normal del certificado, o que alguien se esté haciendo pasar "
                     "por el servidor. Si no estás seguro, no conectes y pregunta en la web de la red." % servidor)
        else:
            intro = ("No se pudo comprobar que %s sea quien dice ser. Si confías en este certificado, "
                     "AccesIRC lo recordará y solo aceptará exactamente este certificado: "
                     "si algún día cambia, te avisará antes de enviar tu contraseña." % servidor)
        detalles = "Mensaje exacto: %s\n%s\n\n%s" % (info["mensaje"], info["motivo"], info["detalles"])
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label=intro), 0, wx.ALL, 8)
        s.Add(wx.StaticText(self, label="&Detalles del certificado (se pueden copiar):"), 0, wx.LEFT | wx.RIGHT, 8)
        texto = wx.TextCtrl(self, value=detalles, style=wx.TE_MULTILINE | wx.TE_READONLY)
        s.Add(texto, 1, wx.EXPAND | wx.ALL, 8)
        fila = wx.BoxSizer(wx.HORIZONTAL)
        if alternativa:
            usar = wx.Button(self, wx.ID_APPLY, "&Verificar con %s" % alternativa)
            usar.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_APPLY))
            fila.Add(usar, 0, wx.ALL, 4)
        confiar = wx.Button(self, wx.ID_YES, "&Confiar en este certificado")
        confiar.Enable(bool(info["huella"]))
        confiar.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES))
        no = wx.Button(self, wx.ID_NO, "&No conectar")
        no.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_NO))
        fila.Add(confiar, 0, wx.ALL, 4)
        fila.Add(no, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
        self.SetEscapeId(wx.ID_NO)
        self.SetSizer(s)
        self.CentreOnParent()
        if alternativa:
            usar.SetDefault()
            usar.SetFocus()
        else:
            texto.SetFocus()
            texto.SetInsertionPoint(0)


class DialogoSonidos(wx.Dialog):
    def __init__(self, padre, principal):
        super().__init__(padre, title="Configurar sonidos", size=(620, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.principal = principal
        self.cfg = principal.cfg
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label="&Eventos y su sonido:"), 0, wx.LEFT | wx.TOP, 8)
        self.lista = wx.ListBox(self, choices=[self._texto(i) for i in range(len(EVENTOS_SONIDO))])
        self.lista.SetSelection(0)
        s.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
        s.Add(wx.StaticText(self, label=(
            "Solo se admiten archivos WAV. También puedes copiar archivos WAV a la carpeta de sonidos "
            "con el nombre del evento, por ejemplo privado.wav, mencion.wav o entrada.wav.")),
            0, wx.LEFT | wx.RIGHT, 8)
        fila = wx.WrapSizer(wx.HORIZONTAL)
        for texto, accion in (("E&legir archivo WAV...", self.elegir),
                              ("&Probar", self.probar),
                              ("Sonido por &defecto", self.por_defecto),
                              ("&Silenciar este evento", self.silenciar),
                              ("Abrir la carpeta de s&onidos", self.abrir_carpeta)):
            b = wx.Button(self, label=texto)
            b.Bind(wx.EVT_BUTTON, lambda e, a=accion: a())
            fila.Add(b, 0, wx.ALL, 4)
        cerrar = wx.Button(self, wx.ID_CLOSE, "&Cerrar")
        cerrar.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        fila.Add(cerrar, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.ALL, 4)
        self.SetEscapeId(wx.ID_CLOSE)
        self.SetSizer(s)
        self.CentreOnParent()
        self.lista.Bind(wx.EVT_KEY_DOWN, self.al_tecla)
        self.lista.SetFocus()

    def _texto(self, i):
        clave, nombre, alias = EVENTOS_SONIDO[i]
        valor = self.cfg["sonidos_eventos"].get(clave, "")
        if valor == "-":
            estado = "silenciado"
        elif valor:
            estado = os.path.basename(valor)
        elif os.path.isfile(os.path.join(DIR_SONIDOS, clave + ".wav")):
            estado = clave + ".wav de la carpeta de sonidos"
        elif alias:
            estado = "sonido de Windows"
        else:
            estado = "sin sonido"
        return "%s: %s" % (nombre, estado)

    def _actual(self):
        return max(0, self.lista.GetSelection())

    def _cambiar(self, valor):
        i = self._actual()
        clave = EVENTOS_SONIDO[i][0]
        if valor is None:
            self.cfg["sonidos_eventos"].pop(clave, None)
        else:
            self.cfg["sonidos_eventos"][clave] = valor
        guardar_config(self.cfg)
        self.lista.SetString(i, self._texto(i))
        self.lista.SetSelection(i)

    def al_tecla(self, ev):
        if ev.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.probar()
        else:
            ev.Skip()

    def elegir(self):
        dlg = wx.FileDialog(self, "Elige un sonido WAV", wildcard="Sonidos WAV (*.wav)|*.wav",
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self._cambiar(dlg.GetPath())
            self.probar()
        dlg.Destroy()
        self.lista.SetFocus()

    def probar(self):
        clave = EVENTOS_SONIDO[self._actual()][0]
        self.principal.sonar(clave, forzar=True)

    def por_defecto(self):
        self._cambiar(None)
        self.probar()

    def silenciar(self):
        self._cambiar("-")

    def abrir_carpeta(self):
        self.principal.abrir_carpeta(DIR_SONIDOS)


class DialogoAutomatizaciones(wx.Dialog):
    def __init__(self, padre, cfg):
        super().__init__(padre, title="Automatizaciones", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.cfg = cfg
        s = wx.BoxSizer(wx.VERTICAL)

        self.chk_rejoin = wx.CheckBox(self, label="&Volver a entrar en el canal si te expulsan")
        self.chk_rejoin.SetValue(cfg["rejoin"])
        self.chk_ausente = wx.CheckBox(self, label="Responder a los &privados cuando estás ausente (/away)")
        self.chk_ausente.SetValue(cfg["respuesta_ausente"])
        s.Add(self.chk_rejoin, 0, wx.ALL, 8)
        s.Add(self.chk_ausente, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        def campo(etiqueta, valor, multilinea=False):
            s.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.RIGHT, 8)
            ctrl = wx.TextCtrl(self, value=valor, size=(520, 110 if multilinea else -1),
                               style=wx.TE_MULTILINE if multilinea else 0)
            s.Add(ctrl, 1 if multilinea else 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
            return ctrl

        self.palabras = campo("Palabras que te &avisan como si te nombraran, separadas por comas:",
                              cfg["palabras_aviso"])
        self.ignorados = campo("&Ignorar a estos apodos, separados por comas:", cfg["ignorados"])
        self.respuestas = campo(
            "&Respuestas automáticas, una por línea, con el formato: texto que aparece => respuesta. "
            "Puedes usar $nick, $canal y $yo. Si la respuesta empieza por barra, se ejecuta como orden:",
            cfg["respuestas"], multilinea=True)

        botones, ok = _botones_aceptar(self)
        s.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizerAndFit(s)
        self.CentreOnParent()
        self.chk_rejoin.SetFocus()

    def guardar(self):
        self.cfg["rejoin"] = self.chk_rejoin.GetValue()
        self.cfg["respuesta_ausente"] = self.chk_ausente.GetValue()
        self.cfg["palabras_aviso"] = self.palabras.GetValue().strip()
        self.cfg["ignorados"] = self.ignorados.GetValue().strip()
        self.cfg["respuestas"] = self.respuestas.GetValue().strip()


class DialogoOpcionesDCC(wx.Dialog):
    def __init__(self, padre, cfg):
        super().__init__(padre, title="Opciones de transferencia de archivos (DCC)")
        self.cfg = cfg
        s = wx.BoxSizer(wx.VERTICAL)

        s.Add(wx.StaticText(self, label="&Carpeta donde se guardan los archivos recibidos:"), 0, wx.LEFT | wx.TOP, 8)
        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.carpeta = wx.TextCtrl(self, value=cfg["carpeta_descargas"] or DESCARGAS_DEFECTO, size=(380, -1))
        examinar = wx.Button(self, label="E&xaminar...")
        examinar.Bind(wx.EVT_BUTTON, self.al_examinar)
        fila.Add(self.carpeta, 1, wx.EXPAND | wx.RIGHT, 6)
        fila.Add(examinar, 0)
        s.Add(fila, 0, wx.EXPAND | wx.ALL, 8)

        self.chk_auto = wx.CheckBox(self, label="Averiguar mi IP pública &automáticamente (consulta api.ipify.org)")
        self.chk_auto.SetValue(cfg["dcc_ip_auto"])
        s.Add(self.chk_auto, 0, wx.ALL, 8)
        s.Add(wx.StaticText(self, label="&IP pública fija (déjala vacía si no sabes cuál es):"), 0, wx.LEFT, 8)
        self.ip = wx.TextCtrl(self, value=cfg["dcc_ip"])
        s.Add(self.ip, 0, wx.EXPAND | wx.ALL, 8)
        s.Add(wx.StaticText(self, label="&Puertos para enviar archivos, por ejemplo 5000-5010:"), 0, wx.LEFT, 8)
        self.puertos = wx.TextCtrl(self, value=cfg["dcc_puertos"])
        s.Add(self.puertos, 0, wx.EXPAND | wx.ALL, 8)
        self.chk_pasivo = wx.CheckBox(self, label="Enviar en modo pa&sivo (útil si tu router no tiene puertos abiertos)")
        self.chk_pasivo.SetValue(cfg["dcc_pasivo"])
        s.Add(self.chk_pasivo, 0, wx.ALL, 8)

        botones, ok = _botones_aceptar(self)
        ok.Bind(wx.EVT_BUTTON, self.al_aceptar)
        s.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizerAndFit(s)
        self.CentreOnParent()
        self.carpeta.SetFocus()

    def al_examinar(self, ev):
        dlg = wx.DirDialog(self, "Elige la carpeta para los archivos recibidos", self.carpeta.GetValue())
        if dlg.ShowModal() == wx.ID_OK:
            self.carpeta.SetValue(dlg.GetPath())
        dlg.Destroy()
        self.carpeta.SetFocus()

    def al_aceptar(self, ev):
        ip = self.ip.GetValue().strip()
        if ip:
            try:
                socket.inet_aton(ip)
            except OSError:
                wx.MessageBox("La IP debe tener el formato 85.12.34.56.", "Revisa los datos", wx.OK | wx.ICON_WARNING, self)
                self.ip.SetFocus()
                return
        if not re.match(r"^\s*\d{1,5}\s*(-\s*\d{1,5})?\s*$", self.puertos.GetValue()):
            wx.MessageBox("Escribe un puerto o un rango, por ejemplo 5000-5010.", "Revisa los datos",
                          wx.OK | wx.ICON_WARNING, self)
            self.puertos.SetFocus()
            return
        self.EndModal(wx.ID_OK)

    def guardar(self):
        carpeta = self.carpeta.GetValue().strip()
        self.cfg["carpeta_descargas"] = "" if carpeta == DESCARGAS_DEFECTO else carpeta
        self.cfg["dcc_ip_auto"] = self.chk_auto.GetValue()
        self.cfg["dcc_ip"] = self.ip.GetValue().strip()
        self.cfg["dcc_puertos"] = self.puertos.GetValue().strip()
        self.cfg["dcc_pasivo"] = self.chk_pasivo.GetValue()


class DialogoActualizacion(wx.Dialog):
    """Avisa de una versión nueva. Devuelve wx.ID_OK (actualizar o abrir la página),
    wx.ID_IGNORE (omitir esta versión) o wx.ID_CANCEL (más tarde)."""

    def __init__(self, padre, info, puede_instalar):
        super().__init__(padre, title="Hay una versión nueva de AccesIRC", size=(640, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        if puede_instalar:
            accion = ("Pulsa «Actualizar ahora»: AccesIRC descargará la nueva versión, se cerrará, "
                      "se instalará y se volverá a abrir solo. Tu configuración se conserva.")
        else:
            accion = ("Pulsa «Abrir la página de descarga» para bajarla. Si usas el instalador, "
                      "las próximas versiones se instalarán solas.")
        texto = "Está disponible AccesIRC %s. Tienes la %s.\n%s\n\nNOVEDADES\n\n%s" % (
            info["version"], VERSION, accion, info["notas"] or "Sin descripción.")
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label="&Información de la versión nueva:"), 0, wx.LEFT | wx.TOP, 8)
        ctrl = wx.TextCtrl(self, value=texto, style=wx.TE_MULTILINE | wx.TE_READONLY)
        s.Add(ctrl, 1, wx.EXPAND | wx.ALL, 8)
        fila = wx.BoxSizer(wx.HORIZONTAL)
        principal = wx.Button(self, wx.ID_OK, "&Actualizar ahora" if puede_instalar
                              else "&Abrir la página de descarga")
        omitir = wx.Button(self, wx.ID_IGNORE, "&Omitir esta versión")
        tarde = wx.Button(self, wx.ID_CANCEL, "&Más tarde")
        for boton in (principal, omitir, tarde):
            boton.Bind(wx.EVT_BUTTON, lambda e, i=boton.GetId(): self.EndModal(i))
            fila.Add(boton, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
        principal.SetDefault()
        self.SetEscapeId(wx.ID_CANCEL)
        self.SetSizer(s)
        self.CentreOnParent()
        ctrl.SetFocus()
        ctrl.SetInsertionPoint(0)


class DialogoTransferencias(wx.Dialog):
    def __init__(self, padre, principal):
        super().__init__(padre, title="Transferencias de archivos", size=(640, 400),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.principal = principal
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label="&Transferencias, de la más reciente a la más antigua:"), 0, wx.LEFT | wx.TOP, 8)
        self.lista = wx.ListBox(self)
        s.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
        fila = wx.WrapSizer(wx.HORIZONTAL)
        for texto, accion in (("A&ctualizar", self.actualizar),
                              ("Ca&ncelar la transferencia", self.cancelar),
                              ("&Abrir la carpeta de descargas", self.abrir_carpeta)):
            b = wx.Button(self, label=texto)
            b.Bind(wx.EVT_BUTTON, lambda e, a=accion: a())
            fila.Add(b, 0, wx.ALL, 4)
        cerrar = wx.Button(self, wx.ID_CLOSE, "Ce&rrar")
        cerrar.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        fila.Add(cerrar, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.ALL, 4)
        self.SetEscapeId(wx.ID_CLOSE)
        self.SetSizer(s)
        self.CentreOnParent()
        self.actualizar()
        self.lista.SetFocus()

    def _orden(self):
        return list(reversed(self.principal.transferencias))

    def actualizar(self):
        textos = [t.descripcion() for t in self._orden()] or ["No hay transferencias"]
        sel = max(0, self.lista.GetSelection())
        self.lista.Set(textos)
        self.lista.SetSelection(min(sel, len(textos) - 1))

    def cancelar(self):
        orden = self._orden()
        sel = self.lista.GetSelection()
        if not 0 <= sel < len(orden):
            return
        t = orden[sel]
        if t.activa():
            self.principal.dcc_cancelar(t)
        else:
            self.principal.hablar("Esa transferencia ya ha terminado", True)
        self.actualizar()
        self.lista.SetFocus()

    def abrir_carpeta(self):
        self.principal.abrir_carpeta(self.principal.carpeta_descargas())


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class Principal(wx.Frame):
    OPCIONES = [
        # clave, texto del menú, atajo, aviso al activar, aviso al desactivar
        ("voz", "&Voz activada", "F2", "Voz activada", "Voz silenciada"),
        ("leer_propios", "Leer &mis propios mensajes", "",
         "Se leerán tus mensajes: has dicho...", "No se leerán tus mensajes"),
        ("leer_todo", "&Leer mensajes de todas las ventanas", "F3",
         "Se leerán los mensajes de todas las ventanas", "Solo se leerá la ventana actual"),
        ("anunciar_entradas", "&Anunciar entradas y salidas", "F4",
         "Se anunciarán las entradas y salidas", "No se anunciarán las entradas y salidas"),
        ("sonidos", "&Sonidos", "F5", "Sonidos activados", "Sonidos desactivados"),
        ("mostrar_hora", "Mostrar la &hora en el historial", "",
         "Hora visible en el historial", "Hora oculta en el historial"),
        ("buscar_actualizaciones", "Buscar act&ualizaciones al iniciar", "",
         "Se buscarán actualizaciones al iniciar", "No se buscarán actualizaciones al iniciar"),
        ("guardar_registros", "&Guardar registros de conversación", "",
         "Se guardarán los registros", "No se guardarán los registros"),
    ]

    def __init__(self):
        super().__init__(None, title=NOMBRE_APP, size=(950, 650))
        self.cfg = cargar_config()
        self.voz = Voz()
        self.voz.activa = self.cfg["voz"]
        self.conexion = None
        self.registrado = False
        self.cierre_voluntario = False
        self.apodo = self.cfg["apodo"]
        self.servidor_previo = ""
        self.temporizador = None
        self.ventanas = [Ventana(self.cfg["servidor"], "servidor")]
        self.actual = 0
        self.lineas_mostradas = 0
        self.historial_entrada = []
        self.pos_historial = 0
        self.nicks_listados = []
        self.uniones_manuales = set()
        self.nombres_en_curso = set()
        self.mostrar_nombres = set()
        self.transferencias = []
        self.dcc_pasivos = {}
        self.ausente = None
        self.avisados_ausencia = set()
        self.ultimas_respuestas = {}
        self.intentos_apodo = 0
        self.ultimo_ctcp = 0.0
        self.names_pendientes = set()
        self.expulsiones = {}
        self.dcc_preguntando = False
        self.hosts_usuarios = {}
        self.userhost_pedidos = set()
        self.actualizando = False
        self.mensaje_salida = "AccesIRC"
        self.claves_canal = {}      # canal en minúsculas -> clave, para volver a entrar al reconectar

        self._crear_menu()
        self._crear_controles()
        self.Bind(wx.EVT_CHAR_HOOK, self.al_tecla_global)
        self.Bind(wx.EVT_CLOSE, self.al_cerrar)
        self.cambiar_ventana(0, anunciar=False)
        self.Show()
        self.entrada.SetFocus()
        wx.CallAfter(self.dialogo_conectar)
        limpiar_actualizaciones_antiguas()
        if (self.cfg["buscar_actualizaciones"]
                and time.time() - float(self.cfg.get("ultima_comprobacion") or 0) > INTERVALO_ACTUALIZACION):
            wx.CallLater(10000, self.comprobar_actualizaciones, False)

    # ----- construcción de la interfaz -----

    def _crear_menu(self):
        barra = wx.MenuBar()

        m = wx.Menu()
        self._item(m, "&Conectar...\tCtrl+O", lambda e: self.dialogo_conectar())
        self._item(m, "&Desconectar\tCtrl+D", lambda e: self.desconectar("Hasta luego"))
        m.AppendSeparator()
        self._item(m, "&Unirse a un canal...\tCtrl+J", lambda e: self.dialogo_unirse())
        self._item(m, "Conversación &privada...\tCtrl+P", lambda e: self.dialogo_privado())
        self._item(m, "Cerrar la &ventana actual\tCtrl+W", lambda e: self.cerrar_ventana())
        m.AppendSeparator()
        self._item(m, "Enviar un &archivo...\tCtrl+Shift+E", lambda e: self.dcc_enviar())
        self._item(m, "Trans&ferencias de archivos\tCtrl+Shift+T", lambda e: self.dialogo_transferencias())
        m.AppendSeparator()
        self._item(m, "Leer el &tema del canal\tCtrl+T", lambda e: self.leer_tema())
        self._item(m, "&Estado de la conexión\tCtrl+E", lambda e: self.leer_estado())
        m.AppendSeparator()
        self._item(m, "&Salir\tCtrl+Q", lambda e: self.Close())
        barra.Append(m, "&Servidor")

        m = wx.Menu()
        for clave, texto, atajo, si, no in self.OPCIONES:
            item = m.AppendCheckItem(wx.ID_ANY, texto + ("\t" + atajo if atajo else ""))
            item.Check(bool(self.cfg[clave]))
            self.Bind(wx.EVT_MENU, lambda e, c=clave, s=si, n=no: self.alternar_opcion(c, e.IsChecked(), s, n), item)
        m.AppendSeparator()
        self._item(m, "C&onfigurar sonidos...", lambda e: self.dialogo_sonidos())
        self._item(m, "Au&tomatizaciones...", lambda e: self.dialogo_automatizaciones())
        self._item(m, "Opciones de &DCC (archivos)...", lambda e: self.dialogo_opciones_dcc())
        m.AppendSeparator()
        self._item(m, "&Probar la voz\tCtrl+Shift+V", lambda e: self.probar_voz())
        self._item(m, "Abrir la &carpeta de registros", lambda e: self.abrir_carpeta(DIR_REGISTROS))
        barra.Append(m, "&Opciones")

        m = wx.Menu()
        self._item(m, "&Atajos de teclado y órdenes\tF1", lambda e: self.mostrar_ayuda())
        self._item(m, "&Diagnóstico de la conexión cifrada", lambda e: self.diagnostico_tls())
        self._item(m, "&Buscar actualizaciones...", lambda e: self.comprobar_actualizaciones(True))
        self._item(m, "Acerca &de AccesIRC", lambda e: wx.MessageBox(
            "AccesIRC %s\nCliente IRC accesible para lectores de pantalla." % VERSION,
            "Acerca de AccesIRC", wx.OK | wx.ICON_INFORMATION, self))
        barra.Append(m, "A&yuda")

        self.SetMenuBar(barra)

    def _item(self, menu, texto, accion):
        item = menu.Append(wx.ID_ANY, texto)
        self.Bind(wx.EVT_MENU, accion, item)
        return item

    def _crear_controles(self):
        # Cada etiqueta se crea justo antes de su control: así NVDA lee el nombre
        # del control al recibir el foco, y Alt + la letra subrayada lleva a él.
        panel = wx.Panel(self)
        self.panel = panel

        lbl_ventanas = wx.StaticText(panel, label="&Ventanas")
        self.lista_ventanas = wx.ListBox(panel, style=wx.LB_SINGLE)
        lbl_historial = wx.StaticText(panel, label="&Historial")
        self.historial = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.lbl_usuarios = wx.StaticText(panel, label="&Usuarios")
        self.lista_usuarios = wx.ListBox(panel, style=wx.LB_SINGLE)
        lbl_mensaje = wx.StaticText(panel, label="&Mensaje")
        self.entrada = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, ctrl, proporcion in ((lbl_ventanas, self.lista_ventanas, 1),
                                           (lbl_historial, self.historial, 4),
                                           (self.lbl_usuarios, self.lista_usuarios, 1)):
            col = wx.BoxSizer(wx.VERTICAL)
            col.Add(etiqueta, 0, wx.BOTTOM, 3)
            col.Add(ctrl, 1, wx.EXPAND)
            fila.Add(col, proporcion, wx.EXPAND | wx.ALL, 5)
        principal = wx.BoxSizer(wx.VERTICAL)
        principal.Add(fila, 1, wx.EXPAND)
        principal.Add(lbl_mensaje, 0, wx.LEFT | wx.RIGHT, 8)
        principal.Add(self.entrada, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(principal)

        self.lista_ventanas.Bind(wx.EVT_LISTBOX, self.al_elegir_ventana)
        self.lista_usuarios.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.privado_con_seleccionado())
        self.lista_usuarios.Bind(wx.EVT_KEY_DOWN, self.al_tecla_usuarios)
        self.lista_usuarios.Bind(wx.EVT_CONTEXT_MENU, self.menu_usuario)
        self.entrada.Bind(wx.EVT_TEXT_ENTER, self.al_enviar)
        self.entrada.Bind(wx.EVT_KEY_DOWN, self.al_tecla_entrada)

    # ----- utilidades de interfaz -----

    @property
    def ventana_actual(self):
        return self.ventanas[self.actual]

    def hablar(self, texto, interrumpir=False):
        self.voz.decir(texto, interrumpir)

    def sonar(self, evento, forzar=False):
        if not winsound or not (self.cfg["sonidos"] or forzar):
            return
        valor = self.cfg["sonidos_eventos"].get(evento, "")
        if valor == "-":
            return
        ruta = valor if valor and os.path.isfile(valor) else os.path.join(DIR_SONIDOS, evento + ".wav")
        try:
            if os.path.isfile(ruta):
                winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            alias = {c: a for c, _, a in EVENTOS_SONIDO}.get(evento)
            if alias:
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def conectado(self):
        return bool(self.conexion and self.conexion.sock and self.registrado)

    def _actualizar_titulo(self):
        estado = self.apodo if self.registrado else "sin conexión"
        self.SetTitle("%s - %s - %s" % (self.ventana_actual.nombre, estado, NOMBRE_APP))

    def _refrescar_lista(self):
        etiquetas = [v.etiqueta() for v in self.ventanas]
        lista = self.lista_ventanas
        if lista.GetCount() != len(etiquetas):
            lista.Set(etiquetas)
        else:
            for i, texto in enumerate(etiquetas):
                if lista.GetString(i) != texto:
                    lista.SetString(i, texto)
        if lista.GetSelection() != self.actual:
            lista.SetSelection(self.actual)

    def _refrescar_usuarios(self):
        v = self.ventana_actual
        if v.tipo == "canal":
            datos = sorted(v.usuarios.values(), key=lambda ru: (
                RANGOS.index(ru[0]) if ru[0] else len(RANGOS), ru[1].lower()))
        else:
            datos = []
        anterior = None
        sel = self.lista_usuarios.GetSelection()
        if 0 <= sel < len(self.nicks_listados):
            anterior = self.nicks_listados[sel].lower()
        self.nicks_listados = [apodo for _, apodo in datos]
        textos = ["%s (%s)" % (apodo, NOMBRE_RANGO[r]) if r else apodo for r, apodo in datos]
        if textos != list(self.lista_usuarios.GetStrings()):
            self.lista_usuarios.Set(textos)
            if anterior:
                for i, apodo in enumerate(self.nicks_listados):
                    if apodo.lower() == anterior:
                        self.lista_usuarios.SetSelection(i)
                        break
        etiqueta = "&Usuarios (%d)" % len(textos) if v.tipo == "canal" else "&Usuarios"
        if self.lbl_usuarios.GetLabel() != etiqueta:
            self.lbl_usuarios.SetLabel(etiqueta)
            self.panel.Layout()

    def _formatear(self, momento, texto):
        return (momento.strftime("[%H:%M] ") if self.cfg["mostrar_hora"] else "") + texto

    def _mostrar_historial(self):
        v = self.ventana_actual
        self.historial.SetValue("\n".join(self._formatear(m, t) for m, t in v.lineas))
        self.historial.SetInsertionPointEnd()
        self.lineas_mostradas = len(v.lineas)

    def _anadir_al_historial(self, momento, texto):
        h = self.historial
        linea = self._formatear(momento, texto)
        con_foco = wx.Window.FindFocus() is h
        pos = h.GetInsertionPoint() if con_foco else None
        al_final = pos is not None and pos >= h.GetLastPosition()
        h.AppendText(("\n" if h.GetLastPosition() > 0 else "") + linea)
        # Si estás leyendo el historial con las flechas, no te movemos el cursor.
        if pos is not None and not al_final:
            h.SetInsertionPoint(pos)
        self.lineas_mostradas += 1
        if self.lineas_mostradas > MAX_LINEAS + 300 and not con_foco:
            self._mostrar_historial()
        # Con el foco en el historial y el cursor al final, NVDA ya lee la línea nueva.
        return al_final

    def _registrar(self, v, momento, texto):
        if not self.cfg["guardar_registros"]:
            return
        try:
            carpeta = os.path.join(DIR_REGISTROS, nombre_seguro(self.cfg["servidor"]))
            os.makedirs(carpeta, exist_ok=True)
            if v.tipo == "servidor":
                archivo = "servidor"
            elif v.tipo == "privado":
                archivo = "privado_" + nombre_seguro(v.nombre)
            else:
                archivo = nombre_seguro(v.nombre)
            with open(os.path.join(carpeta, archivo + ".log"), "a", encoding="utf-8") as f:
                f.write(momento.strftime("%Y-%m-%d %H:%M:%S ") + texto + "\n")
        except OSError:
            pass

    def agregar(self, v, texto, tipo="info", hablar=True, evento=None, voz=None):
        """Añade una línea a una ventana y decide si se lee en voz alta y qué suena.

        tipo: "mensaje", "privado", "resalte" (te nombran), "propio",
              "entrada" (entradas y salidas) o "info".
        evento: sonido a reproducir; si no se indica, se deduce del tipo.
        voz: lo que dice el lector, si ha de ser distinto de lo que se escribe en el historial
             (por ejemplo «Dani dice: hola» para la línea «Dani: hola»).
        """
        hablado = voz or texto
        momento = datetime.datetime.now()
        v.lineas.append((momento, texto))
        if len(v.lineas) > MAX_LINEAS:
            del v.lineas[:len(v.lineas) - MAX_LINEAS]
        self._registrar(v, momento, texto)

        es_actual = v is self.ventana_actual
        lo_lee_nvda = False
        if es_actual:
            lo_lee_nvda = self._anadir_al_historial(momento, texto) and self.voz.motor() == "NVDA"
        elif tipo in ("mensaje", "privado", "resalte"):
            v.sin_leer += 1
            self._refrescar_lista()

        evento = evento or {"privado": "privado", "resalte": "mencion", "mensaje": "mensaje"}.get(tipo)
        if evento:
            self.sonar(evento)

        if tipo == "propio":
            # Lo que escribes tú: «Has dicho: ...» o, con /me, «charlie20 saluda».
            if hablar and self.cfg["leer_propios"] and not lo_lee_nvda:
                self.hablar(hablado)
            return
        if tipo == "entrada" and not self.cfg["anunciar_entradas"]:
            hablar = False
        app_activa = self.IsActive()
        if es_actual and app_activa and lo_lee_nvda:
            hablar = False
        if tipo in ("privado", "resalte"):
            if es_actual and app_activa:
                if not lo_lee_nvda:
                    self.hablar(hablado)
            elif tipo == "privado":
                self.hablar("Privado, " + hablado)
            else:
                self.hablar("%s, %s" % (v.nombre, hablado))
        elif hablar:
            if es_actual and app_activa:
                self.hablar(hablado)
            elif self.cfg["leer_todo"] and tipo == "mensaje":
                self.hablar("%s, %s" % (v.nombre, hablado))

    def obtener_ventana(self, nombre, tipo, crear=True):
        clave = nombre.lower()
        for v in self.ventanas:
            if v.tipo == tipo and v.nombre.lower() == clave:
                return v
        if not crear:
            return None
        v = Ventana(nombre, tipo)
        self.ventanas.append(v)
        self._refrescar_lista()
        return v

    def cambiar_ventana(self, indice, anunciar=True):
        if not 0 <= indice < len(self.ventanas):
            return
        self.actual = indice
        v = self.ventanas[indice]
        v.sin_leer = 0
        self._refrescar_lista()
        self._mostrar_historial()
        self._refrescar_usuarios()
        self._actualizar_titulo()
        if anunciar:
            self.hablar(v.etiqueta(), interrumpir=True)

    def abrir_carpeta(self, ruta):
        try:
            os.makedirs(ruta, exist_ok=True)
            os.startfile(ruta)
        except (AttributeError, OSError):
            self.hablar("La carpeta está en " + ruta, True)

    # ----- teclado -----

    def al_tecla_global(self, ev):
        k = ev.GetKeyCode()
        mods = ev.GetModifiers()
        if mods == wx.MOD_ALT and ord("0") <= k <= ord("9"):
            self.leer_ultimo((k - ord("0")) or 10)
        elif mods == wx.MOD_CONTROL and ord("1") <= k <= ord("9"):
            n = k - ord("1")
            if n < len(self.ventanas):
                self.cambiar_ventana(n)
            else:
                self.hablar("No hay ventana %d" % (n + 1), True)
        elif mods == wx.MOD_CONTROL and k in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN):
            self.cambiar_ventana((self.actual + 1) % len(self.ventanas))
        elif mods == wx.MOD_CONTROL and k in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP):
            self.cambiar_ventana((self.actual - 1) % len(self.ventanas))
        elif k == wx.WXK_F6 and mods in (wx.MOD_NONE, wx.MOD_SHIFT):
            self.ciclar_foco(-1 if mods == wx.MOD_SHIFT else 1)
        elif k == wx.WXK_ESCAPE and mods == wx.MOD_NONE and wx.Window.FindFocus() is not self.entrada:
            self.entrada.SetFocus()
        else:
            ev.Skip()

    def ciclar_foco(self, direccion):
        orden = [self.entrada, self.historial, self.lista_ventanas, self.lista_usuarios]
        actual = wx.Window.FindFocus()
        i = orden.index(actual) if actual in orden else -1
        orden[(i + direccion) % len(orden)].SetFocus()

    def leer_ultimo(self, n):
        lineas = self.ventana_actual.lineas
        if n > len(lineas):
            self.hablar("No hay tantos mensajes", True)
        else:
            self.hablar(lineas[-n][1], True)

    def al_tecla_entrada(self, ev):
        k = ev.GetKeyCode()
        if k in (wx.WXK_UP, wx.WXK_DOWN) and ev.GetModifiers() == wx.MOD_NONE and self.historial_entrada:
            if k == wx.WXK_UP:
                self.pos_historial = max(0, self.pos_historial - 1)
            else:
                self.pos_historial = min(len(self.historial_entrada), self.pos_historial + 1)
            texto = self.historial_entrada[self.pos_historial] if self.pos_historial < len(self.historial_entrada) else ""
            self.entrada.SetValue(texto)
            self.entrada.SetInsertionPointEnd()
            self.hablar(self._sin_clave(texto) or "En blanco", True)
        else:
            ev.Skip()

    def _sin_clave(self, texto):
        """Texto para leer en voz alta sin decir contraseñas."""
        clave = self.cfg.get("clave", "")
        if clave and clave in texto:
            texto = texto.replace(clave, "contraseña")
        return re.sub(r"(?i)\b(identify|ghost|recover|regain|release|register)\b(.*)",
                      lambda m: m.group(1) + " (contraseña oculta)", texto)

    def al_tecla_usuarios(self, ev):
        if ev.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.privado_con_seleccionado()
        else:
            ev.Skip()

    def apodo_seleccionado(self):
        sel = self.lista_usuarios.GetSelection()
        if 0 <= sel < len(self.nicks_listados):
            return self.nicks_listados[sel]
        return None

    def privado_con_seleccionado(self):
        apodo = self.apodo_seleccionado()
        if apodo:
            v = self.obtener_ventana(apodo, "privado")
            self.cambiar_ventana(self.ventanas.index(v))
            self.entrada.SetFocus()

    def menu_usuario(self, ev):
        apodo = self.apodo_seleccionado()
        if not apodo:
            return
        menu = wx.Menu()
        acciones = [
            ("Conversación &privada", self.privado_con_seleccionado),
            ("&Información (whois)", lambda: self.ejecutar_orden("whois " + apodo)),
            ("&Nombrarle en el mensaje", lambda: self._nombrar(apodo)),
            ("Enviar un &archivo", lambda: self.dcc_enviar(apodo)),
            ("I&gnorar", lambda: self.ejecutar_orden("ignore " + apodo)),
        ]
        for texto, accion in acciones:
            item = menu.Append(wx.ID_ANY, texto)
            self.Bind(wx.EVT_MENU, lambda e, a=accion: a(), item)
        self.lista_usuarios.PopupMenu(menu)
        menu.Destroy()

    def _nombrar(self, apodo):
        self.entrada.SetValue(apodo + ": " + self.entrada.GetValue())
        self.entrada.SetInsertionPointEnd()
        self.entrada.SetFocus()

    def al_elegir_ventana(self, ev):
        sel = self.lista_ventanas.GetSelection()
        if sel != wx.NOT_FOUND and sel != self.actual:
            self.cambiar_ventana(sel, anunciar=False)

    # ----- menús y diálogos -----

    def alternar_opcion(self, clave, valor, aviso_si, aviso_no):
        self.cfg[clave] = valor
        guardar_config(self.cfg)
        if clave == "voz":
            self.voz.activa = valor
        if clave == "mostrar_hora":
            self._mostrar_historial()
        self.voz.decir(aviso_si if valor else aviso_no, interrumpir=True, forzar=True)

    def probar_voz(self):
        motor = self.voz.motor()
        if motor:
            self.voz.decir("La voz funciona a través de %s." % motor, interrumpir=True, forzar=True)
        else:
            wx.MessageBox("No se ha encontrado ningún lector de pantalla para hablar. "
                          "Los detalles están en:\n" + RUTA_ERRORES,
                          "Probar la voz", wx.OK | wx.ICON_WARNING, self)

    def mostrar_ayuda(self):
        dlg = DialogoTexto(self, "Ayuda de AccesIRC", TEXTO_AYUDA)
        dlg.ShowModal()
        dlg.Destroy()

    def dialogo_conectar(self):
        dlg = DialogoConexion(self, self.cfg)
        if dlg.ShowModal() == wx.ID_OK:
            valores = dlg.valores()
            guardada = self.cfg["redes"].get(valores["red"], {})
            mismo = (str(guardada.get("servidor", "")).lower() == valores["servidor"].lower()
                     and guardada.get("puerto") == valores["puerto"])
            valores["huella"] = guardada.get("huella", "") if mismo else ""
            self.cfg.update(valores)
            self.cfg["redes"][valores["red"]] = {k: valores[k] for k in CAMPOS_RED}
            guardar_config(self.cfg)
            self.conectar()
        dlg.Destroy()

    def dialogo_sonidos(self):
        dlg = DialogoSonidos(self, self)
        dlg.ShowModal()
        dlg.Destroy()

    def dialogo_automatizaciones(self):
        dlg = DialogoAutomatizaciones(self, self.cfg)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.guardar()
            guardar_config(self.cfg)
            self.hablar("Automatizaciones guardadas", True)
        dlg.Destroy()

    def dialogo_opciones_dcc(self):
        dlg = DialogoOpcionesDCC(self, self.cfg)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.guardar()
            guardar_config(self.cfg)
            self.hablar("Opciones de transferencia guardadas", True)
        dlg.Destroy()

    def dialogo_transferencias(self):
        dlg = DialogoTransferencias(self, self)
        dlg.ShowModal()
        dlg.Destroy()

    def dialogo_unirse(self):
        dlg = wx.TextEntryDialog(self, "Nombre del canal:", "Unirse a un canal", "#")
        if dlg.ShowModal() == wx.ID_OK and dlg.GetValue().strip("# "):
            self.ejecutar_orden("join " + dlg.GetValue().strip())
        dlg.Destroy()

    def dialogo_privado(self):
        dlg = wx.TextEntryDialog(self, "Apodo de la persona:", "Conversación privada")
        if dlg.ShowModal() == wx.ID_OK and dlg.GetValue().strip():
            self.ejecutar_orden("query " + dlg.GetValue().strip())
        dlg.Destroy()

    def leer_tema(self):
        v = self.ventana_actual
        if v.tipo != "canal":
            self.hablar("Esto no es un canal", True)
        else:
            self.hablar("Tema: " + v.tema if v.tema else "Este canal no tiene tema", True)

    def leer_estado(self):
        if self.conectado():
            canales = [v.nombre for v in self.ventanas if v.tipo == "canal" and v.unido]
            texto = "Conectado a %s como %s. " % (self.cfg["red"], self.apodo)
            texto += ("En %d canales: %s." % (len(canales), ", ".join(canales))) if canales else "No estás en ningún canal."
            if self.ausente is not None:
                texto += " Estás ausente."
        elif self.conexion:
            texto = "Conectando a " + self.cfg["servidor"]
        else:
            texto = "Sin conexión. Pulsa Control O para conectar."
        activas = [t for t in self.transferencias if t.activa()]
        if activas:
            texto += " %d transferencias en curso." % len(activas)
        self.hablar(texto, True)

    def cerrar_ventana(self):
        v = self.ventana_actual
        if v.tipo == "servidor":
            self.hablar("La ventana del servidor no se puede cerrar", True)
            return
        if v.tipo == "canal" and v.unido and self.conectado():
            self.conexion.enviar("PART " + v.nombre)
        i = self.ventanas.index(v)
        self.ventanas.remove(v)
        self.actual = 0
        self.cambiar_ventana(max(0, i - 1))

    # ----- conexión -----

    def conectar(self):
        if self.temporizador:
            self.temporizador.Stop()
            self.temporizador = None
        if self.conexion:
            self.conexion.cerrar("Cambiando de servidor")
            self.conexion = None
        c = self.cfg
        if self.servidor_previo and self.servidor_previo != c["servidor"].lower():
            self.ventanas = [self.ventanas[0]]
            self.actual = 0
        self.servidor_previo = c["servidor"].lower()
        for v in self.ventanas:
            if v.tipo == "canal":
                if v.unido:
                    v.reunir = True
                v.unido = False
                v.usuarios = {}
        self.apodo = c["apodo"]
        self.registrado = False
        self.cierre_voluntario = False
        self.intentos_apodo = 0
        self.names_pendientes = set()
        self.hosts_usuarios = {}
        self.userhost_pedidos = set()
        servidor = self.ventanas[0]
        servidor.nombre = c["servidor"]
        self.cambiar_ventana(self.actual, anunciar=False)
        self.agregar(servidor, "Conectando a %s, puerto %s%s..." % (
            c["servidor"], c["puerto"], ", cifrado" if c["ssl"] else ""), hablar=False)
        self.hablar("Conectando a " + c["red"])
        self.conexion = ConexionIRC(c["servidor"], int(c["puerto"]), c["ssl"], c["verificar_cert"],
                                    self.al_recibir, self.al_estado, c.get("huella", ""),
                                    c.get("nombre_cert", "").strip(), self.al_fase)
        self.conexion.iniciar()

    def desconectar(self, mensaje="Hasta luego"):
        self.cierre_voluntario = True
        if self.temporizador:
            self.temporizador.Stop()
            self.temporizador = None
            self.hablar("Reconexión cancelada")
        if self.conexion:
            self.conexion.cerrar(mensaje)

    def enviar(self, linea):
        if self.conexion:
            self.conexion.enviar(linea)

    def _guardar_en_red(self, clave, valor):
        self.cfg[clave] = valor
        red = self.cfg["redes"].setdefault(self.cfg["red"], {k: self.cfg[k] for k in CAMPOS_RED})
        red[clave] = valor
        guardar_config(self.cfg)

    def al_fase(self, conexion, texto):
        if conexion is self.conexion:
            self.agregar(self.ventanas[0], texto, hablar=False)

    def al_estado(self, conexion, estado, error, tipo=None):
        if conexion is not self.conexion:
            return
        servidor = self.ventanas[0]
        c = self.cfg
        if estado == "conectado":
            if conexion.huella_obsoleta:
                self._guardar_en_red("huella", "")
                self.agregar(servidor, "El servidor ha renovado su certificado y el nuevo se verifica "
                             "correctamente. Ya no hace falta el certificado que aceptaste a mano.", hablar=False)
            self.agregar(servidor, "Conexión establecida. Identificándose...", hablar=False)
            usuario = re.sub(r"[^A-Za-z0-9]", "", self.apodo)[:10] or "accesirc"
            metodo, clave = c["metodo_ident"], c["clave"]
            if metodo == "sasl" and clave:
                self.enviar("CAP REQ :sasl")
            if metodo == "pass" and clave:
                self.enviar("PASS " + clave)
            if metodo == "apodo" and clave:
                self.enviar("NICK %s:%s" % (self.apodo, clave))
            else:
                self.enviar("NICK " + self.apodo)
            self.enviar("USER %s 0 * :%s" % (usuario, c["nombre_real"] or self.apodo))
            return
        # desconectado
        self.conexion = None
        self.registrado = False
        for v in self.ventanas:
            if v.tipo == "canal":
                if v.unido:
                    v.reunir = True
                v.unido = False
                v.usuarios = {}
        mensaje = "Desconectado del servidor" + (": " + error if error else ".")
        host = c["servidor"].lower()
        if "chathispano" in host and c["ssl"] and host != "ssl.chathispano.com":
            mensaje += (" Para la conexión cifrada en Chat Hispano, usa el servidor ssl.chathispano.com, "
                        "puerto 6697, con el nombre del certificado chatmovil.chathispano.com.")
        self.agregar(servidor, mensaje, hablar=False)
        self.sonar("desconectar")
        self.hablar(mensaje)
        self._refrescar_lista()
        self._refrescar_usuarios()
        self._actualizar_titulo()
        if tipo in ("certificado", "huella"):
            wx.CallAfter(self._preguntar_certificado, conexion.info_cert, tipo)
        elif tipo == "ssl":
            self.hablar("Revisa el servidor y el puerto, o desmarca la conexión cifrada.")
        elif not self.cierre_voluntario and c["reconectar"]:
            self.hablar("Reconectando en 15 segundos. Control D para cancelar.")
            self.temporizador = wx.CallLater(15000, self.conectar)

    def _preguntar_certificado(self, info, tipo):
        info = info or {"mensaje": "desconocido", "motivo": "", "huella": None, "detalles": ""}
        dlg = DialogoCertificado(self, self.cfg["servidor"], info, tipo)
        respuesta = dlg.ShowModal()
        dlg.Destroy()
        if respuesta == wx.ID_APPLY and info.get("alternativa"):
            self._guardar_en_red("nombre_cert", info["alternativa"])
            self._guardar_en_red("huella", "")
            self.hablar("El certificado se verificará con %s. Conectando." % info["alternativa"], True)
            self.conectar()
        elif respuesta == wx.ID_YES and info["huella"]:
            self._guardar_en_red("huella", info["huella"])
            self.hablar("Certificado aceptado. Conectando.", True)
            self.conectar()

    def diagnostico_tls(self):
        c = self.cfg
        self.hablar("Comprobando la conexión cifrada con %s. Espera unos segundos." % c["servidor"], True)

        def trabajo(host, puerto):
            # nombre_cert se lee del ámbito exterior
            try:
                texto = diagnosticar_tls(host, puerto, nombre_cert)
            except Exception:
                texto = "El diagnóstico ha fallado:\n" + traceback.format_exc()
            wx.CallAfter(self._mostrar_diagnostico, texto)
        nombre_cert = c.get("nombre_cert", "").strip()
        threading.Thread(target=trabajo, args=(c["servidor"], int(c["puerto"])), daemon=True).start()

    def _mostrar_diagnostico(self, texto):
        registrar_error(texto)
        dlg = DialogoTexto(self, "Diagnóstico de la conexión cifrada", texto)
        dlg.ShowModal()
        dlg.Destroy()

    def al_recibir(self, conexion, linea):
        if conexion is not self.conexion:
            return
        try:
            self.procesar(linea)
        except Exception:
            registrar_error("Error procesando: %r\n%s" % (linea, traceback.format_exc()))

    # ----- protocolo IRC -----

    def ignorados(self):
        return {x.lower() for x in lista_comas(self.cfg["ignorados"])}

    def _me_nombra(self, texto):
        palabras = [self.apodo] + [x.strip() for x in self.cfg["palabras_aviso"].split(",")]
        for palabra in palabras:
            if palabra and re.search(r"(?<![\w\-\[\]\\`^{}|])" + re.escape(palabra) + r"(?![\w\-\[\]\\`^{}|])",
                                     texto, re.IGNORECASE):
                return True
        return False

    def procesar(self, linea):
        prefijo, nick, orden, p = parsear(linea)
        servidor = self.ventanas[0]
        yo = bool(nick) and nick.lower() == self.apodo.lower()
        ultimo = limpiar_formato(p[-1]) if p else ""

        if (orden in ("PRIVMSG", "NOTICE", "INVITE") and nick and not yo and "!" in prefijo
                and nick.lower() in self.ignorados()):
            return

        if orden == "001":
            self.registrado = True
            self.apodo = p[0]
            self.agregar(servidor, ultimo, hablar=False)
            self.sonar("conectar")
            self.hablar("Conectado a %s como %s" % (self.cfg["red"], self.apodo))
            if self.cfg["metodo_ident"] == "nickserv" and self.cfg["clave"]:
                cuenta = self.cfg["apodo"]
                if cuenta and cuenta.lower() != self.apodo.lower():
                    # Has entrado con el apodo alternativo: hay que decir a qué cuenta te identificas.
                    self.enviar("PRIVMSG NickServ :IDENTIFY %s %s" % (cuenta, self.cfg["clave"]))
                else:
                    self.enviar("PRIVMSG NickServ :IDENTIFY " + self.cfg["clave"])
            if self.ausente is not None:
                # El servidor olvida la ausencia al reconectar: se vuelve a marcar.
                self.enviar("AWAY :" + self.ausente if self.ausente else "AWAY :Ausente")
            for orden_auto in self.cfg["ordenes"].splitlines():
                orden_auto = orden_auto.strip()
                if orden_auto:
                    self.ejecutar_orden(orden_auto.lstrip("/").replace("$yo", self.apodo).replace("$nick", self.apodo))
            canales = lista_canales(self.cfg["canales"])
            canales += [(v.nombre, self.claves_canal.get(v.nombre.lower(), ""))
                        for v in self.ventanas if v.tipo == "canal" and v.reunir]
            vistos = set()
            for canal, clave in canales:
                if not es_canal(canal):
                    canal = "#" + canal
                if canal.lower() not in vistos:
                    vistos.add(canal.lower())
                    if clave:
                        self.claves_canal[canal.lower()] = clave
                    self.enviar("JOIN %s %s" % (canal, clave) if clave else "JOIN " + canal)
            for v in self.ventanas:
                v.reunir = False
            self._actualizar_titulo()

        elif orden in ("432", "433"):
            if not self.registrado:
                self.intentos_apodo += 1
                alt = self.cfg["apodo_alt"]
                probar_alt = alt and self.apodo.lower() != alt.lower() and self.intentos_apodo == 1
                if probar_alt:
                    nuevo = alt
                elif orden == "433" and self.intentos_apodo <= 4:
                    nuevo = self.apodo + "_"
                else:
                    # 432: el apodo no es válido (demasiado largo o con caracteres no permitidos);
                    # añadirle "_" no lo arregla, así que se para en vez de reintentar sin fin.
                    motivo = ("no es válido en este servidor: puede ser demasiado largo o tener caracteres "
                              "no permitidos" if orden == "432" else "está ocupado")
                    texto = ("No se puede entrar: el apodo %s %s. Pulsa Control O y elige otro apodo."
                             % (self.apodo, motivo))
                    self.agregar(servidor, texto)
                    self.desconectar("Apodo no disponible")
                    return
                self.agregar(servidor, "El apodo %s no está disponible. Probando con %s." % (self.apodo, nuevo))
                self.apodo = nuevo
                self.enviar("NICK " + nuevo)
            else:
                self.agregar(self.ventana_actual, "El apodo %s no está disponible." % (p[1] if len(p) > 2 else ""))

        elif orden == "CAP" and len(p) >= 2:
            sub = p[1].upper()
            if sub == "ACK" and "sasl" in ultimo.lower().split():
                self.enviar("AUTHENTICATE PLAIN")
            elif sub == "NAK":
                self.enviar("CAP END")
                self.agregar(servidor, "Este servidor no admite SASL. Elige otro método de identificación.")
            elif sub == "ACK":
                self.enviar("CAP END")

        elif orden == "AUTHENTICATE" and p and p[0] == "+":
            datos = "%s\0%s\0%s" % (self.cfg["apodo"], self.cfg["apodo"], self.cfg["clave"])
            codificado = base64.b64encode(datos.encode("utf-8")).decode("ascii")
            for i in range(0, len(codificado), 400):
                self.enviar("AUTHENTICATE " + codificado[i:i + 400])
            if len(codificado) % 400 == 0:
                self.enviar("AUTHENTICATE +")

        elif orden == "903":
            self.enviar("CAP END")
            self.agregar(servidor, "Apodo identificado correctamente.", hablar=False)

        elif orden in ("902", "904", "905", "906", "908"):
            self.enviar("CAP END")
            self.agregar(servidor, "No se pudo identificar el apodo: " + ultimo)

        elif orden == "PRIVMSG" and len(p) >= 2:
            self._privmsg(nick, yo, p[0], p[-1])

        elif orden == "NOTICE" and len(p) >= 2:
            self._notice(prefijo, nick, p[0], p[-1])

        elif orden == "JOIN" and p:
            self._join(nick, yo, p[0])

        elif orden == "PART" and p:
            v = self.obtener_ventana(p[0], "canal", crear=False)
            if not v:
                return
            motivo = " (%s)" % limpiar_formato(p[1]) if len(p) > 1 and p[1] else ""
            if yo:
                v.unido = False
                v.usuarios = {}
                self.agregar(v, "Has salido del canal.")
                self._refrescar_lista()
            else:
                v.usuarios.pop(nick.lower(), None)
                self.agregar(v, "%s ha salido del canal%s." % (nick, motivo), "entrada", evento="salida")
            self._refrescar_si_actual(v)

        elif orden == "QUIT":
            motivo = " (%s)" % ultimo if ultimo else ""
            sonado = False
            for v in self.ventanas:
                if v.tipo == "canal" and nick.lower() in v.usuarios:
                    v.usuarios.pop(nick.lower())
                    self.agregar(v, "%s se ha desconectado%s." % (nick, motivo), "entrada",
                                 evento=None if sonado else "salida")
                    sonado = True
                    self._refrescar_si_actual(v)
                elif v.tipo == "privado" and v.nombre.lower() == nick.lower():
                    self.agregar(v, "%s se ha desconectado%s." % (nick, motivo))

        elif orden == "NICK" and p:
            nuevo = p[0]
            if yo:
                self.apodo = nuevo
                self.agregar(self.ventana_actual, "Ahora te llamas %s." % nuevo)
                self._actualizar_titulo()
            for v in self.ventanas:
                if v.tipo == "canal" and nick.lower() in v.usuarios:
                    datos = v.usuarios.pop(nick.lower())
                    datos[1] = nuevo
                    v.usuarios[nuevo.lower()] = datos
                    if not yo:
                        self.agregar(v, "%s ahora se llama %s." % (nick, nuevo), "entrada")
                    self._refrescar_si_actual(v)
                elif v.tipo == "privado" and v.nombre.lower() == nick.lower():
                    v.nombre = nuevo
                    self.agregar(v, "%s ahora se llama %s." % (nick, nuevo))
                    self._refrescar_lista()
                    self._actualizar_titulo()

        elif orden == "KICK" and len(p) >= 2:
            v = self.obtener_ventana(p[0], "canal", crear=False)
            if not v:
                return
            victima = p[1]
            motivo = ": " + ultimo if len(p) > 2 and ultimo else ""
            if victima.lower() == self.apodo.lower():
                v.unido = False
                v.usuarios = {}
                texto = "%s te ha expulsado de %s%s." % (nick, p[0], motivo)
                if self.cfg["rejoin"]:
                    # Como mucho 3 vueltas por canal en 5 minutos, para no entrar en bucle.
                    ahora = time.time()
                    recientes = [x for x in self.expulsiones.get(p[0].lower(), []) if ahora - x < 300]
                    recientes.append(ahora)
                    self.expulsiones[p[0].lower()] = recientes
                    if len(recientes) <= 3:
                        texto += " Volviendo a entrar en 3 segundos."
                        wx.CallLater(3000, self.enviar, "JOIN " + p[0])
                    else:
                        texto += " Te han expulsado varias veces seguidas: no se vuelve a entrar automáticamente."
                self.agregar(v, texto, "resalte", evento="expulsion")
                self._refrescar_lista()
            else:
                v.usuarios.pop(victima.lower(), None)
                self.agregar(v, "%s ha expulsado a %s%s" % (nick, victima, motivo))
            self._refrescar_si_actual(v)

        elif orden == "TOPIC" and p:
            v = self.obtener_ventana(p[0], "canal", crear=False)
            if v:
                v.tema = ultimo
                self.agregar(v, "%s ha cambiado el tema a: %s" % (nick, ultimo))

        elif orden == "MODE" and len(p) >= 2:
            if es_canal(p[0]):
                v = self.obtener_ventana(p[0], "canal", crear=False)
                if v:
                    me_dan_op = self._me_dan_op(p[1], p[2:])
                    self.agregar(v, "%s establece el modo %s" % (nick or prefijo, " ".join(p[1:])),
                                 evento="op" if me_dan_op else None)
                    if any(c in p[1] for c in "qaohv"):
                        self._pedir_nombres(p[0])
            else:
                self.agregar(servidor, "Modo de usuario: " + " ".join(p[1:]), hablar=False)

        elif orden == "INVITE" and len(p) >= 2:
            self.agregar(self.ventana_actual,
                         "%s te invita a %s. Escribe /join %s para entrar." % (nick, p[-1], p[-1]),
                         "resalte", evento="invitacion")

        elif orden == "332" and len(p) >= 3:
            v = self.obtener_ventana(p[1], "canal", crear=False)
            if v:
                v.tema = ultimo
                self.agregar(v, "Tema: " + ultimo, hablar=False)

        elif orden == "302":
            # Respuesta a USERHOST: se guarda el host para comprobar quién se conecta por DCC.
            pedidos = False
            for entrada in ultimo.split():
                apodo, _, resto = entrada.partition("=")
                apodo = apodo.rstrip("*").lower()
                if "@" in resto:
                    self.hosts_usuarios[apodo] = resto.split("@", 1)[1]
                if apodo in self.userhost_pedidos:
                    self.userhost_pedidos.discard(apodo)
                    pedidos = True
            if not pedidos and ultimo:
                self.agregar(servidor, ultimo)

        elif orden == "353" and len(p) >= 3:
            self._nombres(p[-2], ultimo)

        elif orden == "366" and len(p) >= 2:
            self._fin_nombres(p[1])

        elif orden == "305":
            self.agregar(self.ventana_actual, "Ya no estás ausente.")
        elif orden == "306":
            self.agregar(self.ventana_actual, "Ahora estás ausente.")

        elif orden in ("333", "329", "PONG"):
            pass

        elif orden == "ERROR":
            self.agregar(servidor, "El servidor dice: " + ultimo)

        elif orden == "311" and len(p) >= 6:
            self.agregar(self.ventana_actual, "%s es %s@%s (%s)" % (p[1], p[2], p[3], ultimo))
        elif orden == "301" and len(p) >= 3:
            self.agregar(self.ventana_actual, "%s está ausente: %s" % (p[1], ultimo))
        elif orden == "318":
            self.agregar(self.ventana_actual, "Fin de la información de %s." % p[1] if len(p) > 1 else "", hablar=False)
        elif orden in NUMERICOS_WHOIS:
            self.agregar(self.ventana_actual, " ".join(limpiar_formato(x) for x in p[1:]))

        elif orden.isdigit():
            texto = " ".join(limpiar_formato(x) for x in p[1:])
            if orden >= "400":
                self.agregar(self.ventana_actual, texto)
            else:
                self.agregar(servidor, texto, hablar=orden not in NUMERICOS_SILENCIOSOS)

        else:
            self.agregar(servidor, limpiar_formato(linea), hablar=False)

    def _pedir_nombres(self, canal):
        """Pide la lista de usuarios una sola vez aunque lleguen muchos cambios de modo seguidos."""
        clave = canal.lower()
        if clave in self.names_pendientes:
            return
        self.names_pendientes.add(clave)

        def pedir():
            self.names_pendientes.discard(clave)
            if self.conectado():
                self.enviar("NAMES " + canal)
        wx.CallLater(2000, pedir)

    def _me_dan_op(self, modos, argumentos):
        """Comprueba si un cambio de modo te da operador (o rango superior)."""
        signo = "+"
        args = list(argumentos)
        for c in modos:
            if c in "+-":
                signo = c
                continue
            usa_argumento = c in "qaohvbeIk" or (c == "l" and signo == "+")
            arg = args.pop(0) if usa_argumento and args else None
            if signo == "+" and c in "qaoh" and arg and arg.lower() == self.apodo.lower():
                return True
        return False

    def _refrescar_si_actual(self, v):
        if v is self.ventana_actual:
            self._refrescar_usuarios()

    def _privmsg(self, nick, yo, destino, texto):
        if texto.startswith("\x01"):
            ctcp = texto.strip("\x01")
            accion, _, arg = ctcp.partition(" ")
            accion = accion.upper()
            if accion == "ACTION":
                linea = "* %s %s" % (nick, limpiar_formato(arg))
            elif accion == "DCC":
                # Solo se aceptan ofertas de archivos enviadas en privado, no a un canal.
                if not yo and not es_canal(destino):
                    self._dcc_ctcp(nick, arg)
                return
            else:
                # Como mucho una respuesta cada 3 segundos: si no, cualquiera podría hacer que el
                # servidor te desconecte por exceso de mensajes pidiéndolas sin parar.
                ahora = time.time()
                if accion in ("VERSION", "PING", "TIME") and ahora - self.ultimo_ctcp >= 3:
                    self.ultimo_ctcp = ahora
                    if accion == "VERSION":
                        self.enviar("NOTICE %s :\x01VERSION %s %s\x01" % (nick, NOMBRE_APP, VERSION))
                    elif accion == "PING":
                        self.enviar("NOTICE %s :\x01PING %s\x01" % (nick, arg[:64]))
                    elif accion == "TIME":
                        self.enviar("NOTICE %s :\x01TIME %s\x01" % (nick, datetime.datetime.now().ctime()))
                self.agregar(self.ventanas[0], "%s te ha enviado una petición CTCP %s." % (nick, accion), hablar=False)
                return
        else:
            linea = "%s: %s" % (nick, limpiar_formato(texto))

        limpio = limpiar_formato(texto)
        # La voz dice «Dani dice: hola»; las acciones de /me se leen tal cual.
        voz = None if texto.startswith("\x01") else "%s dice: %s" % (nick, limpio)
        if yo and voz:
            voz = "Has dicho: " + limpio
        if es_canal(destino):
            v = self.obtener_ventana(destino, "canal")
            if yo:
                tipo = "propio"
            else:
                tipo = "resalte" if self._me_nombra(limpio) else "mensaje"
        else:
            v = self.obtener_ventana(destino if yo else nick, "privado")
            tipo = "propio" if yo else "privado"
            if not yo:
                self._responder_ausencia(nick)
        self.agregar(v, linea, tipo, voz=voz)
        if not yo:
            self._automatizar(v, nick, limpio)

    def _responder_ausencia(self, nick):
        if self.ausente is None or not self.cfg["respuesta_ausente"]:
            return
        if nick.lower() in self.avisados_ausencia or nick.lower().endswith("serv"):
            return
        self.avisados_ausencia.add(nick.lower())
        motivo = (": " + self.ausente) if self.ausente else "."
        self.enviar("NOTICE %s :Ahora mismo estoy ausente%s Te leeré en cuanto vuelva." % (nick, motivo))

    def _reglas(self):
        reglas = []
        for linea in self.cfg["respuestas"].splitlines():
            patron, separador, respuesta = linea.partition("=>")
            if separador and patron.strip() and respuesta.strip():
                reglas.append((patron.strip(), respuesta.strip()))
        return reglas

    def _automatizar(self, v, nick, texto):
        ahora = time.time()
        for i, (patron, respuesta) in enumerate(self._reglas()):
            if patron.lower() not in texto.lower():
                continue
            clave = (i, v.nombre.lower())
            if ahora - self.ultimas_respuestas.get(clave, 0) < 30:
                continue
            self.ultimas_respuestas[clave] = ahora
            final = respuesta.replace("$nick", nick).replace("$canal", v.nombre).replace("$yo", self.apodo)
            wx.CallLater(1200, self._ejecutar_respuesta, v, final)

    def _ejecutar_respuesta(self, v, texto):
        if v not in self.ventanas or not self.conectado():
            return
        if texto.lower().startswith("/me "):
            self.decir_en_ventana(v, texto[4:], accion=True)
        elif texto.startswith("/"):
            self.ejecutar_orden(texto[1:])
        else:
            self.decir_en_ventana(v, texto)

    def _notice(self, prefijo, nick, destino, texto):
        texto = limpiar_formato(texto)
        if texto.startswith("\x01"):
            self.agregar(self.ventana_actual, "Respuesta CTCP de %s: %s" % (nick, texto.strip("\x01")))
            return
        if not nick or "!" not in prefijo:
            # aviso del propio servidor
            self.agregar(self.ventanas[0], texto, hablar=self.registrado)
        elif es_canal(destino):
            v = self.obtener_ventana(destino, "canal")
            self.agregar(v, "Aviso de %s: %s" % (nick, texto), "mensaje", evento="aviso")
        else:
            v = self.obtener_ventana(nick, "privado", crear=False) or self.ventana_actual
            self.agregar(v, "Aviso de %s: %s" % (nick, texto), evento="aviso")

    def _join(self, nick, yo, canal):
        if yo:
            v = self.obtener_ventana(canal, "canal")
            v.unido = True
            v.usuarios = {}
            self.agregar(v, "Has entrado en %s." % canal, hablar=False)
            manual = canal.lower() in self.uniones_manuales
            self.uniones_manuales.discard(canal.lower())
            if manual or self.ventana_actual.tipo == "servidor":
                self.cambiar_ventana(self.ventanas.index(v), anunciar=False)
                self.hablar("Has entrado en " + canal)
            else:
                self._refrescar_lista()
        else:
            v = self.obtener_ventana(canal, "canal", crear=False)
            if not v:
                return
            v.usuarios[nick.lower()] = ["", nick]
            self.agregar(v, "%s ha entrado en el canal." % nick, "entrada", evento="entrada")
            self._refrescar_si_actual(v)

    def _nombres(self, canal, lista):
        v = self.obtener_ventana(canal, "canal", crear=False)
        if not v:
            self.agregar(self.ventana_actual, "Usuarios en %s: %s" % (canal, lista))
            return
        if canal.lower() not in self.nombres_en_curso:
            self.nombres_en_curso.add(canal.lower())
            v.usuarios = {}
        for ficha in lista.split():
            rango = ficha[0] if ficha[0] in RANGOS else ""
            apodo = ficha.lstrip(RANGOS)
            if apodo:
                v.usuarios[apodo.lower()] = [rango, apodo]

    def _fin_nombres(self, canal):
        self.nombres_en_curso.discard(canal.lower())
        v = self.obtener_ventana(canal, "canal", crear=False)
        if not v:
            return
        self._refrescar_si_actual(v)
        if canal.lower() in self.mostrar_nombres:
            self.mostrar_nombres.discard(canal.lower())
            nombres = sorted((u[1] for u in v.usuarios.values()), key=str.lower)
            self.agregar(v, "%d usuarios en %s: %s" % (len(nombres), canal, ", ".join(nombres)))

    # ----- DCC: transferencias de archivos -----

    def carpeta_descargas(self):
        return self.cfg["carpeta_descargas"] or DESCARGAS_DEFECTO

    def _ajustes_dcc(self):
        return {
            "ip_fija": self.cfg["dcc_ip"].strip(),
            "auto": self.cfg["dcc_ip_auto"],
            "ip_local": self.conexion.ip_local() if self.conexion else "127.0.0.1",
            "puertos": self.cfg["dcc_puertos"],
        }

    def _nueva_transferencia(self, *args):
        t = Transferencia(*args)
        t.al_avanzar = lambda t, pc: wx.CallAfter(self.hablar, "%s, %d por ciento" % (t.nombre, pc))
        self.transferencias.append(t)
        return t

    def _enviar_ctcp_dcc(self, apodo, nombre, ip, puerto, tamano, token=None):
        nombre_ctcp = '"%s"' % nombre if " " in nombre else nombre
        partes = ["DCC SEND", nombre_ctcp, ip_para_dcc(ip), str(puerto), str(tamano)]
        if token:
            partes.append(token)
        self.enviar("PRIVMSG %s :\x01%s\x01" % (apodo, " ".join(partes)))

    def _dcc_ctcp(self, nick, arg):
        subtipo = arg.split(" ", 1)[0].upper()
        if subtipo != "SEND":
            self.agregar(self.ventana_actual,
                         "%s quiere iniciar un DCC %s, que AccesIRC todavía no admite." % (nick, subtipo))
            return
        datos = parsear_dcc_send(arg)
        if not datos:
            self.agregar(self.ventanas[0], "Petición de archivo de %s que no se entiende: %s" % (nick, arg),
                         hablar=False)
            return
        # Respuesta a un envío nuestro en modo pasivo: ahora nos conectamos nosotros.
        token = datos["token"]
        if token and datos["puerto"] and token in self.dcc_pasivos:
            t = self.dcc_pasivos[token]
            if t.apodo.lower() == nick.lower():
                del self.dcc_pasivos[token]
                ip, puerto = datos["ip"], datos["puerto"]
                threading.Thread(target=self._ejecutar_transferencia, daemon=True, args=(
                    t, lambda: socket.create_connection((ip, puerto), timeout=30))).start()
                return
        wx.CallAfter(self._preguntar_dcc, nick, datos)

    def _preguntar_dcc(self, nick, datos):
        nombre = nombre_archivo_limpio(datos["nombre"])
        datos["nombre"] = nombre
        if self.dcc_preguntando:
            # Solo un diálogo a la vez: así nadie puede llenarte la pantalla de peticiones.
            self.agregar(self.ventanas[0], "Rechazado automáticamente el archivo %s de %s: ya tenías "
                         "otra petición pendiente. Si lo querías, pídele que te lo vuelva a enviar." % (nombre, nick),
                         hablar=False)
            return
        self.dcc_preguntando = True
        try:
            acepta = self._dialogo_dcc(nick, datos)
        finally:
            self.dcc_preguntando = False
        if not acepta:
            self.agregar(self.ventanas[0], "Has rechazado el archivo %s de %s." % (nombre, nick), hablar=False)
            return
        self._aceptar_dcc(nick, datos)

    def _dialogo_dcc(self, nick, datos):
        self.sonar("dcc")
        nombre = datos["nombre"]
        tamano = tamano_legible(datos["tamano"]) if datos["tamano"] else "tamaño desconocido"
        carpeta = self.carpeta_descargas()
        if not self.IsActive():
            self.hablar("%s quiere enviarte un archivo. Vuelve a AccesIRC para aceptarlo o rechazarlo." % nick)
            self.RequestUserAttention()
        aviso = ""
        if es_peligroso(nombre):
            aviso = ("¡CUIDADO! Es un archivo de tipo %s, que puede ejecutar programas en tu ordenador. "
                     "Es la forma más habitual de colar un virus. Recházalo salvo que lo esperaras de alguien "
                     "de mucha confianza.\n\n" % os.path.splitext(nombre)[1].lower())
        try:
            libre = shutil.disk_usage(carpeta if os.path.isdir(carpeta) else os.path.expanduser("~")).free
        except OSError:
            libre = None
        if libre is not None and datos["tamano"] and datos["tamano"] > libre:
            wx.MessageBox("%s quiere enviarte «%s» (%s), pero no cabe: solo quedan %s libres en el disco." % (
                nick, nombre, tamano, tamano_legible(libre)), "No hay espacio", wx.OK | wx.ICON_WARNING, self)
            return False
        dlg = wx.MessageDialog(
            self,
            "%s%s quiere enviarte el archivo «%s» (%s).\n\nSe guardará en:\n%s\n\n"
            "Acepta solo archivos de personas de confianza. ¿Quieres aceptarlo?" % (
                aviso, nick, nombre, tamano, carpeta),
            "Te quieren enviar un archivo",
            wx.YES_NO | wx.NO_DEFAULT | (wx.ICON_WARNING if aviso else wx.ICON_QUESTION))
        dlg.SetYesNoLabels("&Aceptar", "&Rechazar")
        acepta = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        return acepta

    def _aceptar_dcc(self, nick, datos):
        carpeta = self.carpeta_descargas()
        if not self.conectado():
            self.agregar(self.ventana_actual, "No se puede recibir el archivo: no estás conectado.")
            return
        try:
            os.makedirs(carpeta, exist_ok=True)
        except OSError as e:
            self.agregar(self.ventana_actual, "No se puede usar la carpeta de descargas: %s" % e)
            return
        t = self._nueva_transferencia("recibir", nick, datos["nombre"],
                                      ruta_libre(carpeta, datos["nombre"]), datos["tamano"])
        if datos["puerto"]:
            ip, puerto = datos["ip"], datos["puerto"]
            conectar = lambda: socket.create_connection((ip, puerto), timeout=30)
        elif datos["token"]:
            # El emisor está en modo pasivo: abrimos nosotros el puerto.
            ajustes = self._ajustes_dcc()
            conectar = lambda: self._escuchar(t, ajustes, lambda ip, puerto: self._enviar_ctcp_dcc(
                nick, datos["nombre"], ip, puerto, datos["tamano"], datos["token"]))
        else:
            t.estado, t.detalle = "fallida", "la petición no indica cómo conectar"
            self.agregar(self.ventana_actual, t.descripcion())
            return
        threading.Thread(target=self._ejecutar_transferencia, args=(t, conectar), daemon=True).start()
        self.agregar(self.ventanas[0], "Recibiendo %s de %s." % (t.nombre, nick), hablar=False)
        self.hablar("Aceptado. Recibiendo " + t.nombre, True)

    def _escuchar(self, t, ajustes, ofrecer):
        """Abre un puerto, anuncia nuestra IP con 'ofrecer' y espera la conexión. Se ejecuta en un hilo."""
        servidor = abrir_puerto(ajustes["puertos"])
        t.sock = servidor
        # Pedimos al servidor la dirección de la otra persona para comprobar quién se conecta.
        wx.CallAfter(self._pedir_userhost, t.apodo)
        try:
            ip = ajustes["ip_fija"]
            if not ip and ajustes["auto"]:
                try:
                    ip = ip_publica()
                except Exception:
                    ip = None
            ip = ip or ajustes["ip_local"]
            wx.CallAfter(ofrecer, ip, servidor.getsockname()[1])
            # Esperar hasta 3 minutos, comprobando cada segundo si se ha cancelado.
            servidor.settimeout(1)
            limite = time.time() + 180
            while True:
                if t.cancelada:
                    raise OSError("cancelada")
                try:
                    conexion, direccion = servidor.accept()
                except socket.timeout:
                    if time.time() > limite:
                        raise
                    continue
                if self._conexion_dcc_valida(t.apodo, direccion[0]):
                    return conexion
                # Alguien distinto (por ejemplo, un escáner de internet) se ha colado: se le
                # cierra la puerta y se sigue esperando a la persona correcta.
                try:
                    conexion.close()
                except OSError:
                    pass
                wx.CallAfter(self.agregar, self.ventanas[0],
                             "Rechazada una conexión de %s que no es de %s, para la transferencia de %s."
                             % (direccion[0], t.apodo, t.nombre), "info", False)
        finally:
            servidor.close()

    def _pedir_userhost(self, apodo):
        if self.conectado():
            self.userhost_pedidos.add(apodo.lower())
            self.enviar("USERHOST " + apodo)

    def _conexion_dcc_valida(self, apodo, ip):
        """Comprueba que quien se conecta por DCC es la persona esperada. Se ejecuta en un hilo.

        Se admite si la IP es de tu red local (estáis en la misma casa u oficina), o si coincide con
        la dirección con la que esa persona está conectada al IRC. Si la red oculta las direcciones
        (host enmascarado), no se puede comprobar y se admite, como hace mIRC."""
        try:
            direccion = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if direccion.is_private or direccion.is_loopback or direccion.is_link_local:
            return True
        host = self.hosts_usuarios.get(apodo.lower())
        if not host:
            return True
        try:
            literal = ipaddress.ip_address(host)
            # Si está conectada al IRC por IPv6, su IPv4 no se conoce: no se puede comprobar.
            return literal.version != 4 or ip == str(literal)
        except ValueError:
            pass
        try:
            ips = {info[4][0] for info in socket.getaddrinfo(host, None, socket.AF_INET)}
        except OSError:
            return True  # host enmascarado o que no se resuelve: no se puede comprobar
        return not ips or ip in ips

    def _ejecutar_transferencia(self, t, conectar):
        """Conecta y transfiere el archivo. Se ejecuta en un hilo aparte."""
        sock = None
        try:
            sock = conectar()
            if t.cancelada:
                raise OSError("cancelada")
            t.sock = sock
            t.estado = "en_curso"
            if t.tipo == "recibir":
                # "x": no pisar nunca un archivo existente, aunque dos transferencias con el
                # mismo nombre lleguen a la vez.
                for _ in range(20):
                    try:
                        f = open(t.ruta, "xb")
                        break
                    except FileExistsError:
                        t.ruta = ruta_libre(os.path.dirname(t.ruta), t.nombre)
                else:
                    raise OSError("no se encontró un nombre libre para guardar el archivo")
                with f:
                    recibir_dcc(sock, f, t)
                marcar_como_descargado(t.ruta)
            else:
                with open(t.ruta, "rb") as f:
                    enviar_dcc(sock, f, t)
            if t.cancelada:
                t.estado = "cancelada"
            elif t.tamano and t.hecho < t.tamano:
                t.estado = "fallida"
                t.detalle = "la conexión se cortó al %d%%" % t.porcentaje()
            else:
                t.estado = "completada"
        except socket.timeout:
            t.estado = "cancelada" if t.cancelada else "fallida"
            if not t.cancelada:
                t.detalle = ("la otra persona no respondió a tiempo" if t.hecho == 0
                             else "la transferencia se quedó parada")
        except Exception as e:
            t.estado = "cancelada" if t.cancelada else "fallida"
            if not t.cancelada:
                if isinstance(e, (ConnectionRefusedError, TimeoutError)) and t.hecho == 0:
                    t.detalle = ("no se pudo conectar con %s; puede que su router no tenga los puertos abiertos"
                                 % t.apodo)
                else:
                    t.detalle = describir_error(e)
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        if t.tipo == "recibir" and t.estado != "completada":
            try:
                if os.path.exists(t.ruta):
                    os.remove(t.ruta)
            except OSError:
                pass
        wx.CallAfter(self._dcc_terminada, t)

    def _dcc_terminada(self, t):
        if t.estado == "completada":
            if t.tipo == "recibir":
                texto = "Archivo recibido: %s, de %s. Guardado como %s." % (
                    t.nombre, t.apodo, os.path.basename(t.ruta))
                if es_peligroso(t.ruta):
                    texto += " Atención: es un archivo que puede ejecutar programas; ábrelo solo si confías en quien lo envía."
            else:
                texto = "Archivo enviado: %s, a %s." % (t.nombre, t.apodo)
            self.sonar("dcc_fin")
        else:
            texto = "Transferencia " + t.descripcion()
        self.agregar(self.ventanas[0], texto, hablar=False)
        if t.estado != "cancelada":
            self.hablar(texto)

    def dcc_enviar(self, apodo=None, ruta=None):
        if not self.conectado():
            self.agregar(self.ventana_actual, "No estás conectado. Pulsa Control O para conectar.")
            return
        if not apodo:
            v = self.ventana_actual
            sugerido = v.nombre if v.tipo == "privado" else (self.apodo_seleccionado() or "")
            dlg = wx.TextEntryDialog(self, "¿A quién le envías el archivo? Escribe su apodo:", "Enviar un archivo", sugerido)
            aceptado = dlg.ShowModal() == wx.ID_OK
            apodo = dlg.GetValue().strip()
            dlg.Destroy()
            if not aceptado or not apodo:
                return
        if not ruta:
            dlg = wx.FileDialog(self, "Elige el archivo que quieres enviar a " + apodo,
                                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
            aceptado = dlg.ShowModal() == wx.ID_OK
            ruta = dlg.GetPath()
            dlg.Destroy()
            if not aceptado:
                return
        if not os.path.isfile(ruta):
            self.agregar(self.ventana_actual, "No encuentro el archivo %s." % ruta)
            return
        nombre = os.path.basename(ruta)
        t = self._nueva_transferencia("enviar", apodo, nombre, ruta, os.path.getsize(ruta))
        ajustes = self._ajustes_dcc()
        if self.cfg["dcc_pasivo"]:
            t.token = str(random.randint(100, 999999))
            self.dcc_pasivos[t.token] = t
            self._enviar_ctcp_dcc(apodo, nombre, ajustes["ip_fija"] or ajustes["ip_local"], 0, t.tamano, t.token)
            wx.CallLater(180000, self._caducar_pasivo, t)
        else:
            conectar = lambda: self._escuchar(t, ajustes, lambda ip, puerto: self._enviar_ctcp_dcc(
                apodo, nombre, ip, puerto, t.tamano))
            threading.Thread(target=self._ejecutar_transferencia, args=(t, conectar), daemon=True).start()
        self.agregar(self.ventana_actual, "Ofreciendo %s (%s) a %s. Esperando a que lo acepte." % (
            nombre, tamano_legible(t.tamano), apodo))

    def _caducar_pasivo(self, t):
        if self.dcc_pasivos.get(t.token) is t:
            del self.dcc_pasivos[t.token]
            t.estado, t.detalle = "fallida", "%s no aceptó el archivo a tiempo" % t.apodo
            self._dcc_terminada(t)

    def dcc_cancelar(self, t):
        if t.token and self.dcc_pasivos.get(t.token) is t:
            del self.dcc_pasivos[t.token]
            t.estado = "cancelada"
        t.cancelar()
        self.hablar("Transferencia cancelada", True)

    # ----- envío de mensajes y órdenes -----

    def al_enviar(self, ev):
        texto = self.entrada.GetValue()
        if not texto.strip():
            return
        self.entrada.SetValue("")
        if not self.historial_entrada or self.historial_entrada[-1] != texto:
            self.historial_entrada.append(texto)
            del self.historial_entrada[:-100]
        self.pos_historial = len(self.historial_entrada)
        if texto.startswith("/") and not texto.startswith("//"):
            self.ejecutar_orden(texto[1:])
        else:
            self.decir_en_ventana(self.ventana_actual, texto[1:] if texto.startswith("//") else texto)

    def _aviso(self, texto):
        self.agregar(self.ventana_actual, texto)

    def decir_en_ventana(self, v, texto, accion=False):
        if v.tipo == "servidor":
            self._aviso("Esta es la ventana del servidor. Cambia a un canal, o usa /join #canal o /msg apodo texto.")
            return
        if not self.conectado():
            self._aviso("No estás conectado. Pulsa Control O para conectar.")
            return
        if v.tipo == "canal" and not v.unido:
            self._aviso("No estás en el canal. Escribe /join %s para entrar." % v.nombre)
            return
        for trozo in dividir_texto(texto):
            if accion:
                self.enviar("PRIVMSG %s :\x01ACTION %s\x01" % (v.nombre, trozo))
                self.agregar(v, "* %s %s" % (self.apodo, trozo), "propio",
                             voz="%s %s" % (self.apodo, trozo))
            else:
                self.enviar("PRIVMSG %s :%s" % (v.nombre, trozo))
                self.agregar(v, "%s: %s" % (self.apodo, trozo), "propio", voz="Has dicho: " + trozo)

    def ejecutar_orden(self, linea):
        orden, _, resto = linea.partition(" ")
        orden = orden.lower()
        resto = resto.strip()
        v = self.ventana_actual

        locales = {"clear", "cls", "close", "cerrar", "help", "ayuda", "server", "connect", "me", "query", "q",
                   "dcc", "ignore", "unignore"}
        if orden not in locales and not self.conectado():
            self._aviso("No estás conectado. Pulsa Control O para conectar.")
            return

        if orden in ("join", "j"):
            if not resto:
                self.dialogo_unirse()
                return
            canal, _, clave = resto.partition(" ")
            if not es_canal(canal):
                canal = "#" + canal
            self.uniones_manuales.add(canal.lower())
            if clave:
                self.claves_canal[canal.lower()] = clave.split()[0]
            existente = self.obtener_ventana(canal, "canal", crear=False)
            if existente and existente.unido:
                self.cambiar_ventana(self.ventanas.index(existente))
                return
            self.enviar("JOIN %s %s" % (canal, clave) if clave else "JOIN " + canal)
        elif orden in ("part", "leave"):
            canal = v.nombre if v.tipo == "canal" else None
            motivo = resto
            if resto and es_canal(resto.split()[0]):
                canal, _, motivo = resto.partition(" ")
            if not canal:
                self._aviso("Indica el canal: /part #canal")
                return
            self.enviar("PART %s :%s" % (canal, motivo) if motivo else "PART " + canal)
        elif orden in ("msg", "privmsg", "m"):
            destino, _, texto = resto.partition(" ")
            if not destino or not texto:
                self._aviso("Uso: /msg apodo texto")
            elif es_canal(destino) or destino.lower().endswith("serv"):
                for trozo in dividir_texto(texto):
                    self.enviar("PRIVMSG %s :%s" % (destino, trozo))
                if destino.lower().endswith("serv"):
                    texto = texto.split()[0] + " ..."  # no mostrar contraseñas
                self._aviso("Enviado a %s: %s" % (destino, texto))
            else:
                self.decir_en_ventana(self.obtener_ventana(destino, "privado"), texto)
        elif orden in ("query", "q"):
            apodo, _, texto = resto.partition(" ")
            if not apodo:
                self.dialogo_privado()
                return
            nueva = self.obtener_ventana(apodo, "privado")
            self.cambiar_ventana(self.ventanas.index(nueva))
            if texto:
                self.decir_en_ventana(nueva, texto)
        elif orden == "me":
            if resto:
                self.decir_en_ventana(v, resto, accion=True)
        elif orden == "nick":
            if resto:
                self.enviar("NICK " + resto.split()[0])
        elif orden == "topic":
            if v.tipo != "canal":
                self._aviso("Esto no es un canal.")
            elif resto:
                self.enviar("TOPIC %s :%s" % (v.nombre, resto))
            else:
                self.leer_tema()
        elif orden in ("whois", "wi"):
            if resto:
                self.enviar("WHOIS " + resto.split()[0])
        elif orden == "names":
            canal = resto.split()[0] if resto else (v.nombre if v.tipo == "canal" else "")
            if canal:
                self.mostrar_nombres.add(canal.lower())
                self.enviar("NAMES " + canal)
        elif orden == "away":
            self.ausente = resto if resto else None
            self.avisados_ausencia.clear()
            self.enviar("AWAY :" + resto if resto else "AWAY")
        elif orden == "notice":
            destino, _, texto = resto.partition(" ")
            if destino and texto:
                self.enviar("NOTICE %s :%s" % (destino, texto))
                self.agregar(v, "Aviso enviado a %s: %s" % (destino, texto), "propio")
        elif orden == "dcc":
            partes = resto.split(None, 2)
            if not partes:
                self.dialogo_transferencias()
            elif partes[0].lower() == "send":
                apodo = partes[1] if len(partes) > 1 else None
                ruta = partes[2].strip().strip('"') if len(partes) > 2 else None
                self.dcc_enviar(apodo, ruta)
            else:
                self._aviso("Uso: /dcc send apodo [archivo], o /dcc para ver las transferencias.")
        elif orden == "ignore":
            lista = lista_comas(self.cfg["ignorados"])
            if not resto:
                self._aviso("Ignoras a: " + ", ".join(lista) if lista else "No ignoras a nadie.")
                return
            apodo = resto.split()[0]
            if apodo.lower() not in {x.lower() for x in lista}:
                lista.append(apodo)
                self.cfg["ignorados"] = ", ".join(lista)
                guardar_config(self.cfg)
            self._aviso("Ignorando a %s. Para dejar de ignorarle: /unignore %s" % (apodo, apodo))
        elif orden == "unignore":
            apodo = resto.split()[0] if resto else ""
            lista = [x for x in lista_comas(self.cfg["ignorados"]) if x.lower() != apodo.lower()]
            self.cfg["ignorados"] = ", ".join(lista)
            guardar_config(self.cfg)
            self._aviso("Ya no ignoras a %s." % apodo if apodo else "Uso: /unignore apodo")
        elif orden == "quit" or orden in ("exit", "disconnect"):
            self.desconectar(resto or "Hasta luego")
        elif orden in ("clear", "cls"):
            v.lineas = []
            self._mostrar_historial()
            self.hablar("Historial borrado", True)
        elif orden in ("close", "cerrar"):
            self.cerrar_ventana()
        elif orden in ("help", "ayuda"):
            self.mostrar_ayuda()
        elif orden in ("server", "connect"):
            self.dialogo_conectar()
        elif orden in ("raw", "quote"):
            if resto:
                self.enviar(resto)
        else:
            self.enviar(("%s %s" % (orden.upper(), resto)).strip())

    # ----- actualizaciones -----

    def comprobar_actualizaciones(self, manual):
        """manual=True desde el menú Ayuda: siempre responde. Automática: solo avisa si hay algo."""
        if self.actualizando:
            if manual:
                self.hablar("Ya se está descargando una actualización", True)
            return
        if manual:
            self.hablar("Buscando actualizaciones...", True)

        def trabajo():
            info = error = None
            try:
                info = consultar_ultima_version()
            except Exception as e:
                error = e
            wx.CallAfter(self._resultado_actualizacion, info, error, manual)
        threading.Thread(target=trabajo, daemon=True).start()

    def _resultado_actualizacion(self, info, error, manual):
        self.cfg["ultima_comprobacion"] = time.time()
        guardar_config(self.cfg)
        if error is not None:
            registrar_error("No se pudo comprobar si hay actualizaciones: %r" % error)
            if manual:
                if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                    texto = "Todavía no hay ninguna versión publicada."
                else:
                    texto = "No se pudo comprobar si hay actualizaciones: %s" % describir_error(error)
                wx.MessageBox(texto, "Buscar actualizaciones", wx.OK | wx.ICON_WARNING, self)
            return
        if info["tupla"] <= version_tupla(VERSION):
            if manual:
                wx.MessageBox("Tienes la versión más reciente de AccesIRC, la %s." % VERSION,
                              "Buscar actualizaciones", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not manual:
            # Sin ventanas que interrumpan: se avisa con la voz y en la ventana del servidor.
            if self.cfg.get("version_omitida") == info["version"]:
                return
            texto = ("Hay una versión nueva de AccesIRC, la %s. Para verla e instalarla, ve al menú "
                     "Ayuda, Buscar actualizaciones." % info["version"])
            self.agregar(self.ventanas[0], texto, hablar=False)
            self.hablar(texto)
            return
        puede_instalar = es_version_instalada() and info["instalador"] is not None
        dlg = DialogoActualizacion(self, info, puede_instalar)
        respuesta = dlg.ShowModal()
        dlg.Destroy()
        if respuesta == wx.ID_IGNORE:
            self.cfg["version_omitida"] = info["version"]
            guardar_config(self.cfg)
            self.hablar("No se volverá a avisar de la versión %s" % info["version"], True)
        elif respuesta == wx.ID_OK:
            if puede_instalar:
                self._descargar_actualizacion(info)
            else:
                webbrowser.open(info["pagina"])

    def _descargar_actualizacion(self, info):
        activas = [t for t in self.transferencias if t.activa()]
        if activas:
            dlg = wx.MessageDialog(self, "Hay %d transferencias de archivos en curso y se cortarán al "
                                   "cerrar AccesIRC para actualizar. ¿Seguir?" % len(activas),
                                   "Actualizar AccesIRC", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            seguir = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if not seguir:
                return
        self.actualizando = True
        estado = {"cancelado": False, "cuarto": 0}
        progreso = wx.ProgressDialog("Actualizar AccesIRC", "Descargando AccesIRC %s..." % info["version"],
                                     maximum=1000, parent=self,
                                     style=wx.PD_CAN_ABORT | wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
        self.hablar("Descargando la actualización", True)

        def avance(hecho, total):
            wx.CallAfter(actualizar_barra, hecho, total)

        def actualizar_barra(hecho, total):
            if estado["cancelado"] or not progreso:
                return
            valor = min(999, int(hecho * 1000 / total)) if total else 0
            seguir, _ = progreso.Update(valor, "Descargando AccesIRC %s: %s de %s" % (
                info["version"], tamano_legible(hecho), tamano_legible(total) if total else "?"))
            if not seguir:
                estado["cancelado"] = True
            cuarto = hecho * 4 // total if total else 0
            if 0 < cuarto < 4 and cuarto > estado["cuarto"]:
                estado["cuarto"] = cuarto
                self.hablar("%d por ciento" % (cuarto * 25))

        def trabajo():
            ruta = error = None
            try:
                ruta = descargar_instalador(info["instalador"], avance, lambda: estado["cancelado"])
            except Exception as e:
                error = e
            wx.CallAfter(terminado, ruta, error)

        def terminado(ruta, error):
            progreso.Destroy()
            self.actualizando = False
            if error is not None:
                if estado["cancelado"]:
                    self.hablar("Actualización cancelada", True)
                    return
                registrar_error("Falló la descarga de la actualización: %r" % error)
                wx.MessageBox("No se pudo descargar la actualización: %s\n\nPuedes bajarla a mano desde:\n%s"
                              % (describir_error(error), info["pagina"]),
                              "Actualizar AccesIRC", wx.OK | wx.ICON_WARNING, self)
                return
            self._instalar_actualizacion(ruta, info)
        threading.Thread(target=trabajo, daemon=True).start()

    def _instalar_actualizacion(self, ruta, info):
        try:
            # /SILENT muestra solo el avance; /REABRIR=si hace que el instalador vuelva a abrir AccesIRC.
            subprocess.Popen([ruta, "/SP-", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                              "/CLOSEAPPLICATIONS", "/REABRIR=si"], close_fds=True)
        except OSError as e:
            registrar_error("No se pudo abrir el instalador %s: %r" % (ruta, e))
            wx.MessageBox("No se pudo abrir el instalador: %s\n\nEstá en:\n%s" % (describir_error(e), ruta),
                          "Actualizar AccesIRC", wx.OK | wx.ICON_WARNING, self)
            return
        self.hablar("Instalando AccesIRC %s. Se volverá a abrir solo en unos segundos." % info["version"], True)
        self.mensaje_salida = "Actualizando AccesIRC"
        wx.CallLater(1500, self.Close)

    # ----- cierre -----

    def al_cerrar(self, ev):
        for t in self.transferencias:
            if t.activa():
                t.cancelar()
        self.desconectar(self.mensaje_salida)
        guardar_config(self.cfg)
        self.Destroy()


def manejador_excepciones(tipo, valor, tb):
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    registrar_error(texto)
    try:
        wx.MessageBox("Ha ocurrido un error inesperado. Los detalles se han guardado en:\n" + RUTA_ERRORES,
                      NOMBRE_APP, wx.OK | wx.ICON_ERROR)
    except Exception:
        pass


def main():
    os.makedirs(DIR_DATOS, exist_ok=True)
    sys.excepthook = manejador_excepciones
    app = wx.App(False)
    Principal()
    app.MainLoop()


if __name__ == "__main__":
    main()
