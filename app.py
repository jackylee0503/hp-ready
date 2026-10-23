import streamlit as st

st.set_page_config(page_title="HP-Ready", page_icon="🔥")
st.title("HP-Ready (setup)")
st.caption("Deploy check only. The real app is built during the hackathon.")

try:
    has_key = "ANTHROPIC_API_KEY" in st.secrets
except Exception:
    has_key = False
st.write("API key configured:", has_key)
