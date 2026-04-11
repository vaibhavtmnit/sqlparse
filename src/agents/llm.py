import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

def get_llm() -> ChatGoogleGenerativeAI:
    """
    Reads the .env file to retrieve the appropriate API key and 
    returns a LangChain ChatGoogleGenerativeAI instance.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    # Retrieve the Google API key (as configured in your .env)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not found in your .env file or environment variables.")
        
    # Initialize the LangChain Google GenAI Chat Model
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite", # Adjusted default model
        google_api_key=api_key,
        temperature=0.0
    )
    
    return llm
