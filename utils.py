# utils.py
import streamlit as st

def sidebar_institucional():
    st.logo("assets/logo.png", link="https://www.penalolen.cl")
    with st.sidebar:
        st.markdown(
            "<div style='padding:10px 0 18px 0'>"
            "<span style='font-size:1.1rem;font-weight:700;'>🏛️ Peñalolén</span><br>"
            "<span style='font-size:0.8rem;opacity:0.7;'>Transparencia Presupuestaria</span>"
            "</div>",
            unsafe_allow_html=True,
        )
