import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

def test_llm():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("FAIL: No API Key")
        return
        
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=api_key
    )
    
    try:
        res = llm.invoke("Hello, are you there?")
        print(f"SUCCESS: {res.content}")
    except Exception as e:
        print(f"FAIL: {e}")

if __name__ == "__main__":
    test_llm()
