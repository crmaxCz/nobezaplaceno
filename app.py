import streamlit as st
import subprocess
import pandas as pd
from datetime import datetime, timedelta

# --- 1. ZÁKLADNÍ INSTALACE ---
def install_playwright_browser():
    if "browser_installed" not in st.session_state:
        with st.spinner("Instalace prohlížeče..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright_browser()
from playwright.sync_api import sync_playwright

# --- 2. KONFIGURACE ---
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

st.set_page_config(page_title="NOBE - Seznam termínů", layout="wide")

# Přihlašovací údaje ze Secrets
USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

# --- 3. JEDNODUCHÝ SCRAPER (Jen seznam) ---
def get_only_list(pobocka_id, username, password):
    seznam_terminu = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # 1. Login
            page.goto("https://nobe.moje-autoskola.cz/index.php")
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            page.wait_for_url("**/index.php*")
            
            # 2. Skok na filtr
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="domcontentloaded")
            
            # 3. Najdeme všechny řádky v tabulce, které mají třídu text-warning (podle tvého HTML)
            rows = page.query_selector_all("tr.text-warning")
            
            for row in rows:
                link_el = row.query_selector("td a")
                if link_el:
                    text_terminu = link_el.inner_text().strip()
                    href = link_el.get_attribute("href")
                    
                    # Zkusíme vytáhnout i lektora (3. sloupec v tvém HTML)
                    cells = row.query_selector_all("td")
                    lektor = cells[2].inner_text().strip() if len(cells) > 2 else "Neznámý"
                    
                    seznam_terminu.append({
                        "Datum a čas": text_terminu,
                        "Lektor": lektor,
                        "URL": f"https://nobe.moje-autoskola.cz{href}"
                    })

        except Exception as e:
            st.error(f"Došlo k chybě: {e}")
        finally:
            browser.close()
            
    return pd.DataFrame(seznam_terminu)

# --- 4. JEDNODUCHÉ UI ---
st.title("Seznam přednášek (Příští 3 měsíce)")

with st.sidebar:
    pobocka_nazev = st.selectbox("Vyber pobočku:", list(POBOCKY.values()))
    pobocka_id = [k for k, v in POBOCKY.items() if v == pobocka_nazev][0]
    potvrdit = st.button("Načíst seznam")

if potvrdit:
    with st.spinner("Stahuji seznam z Moje Autoškola..."):
        df = get_only_list(pobocka_id, USER, PW)
        
        if not df.empty:
            st.success(f"Nalezeno {len(df)} termínů pro pobočku {pobocka_nazev}")
            st.table(df) # Použijeme st.table pro nejjednodušší zobrazení
        else:
            st.warning("Žádné termíny nebyly nalezeny. Zkontroluj, zda jsou v daném období nějaké vypsané.")
else:
    st.info("Vyber pobočku vlevo a klikni na 'Načíst seznam'.")
