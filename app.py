import streamlit as st
import subprocess
import os
import pandas as pd
import re
from datetime import datetime, timedelta

# 1. INSTALACE (Musí být na začátku)
def install_playwright_browser():
    if "browser_installed" not in st.session_state:
        with st.spinner("Instalace prohlížeče..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright_browser()
from playwright.sync_api import sync_playwright

# --- KONFIGURACE ---
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

st.set_page_config(page_title="AŠ NOBE Statistiky", layout="wide")

USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

# --- SCRAPER (DOČASNĚ BEZ @st.cache_data PRO LADĚNÍ) ---
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # KROK 1: Přihlášení
            st.info("Probíhá přihlašování...")
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            
            # Počkáme na potvrzení loginu
            page.wait_for_url("**/index.php*", timeout=20000)
            st.success("Přihlášení úspěšné!")

            # KROK 2: Seznam termínů
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="networkidle")
            
            links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
            urls = list(set([l.get_attribute("href") for l in links]))

            if not urls:
                st.warning(f"Na pobočce {pobocka_nazev} nebyly nalezeny žádné odkazy na termíny.")
                # Pro jistotu ukážeme, co robot vidí
                st.text(f"Obsah stránky: {page.inner_text('body')[:300]}")
                return pd.DataFrame()

            st.write(f"Nalezeno {len(urls)} termínů, analyzuji účastníky...")
            progress_bar = st.progress(0)

            # KROK 3: Procházení jednotlivých URL
            for i, detail_url in enumerate(urls[:15]): # Limit na 15 pro stabilitu
                full_url = f"https://nobe.moje-autoskola.cz/{detail_url}" if "http" not in detail_url else detail_url
                page.goto(full_url, wait_until="domcontentloaded")
                
                try:
                    termin_name = page.inner_text("h1", timeout=5000).replace("Přednáška - ", "").strip()
                    rows = page.query_selector_all("#table_seznam_zaku tr")
                    
                    prihlaseno = 0
                    uhrazeno = 0
                    
                    for row in rows:
                        cells = row.query_selector_all("td")
                        if len(cells) >= 6:
                            prihlaseno += 1
                            txt = cells[5].inner_text().split('z')[0]
                            num_str = "".join(filter(str.isdigit, txt))
                            if num_str and int(num_str) > 0:
                                uhrazeno += 1
                    
                    if prihlaseno > 0:
                        data_list.append({"Termín": termin_name, "Přihlášeno": prihlaseno, "Uhrazeno": uhrazeno})
                except:
                    continue
                progress_bar.progress((i + 1) / min(len(urls), 15))

        except Exception as e:
            st.error(f"Chyba: {str(e)}")
        finally:
            browser.close()

    return pd.DataFrame(data_list)

# --- UI ---
with st.sidebar:
    st.header("📍 Pobočky")
    vybrana_pobocka_nazev = st.radio("Vyberte pobočku:", options=list(POBOCKY.values()))
    vybrana_pobocka_id = [k for k, v in POBOCKY.items() if v == vybrana_pobocka_nazev][0]
    
    if st.button("🔄 Vymazat mezipaměť"):
        st.cache_data.clear()
        st.rerun()

st.title("Statistiky NOBE")
df = get_pobocka_data(vybrana_pobocka_id, vybrana_pobocka_nazev, USER, PW)

if not df.empty:
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    st.metric("Celkem uhrazeno (zobrazené termíny)", df['Uhrazeno'].sum())
    st.bar_chart(df.set_index("Termín")[["Uhrazeno", "Neuhrazeno"]])
    st.dataframe(df, use_container_width=True)
else:
    st.info("Zatím nebyla stažena žádná data. Zkuste změnit pobočku.")
