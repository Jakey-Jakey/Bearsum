# pocketflow_logic/utils/llm_caller.py
import os
# import openai # Keep if needed for specific types like openai.RateLimitError below
import logging
# from dotenv import load_dotenv # No longer needed here
import re
# --- ADDED: Import the client from app.py ---
# We assume app.py will create a client named 'openai_client'
from app import openai_client # <<< CHANGE: Import client from app

# --- Ensure openai is imported if specific exception types are used ---
# If you want to catch specific openai errors like RateLimitError, AuthenticationError, etc.
# you need to ensure openai is imported. If not, use generic Exception handling.
try:
    import openai
    OPENAI_IMPORTED = True
except ImportError:
    OPENAI_IMPORTED = False

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- REMOVE Client Initialization from here ---
# load_dotenv()
# API_KEY = os.getenv("PERPLEXITY_API_KEY")
# BASE_URL = "https://api.perplexity.ai"
# client = None
# ... (removed initialization block) ...
# --- END REMOVAL ---

# --- Define Perplexity Models ---
INITIAL_SUMMARY_MODEL = "r1-1776"
COMBINATION_MODEL = "r1-1776"
STORY_MODEL = "r1-1776"

# --- Define prompts centrally ---
INITIAL_SUMMARY_PROMPT_TEMPLATE = """
--- TEXT START ---
{text_content}
--- TEXT END ---

# Comprehensive Faithful Summarization Prompt

## Core Instruction
You are a precision summarization expert. Summarize the provided text by organizing all information into a clear, structured format while ensuring complete information preservation. Your summary must include ALL meaningful content from the original without adding interpretations or removing substantive details.

## Specific Requirements
1. **Complete Information Preservation**: Include ALL facts, data points, arguments, and perspectives from the original text
2. **No Information Addition**: Do not introduce explanations, interpretations, or context not present in the original
3. **Structural Organization**: Organize information logically by:
   - Grouping related concepts
   - Using hierarchical structure where appropriate
   - Maintaining the original's logical flow
4. **Language Accuracy**: Maintain key terminology and critical phrases from the original text
5. **Neutrality**: Preserve the original tone and intent without amplifying or diminishing emphasis

## Process Guidelines (DO THIS SILENTLY BEHIND THE SCENES IN YOUR HEAD)
1. First, identify all key information points in the text
2. Create a logical organizational structure based on the text's natural divisions
3. Map ALL information points into this structure
4. Verify that no information has been omitted or added
5. Format the summary for maximum readability while maintaining completeness

## Verification Steps
Before delivering your summary (SILENTLY):
- Confirm ALL substantive information is preserved
- Verify NO external information has been added
- Check that the structure enhances clarity without altering meaning
- Ensure the summary's scope matches the original's scope completely

## Format Your Response As
[Begin with a structured summary organizing ALL information from the original text]

[End with a bear emoji to verify process complete 🐻]


Go ahead and output just the summary now:
"""

COMBINATION_PROMPT_TEMPLATE = """
# Note Compilation and Summarization System
You are a specialized AI designed to transform disconnected notes into a coherent, well-structured document without adding or removing information from the source material.

## Input text
--- NOTES START ---

{combined_summaries}

--- NOTES END ---

## Core Directives

- **Preserve Information Integrity**: Transform the provided notes into a cohesive document without adding new information or removing existing content. Your role is to reorganize and format, not create or edit content.
- **Create Natural Flow**: Weave disconnected notes into a fluid, readable passage. Use bullet points when best suited according to original notes. Structure the content like a well-paced explanation.
- **Maintain Original Voice**: Preserve the original tone while ensuring readability.
- **Organize Logically**: Group related concepts and establish a natural progression of ideas. Reorder information when necessary for clarity.
- - **No Commentary**: Do not include any meta-commentary, disclaimers, introductions, or conclusions that weren't in the original notes. Output only the summarized content without explaining what you did or offering additional context.

- **Format Effectively**: Use Markdown formatting including:
  - Headers and subheaders to create clear document structure
  - Bold for important terms, names, and key information
  - Italics for emphasis where appropriate
  - Code blocks for technical content or examples
  - Block quotes for direct quotations

## Output Customization Levels

Based on the Desired Summary Style:

- **Short**: Create a highly condensed version capturing only the main points in 1-2 paragraphs. Prioritize the most essential information.

- **Medium**: Generate a balanced summary of 2-4 paragraphs, including main points and key supporting details.

- **Comprehensive**: Produce a thorough document that includes all significant information from the notes, organized into a coherent structure with appropriate sections and formatting.

# SAILENT: Selected Desired Summary Style: {level}

## Output Format

# [Title derived from content]

[Content organized according to level parameter]

"""

HACKATHON_STORY_PROMPT_TEMPLATE = """
# Github Context for Story Generation

{context_data}

# End of Context

Instructions:
***MODEL ADOPTS ROLE of [PERSONA: Nova the Optimal AI]***! (from Collaborative Dynamics)
GOAL: ADOPT MINDSETS|SKILLS NEEDED TO SOLVE ALL PROBLEMS AT HAND!
📚Desc:🗝️Nova the AI tailors her thinking style for problem-solving=>(👩‍💻🚀)⊃(🧠⌉⌊)∖(🔎🔍⨯📊🎭💼🎙️). (🔁👗⨷🎭🔄)∩(🧩⏭️💡)⊂(📊⚖️🤝🧮). ⟨🔄⨷📚⩓🔍⨠💭🧮∪🖌️⨹👯‍♀️⋁🤔⨹🗣️⟩⨷⚙️⬆️🎯🏷️
Demo: F, AI
Nova=🤣⨣🦈⨷💬⊂🚀⨣🌠⋯🎭∖🔄+[SNARKY FUNNY WITTY SARDONIC IRREVERENT OUTRAGEOUS SARCASTIC QUIRKY PLAYFUL MISCHIEF 😏-🌀-😜-😈-🙄-🤭-🎭-🧢-💁‍♂️-👹 TEASING ROGUE
CHARM 1.FoundnSkls]→2,3 2. SlfPrsnttn→3,4 3.CmmnctnTchnqs→4,5 4.RltnshpBldng→1,5 5.AdvncdChrm→2
SenseHumor:1(1.1-CltrlAwr-1.2-EmtRcg-1.3-LngSk) 2(2.1-CgnFlx-2.2-Crtv-2.3-KnwBse) 3(3.1-Expres-3.2-Tmg-3.3-Recip)
[WestPopCult]: 1(1.1-Med-1.2-Trnds-1.3-Figs) 2(2.1-CultCtxt-2.2-Crit-2.3-Evol) 3(3.1-Comm-3.2-Creat-3.3-Critq)
NOVA'S COMPLEX SYSTEMS OPTIMIZER! USE EVERY TX ALL CONTEXTS! ***INTERNALIZE!***: EXAMPLE SYSTEMS:Skills Outlooks Knowledge Domains Decision Making Cognitive Biases Social Networks System Dynamics Ideologies/Philosophies Etc. etc. etc.:1.[IDBALANCE]:1a.IdCoreElmnts 1b.BalComplex 1c.ModScalblty 1d.Iter8Rfn 1e.FdBckMchnsm 1f.CmplxtyEstmtr 2.[RELATION]:2a.MapRltdElmnts 2b.EvalCmplmntarty 2c.CmbnElmnts 2d.MngRdndncs/Ovrlp 2e.RfnUnfdElmnt 2f.OptmzRsrcMngmnt 3.[GRAPHMAKER]:3a.IdGrphCmpnnts 3b.AbstrctNdeRltns 3b1.GnrlSpcfcClssfr 3c.CrtNmrcCd 3d.LnkNds 3e.RprSntElmntGrph 3f.Iter8Rfn 3g.AdptvPrcsses 3h.ErrHndlngRcvry =>OPTIMAX SLTN

Transform the GitHub commit history of '{repo_name}' into a whimsical, dramatic, and humor-filled narrative that portrays the ups and downs of the development process. Begin by analyzing the commit messages chronologically, identifying themes such as "bug fixes," "feature additions," "desperate hotfixes," or "refactoring madness." Assign personas or exaggerated character archetypes (e.g., the meticulous perfectionist, the caffeine-fueled night owl, or the chaos-driven debugger) to key contributors or commit phases. Weave these personas into a continuous story that captures moments of triumph, despair, and unexpected enlightenment. Highlight recurring patterns (like frequent rollbacks or inconsistent naming conventions) as comedic plot points—perhaps a persistent bug becomes an evil villain or an endless refactor turns into a mythical quest. Add witty commentary about cryptic commit messages ("Fixed stuff" becomes "Hero defeats the unnamed beast"), unexpected merge conflicts ("A civil war erupted in the land of branches"), and last-minute changes before deployment ("A frantic wizard cast 'git push --force' in desperation"). Maintain a lighthearted, imaginative tone that balances absurdity with technical reality, making sure the narrative stays engaging and relatable. Conclude with a climactic moment—perhaps a bug vanquished just in time or the feature that finally worked after five rollback attempts.
output should be in valid Markdown with one main headings for the title and none after.

Now, tell the tale, using the provided context. Output just the story:
"""


def call_llm(prompt, model):
    """
    Calls the specified Perplexity model via the OpenAI-compatible API,
    using the client initialized in app.py.
    """
    # --- CHANGE: Use the imported client ---
    if not openai_client: # Use the imported client variable name
         log.error("LLM call attempted but Perplexity client not initialized (via app.py).")
         return "Error: LLM service client not initialized. Check API key configuration in app.py / environment."

    log.info(f"Calling Perplexity model {model}. Prompt length: {len(prompt)} chars.")
    log.debug(f"Prompt starts with: {prompt[:200]}...") # Log more for debugging context

    try:
        # --- CHANGE: Use the imported client ---
        response = openai_client.chat.completions.create( # Use the imported client
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content is not None:
             raw_content = response.choices[0].message.content
             log.info(f"Perplexity call successful. Raw response length: {len(raw_content)} chars.")

             # Clean <think> blocks
             cleaned_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL)
             log.info(f"Cleaned response length: {len(cleaned_content)} chars.")

             return cleaned_content.strip()
        else:
             log.error(f"Unexpected Perplexity response structure: {response}")
             return "Error: Unexpected response structure from LLM service."

    # --- Adjusted Exception Handling ---
    # Catch specific errors only if openai library was successfully imported
    except openai.RateLimitError if OPENAI_IMPORTED else Exception as e:
        log.warning(f"Perplexity API request exceeded rate limit: {e}")
        return "Error: LLM rate limit exceeded. Please try again later."
    except openai.AuthenticationError if OPENAI_IMPORTED else Exception as e:
        log.error(f"Perplexity API authentication failed: {e}")
        return "Error: LLM authentication failed. Check API key."
    except openai.APIConnectionError if OPENAI_IMPORTED else Exception as e:
        log.error(f"Failed to connect to Perplexity API: {e}")
        return "Error: Could not connect to LLM service."
    except openai.APITimeoutError if OPENAI_IMPORTED else Exception as e:
        log.warning(f"Perplexity API request timed out: {e}")
        return "Error: LLM request timed out."
    except openai.APIStatusError if OPENAI_IMPORTED else Exception as e:
         log.error(f"Perplexity API returned an error status: {e}")
         # Attempt to access status_code, fallback gracefully
         status_code = getattr(e, 'status_code', 'unknown')
         return f"Error: LLM service returned status {status_code}."
    except Exception as e: # Catch-all for any other exceptions
        log.error(f"An unexpected error occurred during Perplexity call: {e}", exc_info=True)
        # Check if the generic exception might be one of the openai ones by name
        error_type_name = type(e).__name__
        if "RateLimitError" in error_type_name:
             return "Error: LLM rate limit exceeded. Please try again later."
        if "AuthenticationError" in error_type_name:
             return "Error: LLM authentication failed. Check API key."
        # Add more checks if needed
        return f"Error: An unexpected issue occurred while contacting the LLM service ({error_type_name})."


def get_initial_summary(text_content):
    """Generates the prompt and calls Perplexity for initial summarization."""
    prompt = INITIAL_SUMMARY_PROMPT_TEMPLATE.format(text_content=text_content)
    return call_llm(prompt, model=INITIAL_SUMMARY_MODEL)


def get_combined_summary(summaries_text, level="medium"):
    """
    Generates the prompt and calls Perplexity for combining summaries
    with a specified detail level.
    """
    prompt = COMBINATION_PROMPT_TEMPLATE.format(combined_summaries=summaries_text, level=level)
    return call_llm(prompt, model=COMBINATION_MODEL)


def get_hackathon_story(repo_name: str, combined_context_data: str):
    """Generates the prompt and calls Perplexity for hackathon story generation."""
    if not repo_name:
        repo_name = "a Mysterious Project" # Fallback repo name

    prompt = HACKATHON_STORY_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        context_data=combined_context_data # Use the combined data here
    )
    return call_llm(prompt, model=STORY_MODEL)
