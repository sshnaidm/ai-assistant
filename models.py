"""This module provides the language models."""

import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

gemini = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", temperature=0.0, top_p=0.0, google_api_key=os.getenv("GEMINI_API_KEY")
)

openai = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, top_p=0.0, api_key=os.getenv("OPENAI_API_KEY"))


# ollama based model
def ollama(ol_model):
    """Initialize the Ollama model."""
    return ChatOllama(model=ol_model, temperature=0.0, top_p=0.0, num_ctx=40000)


# ollama = ChatOllama(model="qwen2.5:7b", temperature=0.0, top_p=0.0, num_ctx=40000)


def init_llm() -> ChatOpenAI | ChatOllama | ChatGoogleGenerativeAI:
    """Initialize the LLM."""
    print("For choosing the model, set the MODEL environment variable to one of: openai, ollama/<model_name>, gemini")
    print("MODEL environment variable:", os.getenv("MODEL"))
    llm = None
    if os.getenv("MODEL"):
        if os.getenv("MODEL") == "openai":
            llm = openai
        elif os.getenv("MODEL").startswith("ollama"):
            llm = ollama(os.getenv("MODEL").replace("ollama/", ""))
        elif os.getenv("MODEL") == "gemini":
            llm = gemini
    else:
        llm = gemini

    print("LLM initialized:", llm)
    return llm
