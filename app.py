import streamlit as st
import subprocess
import pandas as pd
import time

# 1. Instalace Playwrightu (nutné pro Streamlit Cloud)
def install_playwright():
    if "browser_installed" not in st.session_state:
        with st.spinner("Instalace prohlížeče..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright()
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="NOBE Scraper", layout="wide")

# Přihlašovací údaje z tvého nastavení Streamlit (Secrets)
USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

def get_simple_list():
    data = []
    with sync_playwright() as p:
        # Spuštění prohlížeče v "lehkém" módu
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # KROK 1: Přihlášení
            st.info("Probíhá přihlášení...")
            page.goto("https://nobe.moje-autoskola.cz/index.php")
            page.fill('input[name="log_email"]', USER)
            page.fill('input[name="log_heslo"]', PW)
            page.click('input[type="submit"]')
            
            # Počkáme 5 sekund, než systém zpracuje login
            time.sleep(5)

            # KROK 2: Skok přímo na tvou cílovou URL
            target_url = "https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od=26.01.2026&vytez_datum_do=&vytez_typ=545&vytez_ucitel=&vytez_lokalita=326&akce=prednasky_filtr"
            st.info(f"Otevírám seznam termínů...")
            
            # Jdeme na stránku, timeout nastavíme na 60s
            page.goto(target_url, timeout=60000)
            
            # Počkáme 5 sekund na vykreslení tabulky
            time.sleep(5)

            # KROK 3: Sběr dat z tabulky
            # Najdeme všechny řádky tabulky <tr>
            rows = page.query_selector_all("tr")
            
            for row in rows:
                inner_text = row.inner_text()
                # Hledáme pouze řádky, které obsahují odkaz na detail přednášky
                if "admin_prednaska.php?edit_id=" in (row.inner_html() or ""):
                    cells = row.query_selector_all("td")
                    if len(cells) >= 3:
                        data.append({
                            "Datum a čas": cells[0].inner_text().strip(),
                            "Název": cells[1].inner_text().strip(),
                            "Lektor": cells[2].inner_text().strip(),
                            "Lokalita": cells[3].inner_text().strip() if len(cells) > 3 else "Liberec"
                        })

        except Exception as e:
            st.error(f"Chyba při scrapování: {e}")
        finally:
            browser.close()
    return data

# --- JEDNODUCHÉ UI ---
st.title("Seznam přednášek - Liberec")

if st.button("STÁHNOUT DATA"):
    with st.spinner("Pracuji na tom..."):
        vysledek = get_simple_list()
        
        if vysledek:
            st.success(f"Nalezeno {len(vysledek)} termínů.")
            df = pd.DataFrame(vysledek)
            st.table(df)
        else:
            st.warning("Žádná data nebyla nalezena. Ověřte, zda jsou pro toto období v systému vypsané přednášky.")
