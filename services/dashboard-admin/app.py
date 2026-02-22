# -*- coding: utf-8 -*-
import streamlit as st
import httpx
import pandas as pd
import json

API_URL = "http://api-gateway:8000"
ORCHESTRATOR_URL = "http://orchestrator:8001"
EVALUATOR_URL = "http://evaluator:8060"

st.set_page_config(page_title="UCAS Admin Panel", page_icon="⚙️", layout="wide")
st.title("⚙️ UCAS Management Dashboard")

# Inicjalizacja klucza do wymuszania odświeżania tabeli edytora
if "editor_key" not in st.session_state:
    st.session_state["editor_key"] = 0

def check_health():
    try:
        response = httpx.get(f"{ORCHESTRATOR_URL}/health", timeout=2.0)
        return response.status_code == 200, response.json()
    except:
        return False, {}

is_online, health_data = check_health()

with st.sidebar:
    if is_online:
        st.success("✅ Orchestrator Online")
        layers = health_data.get("layers", {})
        for layer, status in layers.items():
            st.write(f"{'🟢' if status == 'healthy' else '🔴'} {layer.upper()}")
    else:
        st.error("🔴 Orchestrator offline.")

tab_manage, tab_data, tab_test, tab_stats = st.tabs(["🗄️ Modele", "🗂️ Dane Treningowe", "🧪 Test API", "📊 Statystyki & Historia"])

try:
    cats_response = httpx.get(f"{API_URL}/categorizers", timeout=5.0)
    cat_list = [c["categorizer_id"] for c in cats_response.json()] if cats_response.status_code == 200 else []
except:
    cat_list = []

# ==========================================
# ZAKŁADKA 1: MODELE
# ==========================================
with tab_manage:
    st.header("Zarejestrowane Kategoryzatory")
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Odśwież listę", use_container_width=True):
            st.rerun()
            
    if not cat_list:
        st.info("Brak kategoryzatorów.")
    else:
        df = pd.DataFrame(cats_response.json())[['categorizer_id', 'name', 'created_at']]
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.subheader("Akcje")
        del_id = st.selectbox("Wybierz model do usunięcia", df['categorizer_id'].tolist())
        if st.button("🗑️ Usuń wybrany kategoryzator", type="primary"):
            del_resp = httpx.delete(f"{API_URL}/categorizers/{del_id}")
            if del_resp.status_code == 200:
                st.success(f"Usunięto {del_id}")
                st.rerun()
            else:
                st.error(f"Błąd usuwania: {del_resp.text}")

# ==========================================
# ZAKŁADKA 2: DANE TRENINGOWE I RETRENOWANIE
# ==========================================
with tab_data:
    st.header("Zarządzanie Danymi Treningowymi i Jakością")
    if not cat_list:
        st.info("Brak kategoryzatorów do edycji.")
    else:
        edit_cat = st.selectbox("Wybierz kategoryzator do edycji", cat_list, key="edit_sel")
        
        sub_edit, sub_quality = st.tabs(["✏️ Edycja Danych", "⭐ Ocena Jakości (Evaluator)"])
        
        with sub_edit:
            try:
                export_resp = httpx.get(f"{ORCHESTRATOR_URL}/categorizers/{edit_cat}/export", timeout=5.0)
                if export_resp.status_code == 200:
                    payload_data = export_resp.json()
                    
                    state_key = f"data_{edit_cat}"
                    if state_key not in st.session_state:
                        st.session_state[state_key] = payload_data.get("training_data", [])
                    
                    with st.expander("📥 Import danych z pliku CSV"):
                        uploaded_file = st.file_uploader("Wgraj plik CSV. Wymagane nazwy kolumn w pierwszym wierszu: 'text', 'category'", type=["csv"])
                        if uploaded_file is not None:
                            try:
                                df_in = pd.read_csv(uploaded_file)
                                if 'text' in df_in.columns and 'category' in df_in.columns:
                                    st.success(f"Poprawnie wczytano {len(df_in)} wierszy z pliku.")
                                    col_rep, col_app = st.columns(2)
                                    if col_rep.button("⚠️ Zastąp obecne dane (Overwrite)"):
                                        st.session_state[state_key] = df_in[['text', 'category']].to_dict('records')
                                        st.session_state["editor_key"] += 1
                                        st.rerun()
                                    if col_app.button("➕ Dołącz do obecnych (Append)"):
                                        st.session_state[state_key] = st.session_state[state_key] + df_in[['text', 'category']].to_dict('records')
                                        st.session_state["editor_key"] += 1
                                        st.rerun()
                                else:
                                    st.error("🔴 Błąd struktury. Plik musi zawierać kolumny 'text' oraz 'category'.")
                            except Exception as e:
                                st.error(f"🔴 Błąd odczytu pliku: {e}")

                    col_info, col_reset = st.columns([3, 1])
                    with col_info:
                        st.write("Edytuj teksty lub przypisane kategorie. Opcja eksportu jest wbudowana w tabelę (ikona w prawym górnym rogu).")
                    with col_reset:
                        if st.button("🔄 Zresetuj widok", use_container_width=True):
                            st.session_state[state_key] = payload_data.get("training_data", [])
                            st.session_state["editor_key"] += 1
                            st.rerun()
                    
                    df_samples = pd.DataFrame(st.session_state[state_key])
                    edited_df = st.data_editor(
                        df_samples, 
                        num_rows="dynamic", 
                        use_container_width=True, 
                        key=f"ed_{st.session_state['editor_key']}"
                    )
                    
                    if st.button("🔥 Zapisz i Przetrenuj Kategoryzator", type="primary"):
                        with st.spinner("Usuwanie starego modelu i uruchamianie nowego treningu... to potrwa dłuższą chwilę."):
                            httpx.delete(f"{API_URL}/categorizers/{edit_cat}", timeout=5.0)
                            
                            payload_data["training_data"] = edited_df.to_dict('records')
                            
                            train_resp = httpx.post(f"{API_URL}/train", json=payload_data, timeout=300.0)
                            
                            if train_resp.status_code == 200:
                                del st.session_state[state_key]
                                st.success("✅ Model przetrenowany z sukcesem!")
                                st.rerun()
                            else:
                                st.error(f"🔴 Błąd treningu: HTTP {train_resp.status_code} - {train_resp.text}")
                else:
                    st.error("Błąd pobierania danych treningowych.")
            except Exception as e:
                st.error(f"Błąd komunikacji: {e}")
                
        with sub_quality:
            st.write("Zarządzaj oceną wektorową. Próbki z oceną poniżej 0.1 zostaną wyeliminowane podczas kuracji.")
            
            c1, c2, c3 = st.columns(3)
            try:
                cur_resp = httpx.get(f"{EVALUATOR_URL}/curation_status/{edit_cat}", timeout=5.0)
                if cur_resp.status_code == 200:
                    cur_data = cur_resp.json()
                    c1.metric("Aktywne próbki", cur_data.get("total_active_samples", 0))
                    c2.metric("Nieocenione próbki", cur_data.get("unscored_count", 0))
                    avg_q = cur_data.get("avg_quality_score")
                    c3.metric("Średnia jakość bazy", f"{avg_q:.2f}" if avg_q else "Brak ocen")
            except Exception as e:
                st.warning("Evaluator offline lub brak danych z bazy.")

            colA, colB, colC = st.columns(3)
            with colA:
                if st.button("⚙️ Ocena pustych (partia 10)", use_container_width=True):
                    with st.spinner("Ocenianie..."):
                        try:
                            httpx.post(f"{EVALUATOR_URL}/score_batch", json={"categorizer_id": edit_cat, "batch_size": 10}, timeout=60.0)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Błąd komunikacji: {e}")
            with colB:
                if st.button("🧹 Uruchom kurację", use_container_width=True):
                    with st.spinner("Czyszczenie bazy..."):
                        try:
                            httpx.post(f"{EVALUATOR_URL}/run_curation", json={"categorizer_id": edit_cat}, timeout=60.0)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Błąd komunikacji: {e}")
            with colC:
                if st.button("🗑️ Wyzeruj wszystkie oceny", use_container_width=True):
                    with st.spinner("Zerowanie ocen..."):
                        try:
                            httpx.post(f"{EVALUATOR_URL}/reset_scores", json={"categorizer_id": edit_cat}, timeout=60.0)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Błąd komunikacji: {e}")
                        
            try:
                samples_resp = httpx.get(f"{ORCHESTRATOR_URL}/categorizers/{edit_cat}/training_samples?include_inactive=true", timeout=10.0)
                if samples_resp.status_code == 200:
                    s_data = samples_resp.json()
                    if s_data:
                        df_q = pd.DataFrame(s_data)
                        
                        req_cols = ["id", "text", "category", "quality_score", "is_active", "quality_reasoning"]
                        for col in req_cols:
                            if col not in df_q.columns:
                                df_q[col] = None
                                
                        df_q.insert(0, "Zaznacz", False)
                        
                        st.write("### Przeliczanie selektywne próbek")
                        edited_df_q = st.data_editor(
                            df_q,
                            column_config={
                                "id": None,
                                "Zaznacz": st.column_config.CheckboxColumn("Zaznacz", default=False)
                            },
                            disabled=["text", "category", "quality_score", "is_active", "quality_reasoning"],
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        selected_ids = edited_df_q[edited_df_q["Zaznacz"] == True]["id"].dropna().tolist()
                        
                        if st.button("🎯 Przelicz zaznaczone", type="primary"):
                            if selected_ids:
                                with st.spinner(f"Wymuszanie przeliczenia {len(selected_ids)} próbek..."):
                                    try:
                                        httpx.post(
                                            f"{EVALUATOR_URL}/score_specific", 
                                            json={"categorizer_id": edit_cat, "sample_ids": selected_ids}, 
                                            timeout=120.0
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Błąd podczas punktowania: {e}")
                            else:
                                st.warning("Zaznacz przynajmniej jedną próbkę na liście.")
                    else:
                        st.info("Brak danych.")
            except Exception as e:
                st.error(f"Błąd pobierania próbek z Orchestratora: {e}")

# ==========================================
# ZAKŁADKA 3: TEST API
# ==========================================
with tab_test:
    st.header("Interaktywny Test Klasyfikacji")
    if not cat_list:
        st.warning("Najpierw wytrenuj model przez API.")
    else:
        with st.form("classify_form"):
            selected_cat = st.selectbox("Kategoryzator", cat_list)
            input_text = st.text_area("Tekst", "Aplikacja zawiesza sie przy generowaniu raportu i zjada caly RAM.")
            strategy = st.radio("Strategia", ["cascade", "tags", "xgboost", "llm"], horizontal=True)
            debug_mode = st.checkbox("Zwróć surowy prompt w API (Debug)", value=True)
            
            if st.form_submit_button("🚀 Klasyfikuj"):
                with st.spinner("Analiza..."):
                    try:
                        resp = httpx.post(
                            f"{API_URL}/classify",
                            json={"categorizer_id": selected_cat, "text": input_text, "strategy": strategy, "return_prompt": debug_mode},
                            timeout=65.0
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Kategoria", data.get("category", "Brak"))
                            c2.metric("Pewność (Confidence)", f"{data.get('confidence', 0):.2%}")
                            c3.metric("Warstwa decyzyjna", data.get("method", "Brak"))
                            
                            if data.get("reasoning"):
                                st.warning(f"**Logika (Reasoning):** {data['reasoning']}")
                            
                            st.subheader("📦 Pełna odpowiedź JSON z API")
                            st.json(data)
                            
                            if data.get("prompt"):
                                st.subheader("🤖 Zwrócony Prompt (z osadzonym RAG)")
                                st.code(data["prompt"], language="markdown")
                                
                        else:
                            st.error(f"Błąd klasyfikacji: HTTP {resp.status_code} - {resp.text}")
                    except Exception as e:
                        st.error(f"Błąd komunikacji z API: {e}")

# ==========================================
# ZAKŁADKA 4: STATYSTYKI & HISTORIA
# ==========================================
with tab_stats:
    st.header("Statystyki Pracy Kaskady")
    if cat_list:
        colA, colB = st.columns([4, 1])
        with colA:
            stat_cat = st.selectbox("Wybierz kategoryzator", cat_list, key="stat_sel")
        with colB:
            if st.button("🔄 Odśwież statystyki", use_container_width=True):
                st.rerun()
        
        try:
            stats_resp = httpx.get(f"{ORCHESTRATOR_URL}/categorizers/{stat_cat}/stats")
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                c1, c2 = st.columns(2)
                c1.metric("Wszystkich żądań", stats.get("total_requests", 0))
                c2.metric("Średni czas", f"{stats.get('average_processing_time_ms', 0)} ms")
                
                st.write("**Dystrybucja warstw decyzyjnych:**")
                st.json(stats.get("method_distribution", {}))
        except:
            st.warning("Brak statystyk.")

        st.divider()
        st.subheader("Ostatnie 50 klasyfikacji (Pełen zrzut z bazy)")
        try:
            hist_resp = httpx.get(f"{ORCHESTRATOR_URL}/categorizers/{stat_cat}/history?limit=50")
            if hist_resp.status_code == 200:
                history = hist_resp.json()
                if not history:
                    st.info("Brak historii dla tego modelu.")
                for item in history:
                    time_str = item.get('created_at', '')[:19]
                    with st.expander(f"[{time_str}] {item['method'].upper()} -> {item['predicted_category']} ({item['confidence']:.2f})"):
                        st.write(f"**Tekst wejściowy:** {item['text']}")
                        st.write(f"**Czas przetwarzania:** {item['time_ms']:.2f} ms")
                        st.write(f"**Fallback:** {item['is_fallback']}")
                        if item.get("reasoning"):
                            st.write(f"**Reasoning:** {item['reasoning']}")
                        
                        st.markdown("**Dane techniczne (JSON):**")
                        st.json({
                            "id": item.get("id"),
                            "cascade_results": item.get("cascade_results")
                        })
                        
                        if item.get("prompt"):
                            st.markdown("**Surowy Prompt LLM:**")
                            st.code(item["prompt"], language="markdown")
        except Exception as e:
            st.error(f"Nie udało się pobrać historii z bazy. {e}")