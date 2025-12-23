import os
import time
import requests
import urllib3
from playwright.sync_api import sync_playwright
from supabase import create_client

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

# Supabase (por variables de entorno en Render)
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BUCKET = "extractos"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Desactivar alertas SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def log(mensaje):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}")


def subir_a_supabase(nombre_archivo, contenido_pdf):
    """
    Sube (o reemplaza) un PDF en Supabase Storage
    """
    supabase.storage.from_(BUCKET).upload(
        nombre_archivo,
        contenido_pdf,
        {
            "content-type": "application/pdf",
            "cache-control": "no-store",
            "upsert": True
        }
    )


# =========================================================
# MÓDULO 1: LOTERÍA DE SANTA FE (Playwright)
# Quini 6 / Brinco
# =========================================================

def procesar_santa_fe(playwright_instance, nombre_juego, url_apps, nombre_archivo_final):
    log(f"--- Iniciando {nombre_juego} ---")

    try:
        browser = playwright_instance.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        try:
            page.goto(url_apps, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            log(f"❌ Error cargando página: {e}")
            browser.close()
            return

        selector = "div.soloextracto > a"

        try:
            page.wait_for_selector(selector, timeout=30000)
            enlace = page.locator(selector)
            href_sucio = enlace.get_attribute("href")

            if not href_sucio:
                log("❌ No se encontró enlace al PDF")
                browser.close()
                return

            pdf_url = href_sucio.replace("&amp;", "&")
            log("Enlace encontrado, descargando PDF...")

            response = context.request.get(pdf_url)
            if not response.ok:
                log(f"❌ Error descargando PDF: status {response.status}")
                browser.close()
                return

            pdf_bytes = response.body()
            if len(pdf_bytes) < 1000:
                log("⚠️ PDF inválido o vacío, no se sube")
                browser.close()
                return

            subir_a_supabase(nombre_archivo_final, pdf_bytes)
            log(f"✅ {nombre_juego} subido a Supabase como {nombre_archivo_final}")

        except Exception as e:
            log(f"❌ Error procesando {nombre_juego}: {e}")

        browser.close()

    except Exception as e:
        log(f"❌ Error crítico en {nombre_juego}: {e}")


# =========================================================
# MÓDULO 2: LOTERÍA DE LA CIUDAD (Requests)
# Loto Plus / Loto 5 Plus
# =========================================================

def procesar_ciudad(nombre_juego, url_base_template, id_base_inicio, nombre_archivo_final):
    log(f"--- Iniciando {nombre_juego} ---")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LoteriaBot/1.0)"
    }

    id_candidato = id_base_inicio
    ultimo_contenido = None
    ultimo_id = None
    fallos_consecutivos = 0

    while fallos_consecutivos < 3:
        id_prueba = id_candidato + 1
        url = url_base_template.format(id_prueba)

        try:
            resp = requests.get(url, headers=headers, timeout=10, verify=False)

            if resp.status_code == 200 and b"%PDF" in resp.content[:20]:
                log(f"PDF válido encontrado – sorteo {id_prueba}")
                ultimo_contenido = resp.content
                ultimo_id = id_prueba
                id_candidato += 1
                fallos_consecutivos = 0
            else:
                fallos_consecutivos += 1

        except Exception:
            fallos_consecutivos += 1

    if ultimo_contenido:
        subir_a_supabase(nombre_archivo_final, ultimo_contenido)
        log(f"✅ {nombre_juego} (sorteo {ultimo_id}) subido a Supabase")
    else:
        log(f"⚠️ No se encontraron PDFs nuevos para {nombre_juego}")


# =========================================================
# EJECUCIÓN PRINCIPAL
# =========================================================

def ejecutar_todo():
    print("=========================================")
    print("   ACTUALIZADOR DE EXTRACTOS – INICIO")
    print("=========================================")

    # --- Santa Fe (Playwright)
    with sync_playwright() as p:
        procesar_santa_fe(
            p,
            "Quini 6",
            "https://apps.loteriasantafe.gov.ar:8443/Extractos/paginas/mostrarQuini6.xhtml",
            "extracto_quini_ultimo.pdf"
        )

        procesar_santa_fe(
            p,
            "Brinco",
            "https://apps.loteriasantafe.gov.ar:8443/Extractos/paginas/mostrarBrinco.xhtml",
            "extracto_brinco_ultimo.pdf"
        )

    # --- Ciudad (Requests)
    procesar_ciudad(
        "Loto Plus",
        "https://loto.loteriadelaciudad.gob.ar/resultadosLoto/descargaExtracto.php?sorteo={}.pdf",
        3840,
        "extracto_loto_ultimo.pdf"
    )

    procesar_ciudad(
        "Loto 5 Plus",
        "https://loto5.loteriadelaciudad.gob.ar/resultadosLoto5/descargaExtracto.php?sorteo={}.pdf",
        1422,
        "extracto_loto5_ultimo.pdf"
    )

    print("=========================================")
    print("   TAREA COMPLETADA")
    print("=========================================")


if __name__ == "__main__":
    ejecutar_todo()
