from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Puslapio nustatymai
st.set_page_config(page_title="DI naujienos", page_icon="🎬")
st.title("🎬 DI naujienų reelsas")

# Įterpk animuotą reelsą iš HTML failo
reel_html = (Path(__file__).parent.parent / "reels" / "index.html").read_text(encoding="utf-8")
components.html(reel_html, height=760)
