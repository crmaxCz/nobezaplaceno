import streamlit as st
import subprocess
import pandas as pd

# --- 1. INSTALACE (Playwright) ---
def install_playwright():
    if "browser_installed" not in st.session_state:
        with st.spinner("Příprava prohlížeče..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright()
from playwright.sync_api import sync_playwright

# --- 2. CONFIG ---
POBOCKY = {"326": "Liberec", "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava"}
USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

st.set_page_config(page_title="DEBUG: Výpis termínů")

# --- 3. SCRAPER (FÁZE 1: Jen seznam) ---
def debug_get_list(pob_id):
    results = []
    with sync_playwright() as p:
        # Spuštění s ignorováním chyb certifikátů a v pomalém režimu pro stabilitu
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        # Nastavíme globální timeout na 90s
        page.set_default_timeout(90000)

        try:
            # A. PŘIHLÁŠENÍ
            st.write("Navazuji spojení s loginem...")
            page.goto("https://nobe.moje-autoskola.cz/index.php", wait_until="domcontentloaded")
            page.fill('input[name="log_email"]', USER)
            page.fill('input[name="log_heslo"]', PW)
            page.click('input[type="submit"]')
            
            # Počkáme na jakýkoliv náznak úspěšného přihlášení
            page.wait_for_selector(".navbar, #maincontent", timeout=45000)
            st.write("✅ Přihlášení OK.")

            # B. FILTR (přesně podle tvé URL, jen s dnešním datem)
            target_url = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od=24.02.2026&vytez_typ=545&vytez_lokalita={pob_id}&akce=prednasky_filtr"
            st.write(f"Jdu na URL: {target_url}")
            
            # KLÍČOVÁ ZMĚNA: Nečekáme na 'load', ale jen na 'domcontentloaded'
            page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
            
            # Počkáme přímo na existenci řádků v tabulce
            st.write("Čekám na vykreslení tabulky...")
            page.wait_for_selector("tr.text-warning", timeout=60000)

            # C. EXTRAKCE
            rows = page.query_selector_all("tr.text-warning")
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) > 1:
                    results.append({
                        "Termín": cells[0].inner_text().strip(),
                        "Název": cells[1].inner_text().strip(),
                        "Učitel": cells[2].inner_text().strip()
                    })

        except Exception as e:
            st.error(f"❌ CHYBA: {str(e)}")
            # Pokud dojde k chybě, uděláme screenshot pro debug (volitelné)
            # page.screenshot(path="error.png")
        finally:
            browser.close()
    return results

# --- 4. UI ---
st.title("Jednoduchý výpis termínů")

pob_id = st.selectbox("Vyber ID pobočky:", options=list(POBOCKY.keys()), format_func=lambda x: POBOCKY[x])

if st.button("SPUSTIT VÝPIS"):
    data = debug_get_list(pob_id)
    if data:
        st.success(f"Našel jsem {len(data)} termínů!")
        st.dataframe(pd.DataFrame(data))
    else:
        st.warning("Seznam je prázdný. Robot tabulku nenašel (možná timeout).")
