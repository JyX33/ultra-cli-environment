import openai
from app.core.config import config

openai.api_key = config.OPENAI_API_KEY


def summarize_content(content: str, prompt_type: str) -> str:
    """
    Summarize content using OpenAI API.
    
    Args:
        content: The text content to summarize
        prompt_type: Either "post" or "comments" to determine the system prompt
        
    Returns:
        String containing the AI-generated summary or error message
    """
    try:
        if prompt_type == "post":
            system_prompt = "Summarize the following article text concisely."
        elif prompt_type == "comments":
            system_prompt = "Summarize the following Reddit comments, capturing the overall community sentiment and key discussion points."
        else:
            raise ValueError(f"Invalid prompt_type: {prompt_type}")
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
        )
        
        return response['choices'][0]['message']['content']
        
    except Exception:
        return "AI summary could not be generated."