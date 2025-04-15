import openai

client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "Tu esi naudingas padėjėjas."},
        {"role": "user", "content": user_input}
    ]
)

st.write(response.choices[0].message.content)


