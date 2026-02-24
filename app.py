import streamlit as st
import subprocess
import os
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. INSTALACE PROHLÍŽEČE ---
def install_playwright_browser():
    if "browser_installed" not in st.session_state:
        with st.spinner("Příprava systému (instalace Chromia)..."):
            try:
                # Instalace binárek pro Streamlit Cloud
                subprocess.run(["playwright", "install", "chromium"], check=True)
                st.session_state["browser_installed"] = True
            except Exception as e:
                st.error(f"Instalace prohlížeče selhala: {e}")

install_playwright_browser()
from playwright.sync_api import sync_playwright

# --- 2. KONFIGURACE ---
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

st.set_page_config(page_title="AŠ NOBE Statistiky", layout="wide")

# Načtení tajných údajů
try:
    USER = st.secrets["moje_jmeno"]
    PW = st.secrets["moje_heslo"]
except KeyError:
    st.error("Chybí přihlašovací údaje v Streamlit Secrets!")
    st.stop()

# --- 3. SCRAPER ---
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        # Spuštění s parametry pro stabilitu na cloudu
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        # Zrychlení: Blokování nepodstatných souborů
        page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())

        try:
            # A. PŘIHLÁŠENÍ
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            
            # Počkáme, až budeme uvnitř
            page.wait_for_url("**/index.php*", timeout=20000)

            # B. FILTR TERMÍNŮ
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="domcontentloaded")
            
            # Sběr odkazů na detaily přednášek
            links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
            urls = list(set([l.get_attribute("href") for l in links]))

            if not urls:
                return pd.DataFrame()

            # C. ANALÝZA JEDNOTLIVÝCH TERMÍNŮ
            status_placeholder = st.empty()
            progress_bar = st.progress(0)

            for i, detail_url in enumerate(urls[:20]): # Limit pro stabilitu
                full_url = f"https://nobe.moje-autoskola.cz/{detail_url}" if "http" not in detail_url else detail_url
                page.goto(full_url, wait_until="domcontentloaded")
                
                try:
                    # Název přednášky
                    termin_name = page.inner_text("h1", timeout=5000).replace("Přednáška - ", "").strip()
                    status_placeholder.text(f"Analyzuji: {termin_name}")

                    # Tabulka s třídou, kterou jsi zjistil
                    table = page.query_selector("table.table-striped")
                    if table:
                        rows = table.query_selector_all("tbody tr")
                        prihlaseno = 0
                        uhrazeno = 0
                        
                        for row in rows:
                            cells = row.query_selector_all("td")
                            # Kontrola: řádek žáka musí mít aspoň 5 buněk a nesmí to být suma ∑
                            if len(cells) >= 5:
                                row_text = row.inner_text()
                                if "∑" in row_text:
                                    continue
                                
                                prihlaseno += 1
                                # 5. sloupec (index 4) - Uhrazeno
                                payment_text = cells[4].inner_text().strip()
                                
                                # Čištění: bereme část před "z", odstraníme mezery a Kč
                                if 'z' in payment_text:
                                    paid_part = payment_text.split('z')[0]
                                    clean_value = re.sub(r'\D', '', paid_part)
                                    if clean_value and int(clean_value) > 0:
                                        uhrazeno += 1
                        
                        if prihlaseno > 0:
                            data_list.append({
                                "Termín": termin_name,
                                "Přihlášeno": prihlaseno,
                                "Uhrazeno": uhrazeno
                            })
                except:
                    continue
                progress_bar.progress((i + 1) / len(urls[:20]))

            status_placeholder.empty()
            progress_bar.empty()

        except Exception as e:
            st.error(f"Chyba při scrapování: {e}")
        finally:
            browser.close()

    return pd.DataFrame(data_list)

# --- 4. DASHBOARD UI ---
with st.sidebar:
    st.image("https://www.nobe.cz/wp-content/uploads/2021/03/logo-nobe-autoskola.png", width=150)
    st.header("📍 Výběr pobočky")
    vybrana_pobocka_nazev = st.radio("Zobrazit data pro:", options=list(POBOCKY.values()))
    vybrana_pobocka_id = [k for k, v in POBOCKY.items() if v == vybrana_pobocka_nazev][0]
    
    st.divider()
    if st.button("🔄 Aktualizovat data"):
        st.cache_data.clear()
        st.rerun()

st.title(f"Statistiky plateb – {vybrana_pobocka_nazev}")

# Volání funkce s cache
@st.cache_data(ttl=900)
def cached_data(p_id, p_name, u, p):
    return get_pobocka_data(p_id, p_name, u, p)

df = cached_data(vybrana_pobocka_id, vybrana_pobocka_nazev, USER, PW)

if not df.empty:
    # Výpočty
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    
    # Metriky
    m1, m2, m3 = st.columns(3)
    m1.metric("Celkem termínů", len(df))
    m2.metric("Přihlášeno celkem", df['Přihlášeno'].sum())
    m3.metric("Uhrazeno celkem", df['Uhrazeno'].sum())

    # Graf
    st.subheader("Vizualizace obsazenosti a plateb")
    st.bar_chart(df.set_index("Termín")[["Uhrazeno", "Neuhrazeno"]])

    # Tabulka
    st.subheader("Detailní přehled")
    st.dataframe(df, use_container_width=True)
else:
    st.info("Pro vybranou pobočku nebyla nalezena žádná data o budoucích přednáškách.")
