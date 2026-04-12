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

def get_embeddings():
    """
    Acts as a universal bridge for Embeddings. 
    Reads 'EMBEDDINGS_PROVIDER' and 'EMBEDDINGS_MODEL' from the environment,
    falling back to Google GenAI as the default.
    
    Supported Providers: 'google', 'openai', 'huggingface'
    """
    load_dotenv()
    
    provider = os.getenv("EMBEDDINGS_PROVIDER", "google").lower()
    custom_model = os.getenv("EMBEDDINGS_MODEL")
    
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings.")
        model_name = custom_model or "text-embedding-3-small"
        return OpenAIEmbeddings(model=model_name, openai_api_key=api_key)
        
    elif provider == "huggingface":
        # Requires langchain-huggingface and sentence-transformers
        from langchain_huggingface import HuggingFaceEmbeddings
        model_name = custom_model or "all-MiniLM-L6-v2"
        return HuggingFaceEmbeddings(model_name=model_name)
        
    else:
        # Default to Google
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for Google GenAI embeddings.")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        model_name = custom_model or "models/embedding-001"
        return GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=api_key)

