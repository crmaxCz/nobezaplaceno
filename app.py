import streamlit as st
import subprocess
import pandas as pd
import time
from datetime import datetime, timedelta

# 1. INSTALACE
def install_playwright():
    if "browser_installed" not in st.session_state:
        subprocess.run(["playwright", "install", "chromium"])
        st.session_state["browser_installed"] = True

install_playwright()
from playwright.sync_api import sync_playwright

# 2. CONFIG
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

st.set_page_config(page_title="NOBE - Seznam termínů", layout="wide")

def get_data(pob_id):
    results = []
    # Dnešní datum pro filtr
    dnes = datetime.now().strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        # ZRYCHLENÍ: Blokujeme všechno kromě dokumentu
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "style", "font", "script"] else route.continue_())

        try:
            # LOGIN
            page.goto("https://nobe.moje-autoskola.cz/index.php")
            page.fill('input[name="log_email"]', USER)
            page.fill('input[name="log_heslo"]', PW)
            page.click('input[type="submit"]')
            time.sleep(3) # Počkáme na zpracování login

            # FILTR (Tvůj odkaz)
            url = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_typ=545&vytez_lokalita={pob_id}&akce=prednasky_filtr"
            st.write(f"Načítám: {url}")
            
            # Jdeme na stránku, ale nečekáme na status "Hotovo"
            page.goto(url, wait_until="commit") 
            time.sleep(5) # Pevná pauza na vykreslení tabulky

            # EXTRAKCE - Hledáme všechny řádky, které vypadají jako tvůj kód
            rows = page.query_selector_all("tr")
            for row in rows:
                if "admin_prednaska.php?edit_id=" in (row.inner_html() or ""):
                    cells = row.query_selector_all("td")
                    if len(cells) >= 3:
                        results.append({
                            "Datum": cells[0].inner_text().strip(),
                            "Předmět": cells[1].inner_text().strip(),
                            "Učitel": cells[2].inner_text().strip(),
                            "ID": cells[0].query_selector("a").get_attribute("href").split("=")[-1] if cells[0].query_selector("a") else "N/A"
                        })
        except Exception as e:
            st.error(f"Chyba: {e}")
        finally:
            browser.close()
    return results

# --- UI ---
st.title("Termíny přednášek NOBE")

with st.sidebar:
    volba = st.selectbox("Pobočka:", list(POBOCKY.values()))
    pob_id = [k for k, v in POBOCKY.items() if v == volba][0]
    run = st.button("Ukaž termíny")

if run:
    with st.spinner("Pracuji..."):
        data = get_data(pob_id)
        if data:
            df = pd.DataFrame(data)
            st.success(f"Nalezeno {len(df)} termínů.")
            st.table(df)
        else:
            st.warning("Nepodařilo se nic najít. Pravděpodobně timeout na straně serveru.")
