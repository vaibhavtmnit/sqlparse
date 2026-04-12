import os
import google.generativeai as genai
from dotenv import load_dotenv

def list_models():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("FAIL: No API Key")
        return
        
    genai.configure(api_key=api_key)
    
    try:
        models = genai.list_models()
        print("Available Models:")
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"FAIL: {e}")

if __name__ == "__main__":
    list_models()
