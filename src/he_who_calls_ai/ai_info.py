import ollama
from typing import Optional

def query_local_ollama(
    prompt: str, 
    system_prompt: Optional[str] = None, 
    model: str = "llama3.2"
) -> str:
    """
    prompt: main user query.
    system_prompt: Instructions for the model's constraints.
    """
    messages = []
    
    if system_prompt:
        messages.append({
            "role": "system", 
            "content": system_prompt
        })
        
    messages.append({
        "role": "user", 
        "content": prompt
    })

    try:
        response = ollama.chat(model=model, messages=messages)
        return response['message']['content']
    
    except ollama.ResponseError as e:
        print(f"Ollama API Error: {e.error}")
        return ""
    except Exception as e:
        print(f"Failed to connect to Ollama. Is the app running? Error: {e}")
        return ""

# Optional: Quick test execution if you run this file directly
if __name__ == "__main__":
    test_response = query_local_ollama(
        prompt="Suggest an AI-related DEL with no midsem.",
        system_prompt="You are a strict BITS Pilani course recommender.",
        model="llama3" # Replace with whichever model you pulled (e.g., mistral, phi3)
    )
    print("Test Response:", test_response)