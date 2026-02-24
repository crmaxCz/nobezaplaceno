import streamlit as st
import subprocess
import os

# 1. Oprava instalace: Musíme nejdřív zkusit importovat, a když to nejde, tak doinstalovat.
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # Pokud knihovna chybí, nainstalujeme ji (to se stane při prvním spuštění)
    subprocess.run(["pip", "install", "playwright"])
    from playwright.sync_api import sync_playwright

# 2. Instalace prohlížeče Chromium (pokud ještě není)
# Toto spustíme jen jednou při startu aplikace
if "playwright_installed" not in st.session_state:
    os.system("playwright install chromium")
    st.session_state["playwright_installed"] = True

import pandas as pd
import re

# Tvůj přesný seznam poboček v požadovaném pořadí
POBOCKY = {
    "136": "Praha",
    "137": "Brno",
    "268": "Plzeň",
    "354": "Ostrava",
    "133": "Olomouc",
    "277": "Hradec Králové",
    "326": "Liberec",
    "387": "Pardubice",
    "151": "Nový Jičín",
    "321": "Frýdek - Místek",
    "237": "Havířov",
    "203": "Opava",
    "215": "Trutnov",
    "400": "Zlín"
}

st.set_page_config(page_title="AŠ NOBE Statistiky", layout="wide")

st.title("📊 Dashboard obsazenosti a plateb NOBE")

# --- FUNKCE PRO SCRAPING ---
def scrape_data(username, password, selected_pobocky_ids):
    data_list = []
    
    with sync_playwright() as p:
        # Instalace prohlížeče přímo v rámci běhu (nutné pro Streamlit Cloud)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Přihlášení
        try:
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="prihlasovaci_jmeno"]', username)
            page.fill('input[name="heslo"]', password)
            page.click('input[type="submit"]')
            page.wait_for_load_state("networkidle")
            
            for pid in selected_pobocky_ids:
                nazev_pobocky = POBOCKY[pid]
                st.info(f"Stahuji data pro: {nazev_pobocky}...")
                
                # Načtení seznamu termínů pro pobočku
                url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od=01.01.2024&vytez_typ=545&vytez_lokalita={pid}&akce=prednasky_filtr"
                page.goto(url_seznam)
                
                # Najdeme všechny odkazy na detaily (edit_id)
                links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
                urls = list(set([l.get_attribute("href") for l in links]))
                
                for detail_url in urls:
                    page.goto(f"https://nobe.moje-autoskola.cz/{detail_url}")
                    
                    # Získání názvu/data z nadpisu
                    termin_name = page.inner_text("h1").replace("Přednáška - ", "")
                    
                    # Analýza tabulky žáků
                    rows = page.query_selector_all("#table_seznam_zaku tr")
                    
                    prihlaseno = 0
                    uhrazeno = 0
                    
                    for row in rows:
                        cells = row.query_selector_all("td")
                        if len(cells) > 5:
                            prihlaseno += 1
                            platba_text = cells[5].inner_text()
                            # Logika: pokud je tam cokoliv před "z", považujeme za uhrazeno
                            if re.search(r'\d.*z', platba_text):
                                uhrazeno += 1
                    
                    data_list.append({
                        "Pobočka": nazev_pobocky,
                        "Termín": termin_name,
                        "Přihlášeno": prihlaseno,
                        "Uhrazeno": uhrazeno
                    })
        except Exception as e:
            st.error(f"Chyba při scrapování: {e}")
        
        browser.close()
    return pd.DataFrame(data_list)

# --- BOČNÍ PANEL ---
user = st.secrets["moje_jmeno"]
pw = st.secrets["moje_heslo"]

with st.sidebar:
    st.header("Ovládání")
    st.info(f"Přihlášen jako: {user}") # Jen pro info, že to funguje
    
    st.subheader("Výběr poboček")
    selected_names = st.multiselect("Vyber pobočky", options=list(POBOCKY.values()), default=list(POBOCKY.values()))
    selected_ids = [k for k, v in POBOCKY.items() if v in selected_names]

    run_btn = st.button("🚀 Spustit aktualizaci")

# --- HLAVNÍ PLOCHA ---
if run_btn:
    if not user or not pw:
        st.warning("Zadejte prosím přihlašovací údaje.")
    else:
        results_df = scrape_data(user, pw, selected_ids)
        if not results_df.empty:
            st.session_state['data'] = results_df
            st.success("Data byla úspěšně načtena!")

if 'data' in st.session_state:
    df = st.session_state['data']
    
    # Výpočty
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    df['% Uhrazeno'] = (df['Uhrazeno'] / df['Přihlášeno'] * 100).round(1)

    # Celkové statistiky v kartách
    c1, c2, c3 = st.columns(3)
    c1.metric("Celkem přihlášeno", df['Přihlášeno'].sum())
    c2.metric("Celkem uhrazeno", df['Uhrazeno'].sum())
    c3.metric("Průměrná úhrada", f"{df['% Uhrazeno'].mean().round(1)} %")

    # Grafy
    st.subheader("Vizualizace termínů")
    st.bar_chart(df, x="Termín", y=["Uhrazeno", "Neuhrazeno"])
    
    # Detailní tabulka
    st.subheader("Detailní data")
    st.dataframe(df.sort_values(by="Pobočka"), use_container_width=True)
