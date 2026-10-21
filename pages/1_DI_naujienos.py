from pathlib import Path

import streamlit as st

# Puslapio nustatymai
st.set_page_config(page_title="DI naujienos", page_icon="🎬")
st.title("🎬 DI naujienų reelsas")

# Įterpk animuotą reelsą iš HTML failo
reel_path = Path(__file__).parent.parent / "reels" / "index.html"

if hasattr(st, "iframe"):
    # Naujesnės Streamlit versijos (components.html pasenęs ir šalinamas)
    st.iframe(reel_path, height=760)
else:
    # Senesnės Streamlit versijos
    import streamlit.components.v1 as components

    components.html(reel_path.read_text(encoding="utf-8"), height=760)
