import streamlit as st
import subprocess
import pandas as pd
import time

# 1. Instalace prohlížeče
def install_playwright():
    if "browser_installed" not in st.session_state:
        with st.spinner("Instalace jádra..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright()
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="NOBE - Pouze Tabulka", layout="wide")

# Přihlašovací údaje
USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

def scrape_simple_table(pob_id):
    data = []
    with sync_playwright() as p:
        # Spuštění prohlížeče
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # KROK 1: Login
            st.write("🔑 Přihlašování...")
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', USER)
            page.fill('input[name="log_heslo"]', PW)
            page.click('input[type="submit"]')
            
            # Počkáme 5 sekund na jistotu, že login proběhl
            time.sleep(5)

            # KROK 2: Přímý skok na tvoji URL
            # Upravil jsem datum na 26.01.2026, jak jsi chtěl
            target_url = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od=26.01.2026&vytez_datum_do=&vytez_typ=545&vytez_ucitel=&vytez_lokalita={pob_id}&akce=prednasky_filtr"
            st.write(f"🌐 Otevírám: {target_url}")
            
            # Jdeme na stránku a neřešíme, jestli se načetla celá (timeout ignorujeme)
            try:
                page.goto(target_url, timeout=60000)
            except:
                st.write("⚠️ Stránka se načítá pomalu, ale zkusím číst data...")

            # Počkáme 5 sekund, aby se vygenerovalo HTML
            time.sleep(5)

            # KROK 3: Sebrat všechny řádky tabulky
            # Najdeme všechny řádky <tr>, které v sobě mají odkaz na přednášku
            rows = page.query_selector_all("tr")
            
            for row in rows:
                inner_html = row.inner_html()
                if "admin_prednaska.php?edit_id=" in inner_html:
                    cells = row.query_selector_all("td")
                    if len(cells) >= 5:
                        data.append({
                            "Datum": cells[0].inner_text().strip(),
                            "Předmět": cells[1].inner_text().strip(),
                            "Učitel": cells[2].inner_text().strip(),
                            "Místo": cells[3].inner_text().strip()
                        })

        except Exception as e:
            st.error(f"❌ Chyba: {e}")
        finally:
            browser.close()
    return data

# --- JEDNODUCHÉ ROZHRANÍ ---
st.title("Výpis přednášek z Moje Autoškola")

# Seznam ID poboček (přidal jsem Liberec jako výchozí)
pob_id = st.text_input("ID Lokality (např. 326 pro Liberec):", value="326")

if st.button("STÁHNOUT TABULKU"):
    with st.spinner("Stahuji data..."):
        vysledek = scrape_simple_table(pob_id)
        
        if vysledek:
            st.success(f"Nalezeno {len(vysledek)} záznamů.")
            df = pd.DataFrame(vysledek)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("Tabulka nebyla nalezena. Buď je v daném období prázdná, nebo se stránka nenačetla včas.")
