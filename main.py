import streamlit as st
import openai

# OpenAI klientas su slapta API rakto iškvietimu
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Chatbot", page_icon="🤖")
st.title("🤖 Chatbot")

user_input = st.text_input("Kuo galiu padėti?")

if user_input:
    with st.spinner("Rašau atsakymą..."):
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Tu esi naudingas padėjėjas."},
                {"role": "user", "content": user_input}
            ]
        )
        st.write(response.choices[0].message.content)
