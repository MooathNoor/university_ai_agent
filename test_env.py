
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    print("API Key loaded successfully ✅")
else:
    print("API Key not found ❌")