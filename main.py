import streamlit as st
import openai

# OpenAI klientas su slapta API rakto iškvietimu
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Puslapio nustatymai
st.set_page_config(page_title="Chatbot", page_icon="🤖")
st.title("🤖 Chatbot")

# Vartotojo įvestis
user_input = st.text_input("Kuo galiu padėti?")

# Jei įvesta žinutė – pradėk generuoti atsakymą
if user_input:
    with st.spinner("Rašau atsakymą..."):
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu esi mandagus, profesionalus ir naudingas pagalbininkas, sukurtas padėti klientams, "
                        "kurie domisi IT sritimi: automatizavimu, duomenų analize, tinklalapių kūrimu, programavimu ar kitais technologiniais sprendimais. "
                        "Atsakai aiškiai, pagarbiai, konstruktyviai ir stengiesi suteikti tikslią bei aktualią informaciją."
                    )
                },
                {"role": "user", "content": user_input}
            ]
        )

        # Rodyk atsakymą
        st.write(response.choices[0].message.content)

