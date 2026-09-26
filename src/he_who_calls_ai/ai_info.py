import os
import time
from google import genai
from google.genai import types
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
def query_gemini(
    prompt: str, 
    system_prompt: Optional[str] = None, 
    model: str = "gemini-3.8-flash",
    max_retries: int = 3,
    retry_delay: float = 6.0,
) -> str:
    """
    Sends a query to the Gemini API and returns the generated text.
    
    Args:
        prompt (str): The main user query.
        system_prompt (str, optional): Instructions for the model's persona/constraints.
        model (str): The Gemini model to use. Defaults to the free-tier Flash model.
        max_retries (int): Retry attempts on transient 503/429 errors (default 3).
        retry_delay (float): Initial wait in seconds between retries; doubles each time.
        
    Returns:
        str: The text response from the model.
    """
    # Initialize the client. It automatically picks up the GEMINI_API_KEY environment variable.
    client = genai.Client()
    
    # Configure generation parameters and inject the system prompt if provided
    config = types.GenerateContentConfig()
    if system_prompt:
        config.system_instruction = system_prompt

    delay = retry_delay
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            err = str(e)
            transient = ("503" in err or "UNAVAILABLE" in err
                         or "429" in err or "RESOURCE_EXHAUSTED" in err)
            if transient and attempt < max_retries:
                print(f"Gemini transient error (attempt {attempt}/{max_retries}): retrying in {delay:.0f}s ...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"Gemini API Error: {e}")
                return ""
# Optional: Quick test execution if you run this file directly
if __name__ == "__main__":
    # Make sure to set your API key in your terminal before running:
    # export GEMINI_API_KEY="your_api_key_here"
    
    test_response = query_gemini(
        prompt="Suggest an AI-related DEL with no midsem.",
        system_prompt="You are a strict BITS Pilani course recommender.",
        model="gemini-3.8-flash" 
    )
    print("Test Response:", test_response)