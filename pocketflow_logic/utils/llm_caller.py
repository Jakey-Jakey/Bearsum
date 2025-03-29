# pocketflow_logic/utils/llm_caller.py
import os
import openai # Use the openai library as recommended by Perplexity docs
import logging
from dotenv import load_dotenv

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Load environment variables at module load time
load_dotenv()
# --- Use Perplexity API Key ---
API_KEY = os.getenv("PERPLEXITY_API_KEY")
# --- Perplexity API Base URL ---
BASE_URL = "https://api.perplexity.ai"

client = None # Initialize client as None

if not API_KEY:
    log.warning("PERPLEXITY_API_KEY environment variable not set. LLM calls will fail.")
else:
    try:
        # --- Configure OpenAI client for Perplexity ---
        client = openai.OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )
        log.info("Perplexity client (via OpenAI library) initialized successfully.")
    except Exception as e:
         log.error(f"Failed to initialize Perplexity client: {e}", exc_info=True)
         # client remains None

# --- Define Perplexity Models ---
# Using smaller/faster Sonar Llama 3 model for initial summaries
INITIAL_SUMMARY_MODEL = "sonar"
# Using larger Sonar Llama 3 model for potentially better combination
COMBINATION_MODEL = "sonar"

# --- Define prompts centrally ---
INITIAL_SUMMARY_PROMPT_TEMPLATE = """
Summarize the following text concisely, capturing the main points:

--- TEXT START ---
{text_content}
--- TEXT END ---

Concise Summary:
"""

# --- Updated Combination Prompt Template ---
COMBINATION_PROMPT_TEMPLATE = """
Combine the following summaries into a single, coherent document. Preserve the key information from each summary. Structure the output clearly.

**Desired Summary Style:** {level}

--- SUMMARIES START ---
{combined_summaries}
--- SUMMARIES END ---

Instructions based on Desired Summary Style:
- If 'Short': Generate a very concise summary, capturing only the absolute main points in 1-2 sentences.
- If 'Medium': Generate a standard summary, balancing detail and brevity, typically 1-2 paragraphs.
- If 'Comprehensive': Generate a detailed summary covering all significant points presented in the provided summaries. Aim for thoroughness.

Coherent Combined Document ({level}):
"""
# -----------------------------------------

# --- call_llm function remains the same ---
def call_llm(prompt, model):
    """
    Calls the specified Perplexity model via the OpenAI-compatible API.

    Args:
        prompt (str): The prompt to send to the LLM.
        model (str): The Perplexity model name to use (e.g., 'llama-3-sonar-small-8b-chat').

    Returns:
        str: The LLM's response content, or an error message string.
    """
    if not client:
         log.error("LLM call attempted but Perplexity client not initialized.")
         return "Error: LLM service client not initialized. Check API key configuration."

    log.info(f"Calling Perplexity model {model}. Prompt length: {len(prompt)} chars.")
    log.debug(f"Prompt starts with: {prompt[:100]}...")

    try:
        # Use the same chat completions structure
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
            # Add other parameters like temperature, max_tokens if needed
            # e.g., temperature=0.7, max_tokens=1024
        )

        # Check response structure (same as before)
        if response.choices and response.choices[0].message and response.choices[0].message.content is not None:
             content = response.choices[0].message.content
             log.info(f"Perplexity call successful. Response length: {len(content)} chars.")
             return content.strip()
        else:
             log.error(f"Unexpected Perplexity response structure: {response}")
             return "Error: Unexpected response structure from LLM service."

    # --- Error handling remains largely the same, using openai exceptions ---
    except openai.RateLimitError as e:
        log.warning(f"Perplexity API request exceeded rate limit: {e}")
        return "Error: LLM rate limit exceeded. Please try again later."
    except openai.AuthenticationError as e:
        # This error will trigger if the PERPLEXITY_API_KEY is invalid
        log.error(f"Perplexity API authentication failed: {e}")
        return "Error: LLM authentication failed. Check API key."
    except openai.APIConnectionError as e:
        log.error(f"Failed to connect to Perplexity API: {e}")
        return "Error: Could not connect to LLM service."
    except openai.APITimeoutError as e:
        log.warning(f"Perplexity API request timed out: {e}")
        return "Error: LLM request timed out."
    except openai.APIStatusError as e: # Catch other API errors (e.g., 4xx, 5xx)
         log.error(f"Perplexity API returned an error status: {e}")
         return f"Error: LLM service returned status {e.status_code}."
    except Exception as e:
        log.error(f"An unexpected error occurred during Perplexity call: {e}", exc_info=True)
        return "Error: An unexpected issue occurred while contacting the LLM service."

# --- get_initial_summary remains the same ---
def get_initial_summary(text_content):
    """Generates the prompt and calls Perplexity for initial summarization."""
    prompt = INITIAL_SUMMARY_PROMPT_TEMPLATE.format(text_content=text_content)
    return call_llm(prompt, model=INITIAL_SUMMARY_MODEL)

# --- Updated get_combined_summary signature ---
def get_combined_summary(summaries_text, level="medium"):
    """
    Generates the prompt and calls Perplexity for combining summaries
    with a specified detail level.
    """
    prompt = COMBINATION_PROMPT_TEMPLATE.format(combined_summaries=summaries_text, level=level)
    return call_llm(prompt, model=COMBINATION_MODEL)
# ------------------------------------------