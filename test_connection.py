from dotenv import load_dotenv
from openai import OpenAI
import os

# Load the API key from .env into the environment
load_dotenv()

# Groq uses the OpenAI-compatible API, so we use the OpenAI client
# but point it at Groq's servers instead of OpenAI's
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Send a simple message and get a response
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    max_tokens=200,
    messages=[
        {"role": "user", "content": "Say hello in one short sentence, and confirm you're working."}
    ]
)

# Print just the text of the reply
print(response.choices[0].message.content)