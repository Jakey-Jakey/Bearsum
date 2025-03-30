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
# Using smaller/faster Sonar model for initial summaries
INITIAL_SUMMARY_MODEL = "sonar" # Use updated model names if needed
# Using larger Sonar model for potentially better combination
COMBINATION_MODEL = "sonar" # Use updated model names if needed
# Use a capable model for creative writing
STORY_MODEL = "sonar"

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

# --- New Hackathon Story Prompt Template ---
HACKATHON_STORY_PROMPT_TEMPLATE = """
Transform a GitHub commit history of '{repo_name}' into a whimsical, dramatic, and humor-filled narrative that portrays the ups and downs of the development process. Begin by analyzing the commit messages chronologically, identifying themes such as "bug fixes," "feature additions," "desperate hotfixes," or "refactoring madness." Assign personas or exaggerated character archetypes (e.g., the meticulous perfectionist, the caffeine-fueled night owl, or the chaos-driven debugger) to key contributors or commit phases. Weave these personas into a continuous story that captures moments of triumph, despair, and unexpected enlightenment. Highlight recurring patterns (like frequent rollbacks or inconsistent naming conventions) as comedic plot points—perhaps a persistent bug becomes an evil villain or an endless refactor turns into a mythical quest. Add witty commentary about cryptic commit messages ("Fixed stuff" becomes "Hero defeats the unnamed beast"), unexpected merge conflicts ("A civil war erupted in the land of branches"), and last-minute changes before deployment ("A frantic wizard cast 'git push --force' in desperation"). Maintain a lighthearted, imaginative tone that balances absurdity with technical reality, making sure the narrative stays engaging and relatable. Conclude with a climactic moment—perhaps a bug vanquished just in time or the feature that finally worked after five rollback attempts.
output should be in valid Markdown.

Github Commit history:
{formatted_commits_str}

Now, tell the tale, output just the story:
"""


# --- call_llm function remains the same ---
def call_llm(prompt, model):
    """
    Calls the specified Perplexity model via the OpenAI-compatible API.

    Args:
        prompt (str): The prompt to send to the LLM.
        model (str): The Perplexity model name to use (e.g., 'llama-3-sonar-small-32k-chat').

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
            messages=[{"role": "user", "content": prompt}],
            # Add other parameters like temperature, max_tokens if needed
            # Consider adding temperature for more creative stories, e.g., temperature=0.8
            temperature=0.7
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

# --- New function for Hackathon Story ---
def get_hackathon_story(repo_name: str, formatted_commits_str: str):
    """Generates the prompt and calls Perplexity for hackathon story generation."""
    if not repo_name:
        repo_name = "a Mysterious Project" # Fallback repo name

    prompt = HACKATHON_STORY_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        formatted_commits_str=formatted_commits_str
    )
    return call_llm(prompt, model=STORY_MODEL)
