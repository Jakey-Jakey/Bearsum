# app.py
import gevent.monkey
gevent.monkey.patch_all()
import os
import uuid
import tempfile
import shutil
import logging
import threading
import markdown
import redis
import json
from datetime import datetime # Import datetime for formatting
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify, send_file
from flask_session import Session
from flask_sse import sse
from dotenv import load_dotenv

# Import PocketFlow flow creation function (if still needed, otherwise remove)
# from pocketflow_logic.flow import create_summary_flow

# Import utilities
from pocketflow_logic.utils import file_handler, llm_caller # <<< Ensure llm_caller is imported
# --- ADD Import for GitHub utils and exceptions ---
from pocketflow_logic.utils import github_utils
from pocketflow_logic.utils.github_utils import GitHubUrlError, RepoNotFoundError, GitHubApiError
# -------------------------------------------------

# --- Configuration ---
load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
app.logger.setLevel(logging.INFO)

# --- Flask-Session Configuration ---
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-replace-me!")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "./flask_session"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
Session(app)

# --- Flask-SSE Configuration ---
app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app.register_blueprint(sse, url_prefix='/stream')

# --- Redis Task Storage Functions ---
# Store results for both summarizer and story generator
# Structure in Redis: key="task_result:<task_id>", value=JSON string of {'type': 'summary'/'story', 'result': ..., 'errors': [], 'state': 'processing'/'completed'/'error'}
def store_task_result(task_id, result_type, state, result, errors=None):
    """Stores task result in Redis."""
    if errors is None:
        errors = []

    try:
        redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True) # decode_responses=True is helpful
        result_data = {
            'type': result_type,
            'state': state,
            'result': result,
            'errors': errors
        }
        # Store with expiration (e.g., 1 hour = 3600 seconds)
        redis_conn.setex(f"task_result:{task_id}", 3600, json.dumps(result_data))
        app.logger.info(f"Stored task {task_id} result in Redis (state={state})")
    except Exception as e:
        app.logger.error(f"Error storing task result in Redis for {task_id}: {e}", exc_info=True)

def get_task_result(task_id):
    """Retrieves task result from Redis."""
    try:
        redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        result_data_json = redis_conn.get(f"task_result:{task_id}")

        if result_data_json:
            return json.loads(result_data_json)
        return None
    except Exception as e:
        app.logger.error(f"Error retrieving task result from Redis for {task_id}: {e}", exc_info=True)
        return None

def delete_task_result(task_id):
    """Deletes task result from Redis."""
    try:
        redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        redis_conn.delete(f"task_result:{task_id}")
        app.logger.info(f"Deleted task {task_id} result from Redis")
    except Exception as e:
        app.logger.error(f"Error deleting task result from Redis for {task_id}: {e}", exc_info=True)

# Security check for default SECRET_KEY
if not app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
    app.logger.critical("SECURITY ALERT: Running in non-debug mode with default SECRET_KEY!")
    raise RuntimeError("FLASK_SECRET_KEY must be set to a strong, unique value in production (non-debug) mode.")
elif app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
     app.logger.warning("SECURITY WARNING: Using default SECRET_KEY in debug mode. Set FLASK_SECRET_KEY environment variable.")

# Pass file limits to template context via config
app.config['MAX_FILES'] = file_handler.MAX_FILES
app.config['MAX_FILE_SIZE_MB'] = file_handler.MAX_FILE_SIZE_MB

# --- Background Task Function (Summarizer) --- CORRECTED ---
def run_summarizer_async(task_id, temp_file_details, summary_level, original_filenames):
    """Runs the file summarization in a background thread."""
    with app.app_context():
        app.logger.info(f"Summarizer Task {task_id}: Background thread started.")
        # Initialize state in Redis
        store_task_result(task_id, 'summary', 'processing', None, [])
        final_state = "unknown" # Track the intended final state
        all_summaries = {}
        errors = []
        temp_dir = None # Initialize temp_dir

        try:
            sse.publish({"type": "status", "message": "Initializing summarization..."}, channel=task_id)

            # --- Simplified Logic (No PocketFlow) ---
            # 1. Process each file individually
            total_files = len(temp_file_details)
            if total_files > 0:
                 # Get temp_dir from the first file detail (assuming they are all in the same dir)
                 temp_dir = os.path.dirname(temp_file_details[0]['temp_path'])

            for i, file_detail in enumerate(temp_file_details):
                original_name = file_detail['original_name']
                temp_path = file_detail['temp_path']
                sse.publish({"type": "status", "message": f"Processing file {i+1}/{total_files}: '{original_name}'..."}, channel=task_id)

                content = file_handler.read_file_content(temp_path)
                if content is None:
                    error_msg = f"Could not read file: {original_name}"
                    errors.append(error_msg)
                    all_summaries[original_name] = f"Error: {error_msg}"
                    sse.publish({"type": "status", "message": f"Error reading '{original_name}'."}, channel=task_id)
                    continue
                if not content.strip():
                    all_summaries[original_name] = "Skipped: File is empty"
                    sse.publish({"type": "status", "message": f"Skipping '{original_name}': File is empty."}, channel=task_id)
                    continue

                sse.publish({"type": "status", "message": f"Requesting summary for '{original_name}'..."}, channel=task_id)
                summary = llm_caller.get_initial_summary(content)
                all_summaries[original_name] = summary
                if isinstance(summary, str) and summary.startswith("Error:"):
                    error_msg = f"LLM Error for '{original_name}': {summary}"
                    errors.append(error_msg)
                    sse.publish({"type": "status", "message": f"LLM Error for '{original_name}'."}, channel=task_id)
                else:
                    sse.publish({"type": "status", "message": f"Received summary for '{original_name}'."}, channel=task_id)

            # 2. Combine summaries if any were successful
            valid_summaries = {name: summ for name, summ in all_summaries.items() if isinstance(summ, str) and not summ.startswith("Error:") and not summ.startswith("Skipped:")}

            if not valid_summaries:
                 if not errors: errors.append("No valid summaries could be generated.")
                 final_summary = f"Error: Could not generate summaries for any file. Reported issues: {'; '.join(errors)}" if errors else "Error: No summaries generated."
                 final_state = "error"
                 # Store intermediate error state
                 store_task_result(task_id, 'summary', final_state, final_summary, errors)
            else:
                sse.publish({"type": "status", "message": f"Combining {len(valid_summaries)} summaries ({summary_level} level)..."}, channel=task_id)
                combined_text = "\n\n".join([f"--- Summary for {name} ---\n{summary}" for name, summary in valid_summaries.items()])
                final_summary = llm_caller.get_combined_summary(combined_text, level=summary_level)

                # Append notes about failed files
                failed_files = [name for name, summ in all_summaries.items() if name not in valid_summaries]
                if failed_files:
                    note = f"\n\nNote: The following files could not be summarized or were skipped: {', '.join(failed_files)}"
                    if isinstance(final_summary, str) and not final_summary.startswith("Error:"):
                        final_summary += note
                    elif isinstance(final_summary, str) and final_summary.startswith("Error:"):
                         final_summary += f" ({note})"
                    # Add failed files info to errors list as well
                    errors.append(f"Note on failures: {note.strip()}")


                if isinstance(final_summary, str) and final_summary.startswith("Error:"):
                     errors.append(f"Final Combination Error: {final_summary}")
                     final_state = "error"
                else:
                     final_state = "completed"

                # Store the final result (or error from combination)
                store_task_result(task_id, 'summary', final_state, final_summary, errors)
        except Exception as e:
             # Catch unexpected errors during the main processing
             error_id = uuid.uuid4()
             app.logger.error(f"Summarizer Task {task_id}: Unhandled exception during processing (Error ID: {error_id}).", exc_info=True)
             error_message = f"A critical background error occurred during summarization (Ref: {error_id})."
             errors.append(error_message)
             final_state = "error"
             # Store the critical error state
             store_task_result(task_id, 'summary', final_state, f"Error: {error_message}", errors)

        finally:
            # --- CORRECTED FINALLY BLOCK ---
            # Attempt to get the most recent result from Redis
            current_result = get_task_result(task_id)

            # Determine the final state and content for logging/SSE, handling potential None result
            if current_result is None:
                # Fallback if Redis retrieval failed
                app.logger.error(f"Summarizer Task {task_id}: Could not retrieve task result from Redis in finally block. Using fallback error state.")
                final_state_for_publish = "error"
                result_for_publish = "Error: Summarization failed and final state could not be retrieved."
                errors_for_publish = ["Could not retrieve final task state from Redis."]
            else:
                # Use the retrieved result
                # Ensure the state is finalized (if it was left as 'unknown' in the try block)
                final_state_for_publish = final_state if final_state != "unknown" else current_result.get('state', 'error')

                # Ensure result and errors exist for logging/SSE, providing defaults
                result_for_publish = current_result.get("result", "Error: Summarization failed unexpectedly.")
                errors_for_publish = current_result.get("errors", [])
                if not errors_for_publish and final_state_for_publish == "error":
                    errors_for_publish.append("An unknown error occurred during summarization.")

                # If the state was adjusted here, maybe update Redis again (optional, depends on need)
                if final_state_for_publish != current_result.get('state'):
                     app.logger.warning(f"Summarizer Task {task_id}: State adjusted in finally block from '{current_result.get('state')}' to '{final_state_for_publish}'.")
                     # You might uncomment the next line if you need to persist this adjusted state back to Redis immediately
                     # store_task_result(task_id, 'summary', final_state_for_publish, result_for_publish, errors_for_publish)


            # Log the final state decided upon
            app.logger.info(f"Summarizer Task {task_id}: FINAL state={final_state_for_publish}, errors={errors_for_publish}, result_preview='{str(result_for_publish)[:100]}...'")
            # Publish the final state via SSE
            sse.publish({"type": final_state_for_publish, "message": f"Summarization {final_state_for_publish}."}, channel=task_id)
            # --- END CORRECTION ---

            # Cleanup temp files
            if temp_dir and os.path.exists(temp_dir):
                 try:
                     shutil.rmtree(temp_dir)
                     app.logger.info(f"Summarizer Task {task_id}: Cleaned up temp directory {temp_dir}")
                 except Exception as cleanup_err:
                     app.logger.error(f"Summarizer Task {task_id}: Error cleaning up temp dir {temp_dir}: {cleanup_err}")


# --- Background Task Function (Story Generator) --- CORRECTED ---
def run_story_generation_async(task_id: str, github_url: str):
    """Fetches commits AND README, then generates a hackathon story."""
    with app.app_context():
        app.logger.info(f"Story Task {task_id}: Background thread started for URL: {github_url}")
        store_task_result(task_id, 'story', 'processing', None, [])
        owner, repo = None, None
        final_state = "unknown"
        error_message = None
        commits = []
        readme_content = None
        combined_context = "" # Initialize combined context

        try:
            # 1. Validate URL and Extract Owner/Repo
            sse.publish({"type": "status", "message": "Validating GitHub URL..."}, channel=task_id)
            try:
                owner, repo = github_utils.parse_github_url(github_url)
            except GitHubUrlError as e:
                error_message = f"Invalid GitHub URL: {e}"
                raise # Re-raise to be caught by the outer try/except

            # --- 2. Fetch README Content ---
            sse.publish({"type": "status", "message": f"Fetching README for {owner}/{repo}..."}, channel=task_id)
            try:
                readme_content = github_utils.get_readme_content(owner, repo)
                if readme_content:
                    sse.publish({"type": "status", "message": "README found."}, channel=task_id)
                else:
                    # This covers both 404 and non-fatal errors in get_readme_content
                    sse.publish({"type": "status", "message": "README not found or unreadable. Proceeding without it."}, channel=task_id)
            except GitHubApiError as e:
                # Log API errors (like rate limits) but allow proceeding if commits can still be fetched
                app.logger.warning(f"Story Task {task_id}: GitHub API error fetching README for {owner}/{repo}: {e}. Attempting to proceed with commits.")
                # Use get_task_result and store_task_result to manage errors across retries if applicable,
                # otherwise append directly if using simple in-memory dict
                current_task_data = get_task_result(task_id) or {'errors': []}
                current_task_data['errors'].append(f"Warning: Could not fetch README due to API error ({e}). Story context may be limited.")
                store_task_result(task_id, 'story', 'processing', current_task_data.get('result'), current_task_data['errors'])

                sse.publish({"type": "status", "message": f"Warning: Error fetching README ({e}). Trying commits only."}, channel=task_id)
                readme_content = None # Ensure it's None
            except Exception as e_readme:
                 # Catch any other unexpected error during README fetch
                 error_id_readme = uuid.uuid4()
                 app.logger.error(f"Story Task {task_id}: Unexpected error fetching README for {owner}/{repo} (Error ID: {error_id_readme}).", exc_info=True)
                 # Use get/store task result for errors
                 current_task_data = get_task_result(task_id) or {'errors': []}
                 current_task_data['errors'].append(f"Warning: Unexpected error fetching README (Ref: {error_id_readme}).")
                 store_task_result(task_id, 'story', 'processing', current_task_data.get('result'), current_task_data['errors'])

                 sse.publish({"type": "status", "message": "Warning: Unexpected error fetching README. Trying commits only."}, channel=task_id)
                 readme_content = None # Ensure it's None
            # --- End Fetch README ---

            # 3. Fetch Commits
            sse.publish({"type": "status", "message": f"Fetching recent commits for {owner}/{repo}..."}, channel=task_id)
            try:
                # FIX IS HERE: Call the function without 'days' or 'limit'
                commits = github_utils.get_recent_commits(owner, repo)
            except RepoNotFoundError as e:
                error_message = str(e) # If repo not found, we can't get commits or README
                raise
            except GitHubApiError as e:
                # If commits fail, we might still have README, but story is likely poor. Treat as failure.
                error_message = f"GitHub API Error fetching commits: {e}"
                raise
            except Exception as e_commits: # Catch other commit errors
                 error_id_commits = uuid.uuid4()
                 app.logger.error(f"Story Task {task_id}: Unexpected error fetching commits for {owner}/{repo} (Error ID: {error_id_commits}).", exc_info=True)
                 error_message = f"Unexpected error fetching commits (Ref: {error_id_commits})."
                 raise # Re-raise as fatal error for commits

            # Check if we have *any* content (commits or README)
            if not commits and not readme_content:
                 error_message = f"No recent commits found and no README available for '{owner}/{repo}'. Cannot generate story."
                 final_state = "error"
                 # Store the specific error message
                 store_task_result(task_id, 'story', "error", f"Could not generate story: {error_message}", [error_message])
                 app.logger.warning(f"Story Task {task_id}: {error_message}")
                 # Proceed to finally without calling LLM

            else:
                # 4. Format Context (README + Commits)
                sse.publish({"type": "status", "message": "Formatting context for AI storyteller..."}, channel=task_id)
                context_parts = []

                if readme_content:
                    # Limit README size to avoid excessive context length (e.g., first 10000 chars)
                    readme_limit = 10000
                    truncated_readme = readme_content[:readme_limit]
                    if len(readme_content) > readme_limit:
                        truncated_readme += "\n... (README truncated)"
                        app.logger.info(f"Story Task {task_id}: Truncated README for context (limit {readme_limit} chars).")

                    context_parts.append("--- README CONTENT START ---")
                    context_parts.append(truncated_readme) # Use potentially truncated content
                    context_parts.append("--- README CONTENT END ---")

                if commits:
                    formatted_commits_list = []
                    for i, c in enumerate(commits):
                        try:
                            # Attempt to parse ISO date string, handle potential errors
                            dt_obj = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
                            formatted_date = dt_obj.strftime('%Y-%m-%d %H:%M UTC')
                        except (ValueError, TypeError, KeyError):
                            formatted_date = c.get('date', 'Unknown Date') # Fallback
                        message_preview = c.get('message', '')[:100] + ('...' if len(c.get('message', '')) > 100 else '')
                        formatted_commits_list.append(
                            f"{i+1}. Author: {c.get('author', 'N/A')}, Date: {formatted_date}, Message: {message_preview}"
                        )
                    formatted_commits_str = "\n".join(formatted_commits_list)

                    context_parts.append("\n--- COMMIT HISTORY START ---") # Add newline for separation
                    context_parts.append(formatted_commits_str)
                    context_parts.append("--- COMMIT HISTORY END ---")
                    sse.publish({"type": "status", "message": f"Found {len(commits)} recent commits."}, channel=task_id)
                elif not readme_content: # Should not happen due to earlier check, but safeguard
                     app.logger.error(f"Story Task {task_id}: Logic error - No commits and no readme, but proceeded.")
                     raise ValueError("Internal error: No content to generate story from.")


                combined_context = "\n\n".join(context_parts) # Join sections with double newline

                # 5. Call LLM for Story
                sse.publish({"type": "status", "message": "Asking the AI storyteller..."}, channel=task_id)
                # Pass the combined context string
                story_result = llm_caller.get_hackathon_story(repo, combined_context)

                if isinstance(story_result, str) and story_result.startswith("Error:"):
                    error_message = f"Story Generation Failed: {story_result}"
                    raise ValueError(error_message) # Treat LLM error as exception

                # 6. Success
                # Get existing errors before overwriting
                current_task_data = get_task_result(task_id) or {'errors': []}
                store_task_result(task_id, 'story', "completed", story_result, current_task_data.get('errors', [])) # Preserve existing warnings
                final_state = "completed"
                sse.publish({"type": "status", "message": "Story generation complete!"}, channel=task_id)

        except (GitHubUrlError, RepoNotFoundError, GitHubApiError, ValueError, Exception) as e:
            error_id = uuid.uuid4()
            if not error_message: # Ensure a generic message if specific one wasn't set
                 error_message = f"A critical background error occurred (Ref: {error_id}). Reason: {type(e).__name__}"
            # Check if it's a known GitHub error type before logging the full trace for those
            if isinstance(e, (GitHubUrlError, RepoNotFoundError, GitHubApiError, ValueError)):
                 app.logger.error(f"Story Task {task_id}: Background task failed. Error: {error_message} - {e}")
            else: # Log full trace for unexpected errors
                 app.logger.error(f"Story Task {task_id}: Background task failed unexpectedly. Error: {e} (Error ID: {error_id}).", exc_info=True)
                 error_message = f"An unexpected background error occurred (Ref: {error_id})." # Overwrite with generic for unexpected

            # Store error state - get existing errors first
            current_task_data = get_task_result(task_id) or {'errors': []}
            current_task_data['errors'].append(error_message) # Append the new error
            store_task_result(task_id, 'story', "error", f"Could not generate story: {error_message}", current_task_data['errors'])
            final_state = "error"

        finally:
            # Attempt to get the most recent result from Redis
            current_result = get_task_result(task_id)

            # Determine the final state and content for logging/SSE, handling potential None result
            if current_result is None:
                # Fallback if Redis retrieval failed
                app.logger.error(f"Story Task {task_id}: Could not retrieve task result from Redis in finally block. Using fallback error state.")
                final_state_for_publish = "error"
                result_for_publish = "Error: Story generation failed and final state could not be retrieved."
                errors_for_publish = ["Could not retrieve final task state from Redis."]
            else:
                # Use the retrieved result
                # Ensure the state is finalized (if it was left as 'unknown' in the try block)
                final_state_for_publish = final_state if final_state != "unknown" else current_result.get('state', 'error')

                # Ensure result and errors exist for logging/SSE, providing defaults
                result_for_publish = current_result.get("result", "Error: Story generation failed unexpectedly.")
                errors_for_publish = current_result.get("errors", [])
                if not errors_for_publish and final_state_for_publish == "error":
                    errors_for_publish.append("An unknown error occurred during story generation.")

                # If the state was updated here, maybe update Redis again (optional)
                if final_state_for_publish != current_result.get('state'):
                     app.logger.warning(f"Story Task {task_id}: State adjusted in finally block from '{current_result.get('state')}' to '{final_state_for_publish}'.")
                     # store_task_result(task_id, 'story', final_state_for_publish, result_for_publish, errors_for_publish)

            # Log the final state decided upon
            app.logger.info(f"Story Task {task_id}: FINAL state={final_state_for_publish}, errors={errors_for_publish}, result_preview='{str(result_for_publish)[:100]}...'")
            # Publish the final state via SSE
            sse.publish({"type": final_state_for_publish, "message": f"Story generation {final_state_for_publish}."}, channel=task_id)


# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    app.logger.info(f"Index route accessed. Session: {dict(session)}")

    summary_task_id = session.get('current_summary_task_id')
    story_task_id = session.get('current_story_task_id')
    results = None
    task_id_to_clear_session_key = None
    is_processing_summary = False
    is_processing_story = False
    active_task_id_for_template = None # Store the ID of the task currently processing

    # --- RESULT CHECKING LOGIC ---
    task_to_check = None
    task_type = None
    task_state = None

    if summary_task_id:
        task_to_check = summary_task_id
        task_type = 'summary'
    elif story_task_id:
        task_to_check = story_task_id
        task_type = 'story'

    if task_to_check:
        # Try to get the task from Redis
        task_entry = get_task_result(task_to_check)

        if task_entry:
            # Task found in Redis
            task_state = task_entry.get('state')
            app.logger.info(f"Task {task_to_check} (Type: {task_type}). Found in Redis with state: {task_state}")

            if task_state == 'completed' or task_state == 'error':
                # Task is finished, get results and clear Redis entry and session key
                results = task_entry
                delete_task_result(task_to_check) # Remove from Redis
                task_id_to_clear_session_key = f'current_{task_type}_task_id' # Mark session key for clearing
                app.logger.info(f"{task_type.capitalize()} Task {task_to_check}: Results retrieved (state={task_state}), cleared from Redis.")
            elif task_state == 'processing':
                # Task is still running
                app.logger.info(f"{task_type.capitalize()} Task {task_to_check}: Still processing.")
                if task_type == 'summary':
                    is_processing_summary = True
                else: # task_type == 'story'
                    is_processing_story = True
                active_task_id_for_template = task_to_check
            else:
                # Unknown state, treat as error
                app.logger.warning(f"Task {task_to_check} found with unexpected state '{task_state}'. Treating as error.")
                results = {'state': 'error', 'errors': [f"Task ended in unexpected state: {task_state}"], 'type': task_type, 'result': None}
                delete_task_result(task_to_check) # Remove from Redis
                task_id_to_clear_session_key = f'current_{task_type}_task_id' # Mark session key for clearing
        else:
            # Task not in Redis but ID still in session? Maybe it just started or expired.
            app.logger.warning(f"Task {task_to_check} (Type: {task_type}) ID found in session but not in Redis. Assuming it's expired or failed to start/store. Clearing session key.")
            # Treat as if it's not processing anymore, clear the session key
            task_id_to_clear_session_key = f'current_{task_type}_task_id'
            # Ensure flags are false
            if task_type == 'summary': is_processing_summary = False
            if task_type == 'story': is_processing_story = False
            active_task_id_for_template = None


    # Clear session variables if marked for clearing
    if task_id_to_clear_session_key:
        session.pop(task_id_to_clear_session_key, None)
        app.logger.info(f"Cleared session key: {task_id_to_clear_session_key}")

    # Clear download caches if NOT processing that specific task type
    if not is_processing_summary:
         session.pop('download_summary_raw', None)
    if not is_processing_story:
         session.pop('story_result_raw', None) # Changed key to be consistent
    # --- END RESULT CHECKING LOGIC ---


    # Prepare results for template based on retrieved 'results'
    summary_html, summary_raw = None, None
    story_html, story_raw = None, None

    if results: # Only process if results were actually retrieved
        errors = results.get("errors")
        if errors:
            for error in errors: flash(error, 'error')

        result_content = results.get("result")
        result_type = results.get('type') # Get type from retrieved results

        if result_type == 'summary':
            if isinstance(result_content, str) and result_content.startswith("Error:"):
                # Flash the error if it's an error string, even if other errors were flashed
                if result_content not in (errors or []): # Avoid duplicate flash
                    flash(f"Summarization failed: {result_content}", 'error')
                summary_raw = None # Don't display error as raw content
            elif result_content:
                summary_raw = result_content
                try:
                     summary_html = markdown.markdown(summary_raw, extensions=['fenced_code', 'sane_lists'])
                     session['download_summary_raw'] = summary_raw # Store for download
                except Exception as md_err:
                     app.logger.error(f"Markdown rendering failed for summary: {md_err}")
                     flash("Failed to render summary preview.", 'error')
                     summary_html = f"<p><em>(Failed to render Markdown preview)</em></p><pre>{summary_raw}</pre>" # Show raw in preview on render error
                     session.pop('download_summary_raw', None) # Clear download cache
            else: # result_content is None or empty
                 summary_raw = None
                 if results.get('state') == 'completed': # If completed but no content
                     flash("Summarization completed, but the result was empty.", 'warning')

        elif result_type == 'story':
            if isinstance(result_content, str) and result_content.startswith("Error:"):
                if result_content not in (errors or []):
                     flash(f"Story generation failed: {result_content}", 'error')
                story_raw = None
            elif result_content:
                story_raw = result_content
                try:
                     story_html = markdown.markdown(story_raw, extensions=['fenced_code', 'sane_lists'])
                     session['story_result_raw'] = story_raw # Store for potential copy/future download
                except Exception as md_err:
                     app.logger.error(f"Markdown rendering failed for story: {md_err}")
                     flash("Failed to render story preview.", 'error')
                     story_html = f"<p><em>(Failed to render Markdown preview)</em></p><pre>{story_raw}</pre>"
                     session.pop('story_result_raw', None)
            else: # result_content is None or empty
                 story_raw = None
                 if results.get('state') == 'completed':
                     flash("Story generation completed, but the result was empty.", 'warning')

    app.logger.info(f"Rendering index. Processing Summary: {is_processing_summary}, Processing Story: {is_processing_story}")
    app.logger.info(f"Summary Result Available: {summary_raw is not None}, Story Result Available: {story_raw is not None}")

    # Ensure the active task ID is passed correctly to the template only if processing
    template_summary_task_id = active_task_id_for_template if is_processing_summary else None
    template_story_task_id = active_task_id_for_template if is_processing_story else None

    return render_template('index.html',
                           config=app.config,
                           summary_html=summary_html,
                           summary_raw=summary_raw,
                           story_html=story_html,
                           story_raw=story_raw,
                           is_processing_summary=is_processing_summary,
                           is_processing_story=is_processing_story,
                           summary_task_id=template_summary_task_id, # Pass correct active ID
                           story_task_id=template_story_task_id      # Pass correct active ID
                           )

@app.route('/process', methods=['POST'])
def process_files():
    # Clear potentially active tasks and results from previous runs
    session.pop('current_story_task_id', None)
    session.pop('current_summary_task_id', None)
    session.pop('download_summary_raw', None)
    session.pop('story_result_raw', None)
    # Note: We don't clear Redis here, let expiration handle old tasks or overwrite on new task start

    if 'files' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('index'))
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        flash('No files selected.', 'error')
        return redirect(url_for('index'))
    allowed_levels = ['short', 'medium', 'comprehensive']
    summary_level = request.form.get('summary_level', 'medium')
    if summary_level not in allowed_levels:
        flash(f"Invalid summary level specified, using default 'Medium'.", 'warning')
        summary_level = 'medium'

    temp_dir_base = None # Initialize variable
    processing_errors = []
    try:
        # Create a unique temp directory for this request
        temp_dir_base = tempfile.mkdtemp(prefix='summarizer_')
        app.logger.info(f"Created temp dir base for summary request: {temp_dir_base}")

        # Validate and save files
        saved_details, validation_errors = file_handler.save_uploaded_files(uploaded_files, temp_dir_base)
        processing_errors.extend(validation_errors) # Add validation errors to be flashed later

        # Filter for files that were successfully saved (have a temp_path and no error)
        successfully_saved_files = [d for d in saved_details if d.get('temp_path') and not d.get('error')]

        if not successfully_saved_files:
             # If no files could be saved/validated, report errors and redirect
             if not processing_errors: processing_errors.append("No valid files could be processed for summary.")
             for error in processing_errors: flash(error, 'error')
             app.logger.warning(f"Summary file validation/saving failed: {processing_errors}")
             # Cleanup the created temp dir if it exists
             if temp_dir_base and os.path.exists(temp_dir_base):
                 try: shutil.rmtree(temp_dir_base)
                 except Exception as cleanup_err: app.logger.error(f"Error cleaning temp dir {temp_dir_base} after validation failure: {cleanup_err}")
             return redirect(url_for('index'))

        # Generate task ID and prepare details for the background thread
        task_id = str(uuid.uuid4())
        original_filenames = [d['original_name'] for d in successfully_saved_files]
        # Pass only necessary info to the thread
        thread_file_details = [{'original_name': d['original_name'], 'temp_path': d['temp_path'], 'size': d['size']} for d in successfully_saved_files]

        # Start the background thread
        thread = threading.Thread(target=run_summarizer_async, args=(
            task_id, thread_file_details, summary_level, original_filenames
        ))
        thread.daemon = True # Allows app to exit even if thread is running
        thread.start()
        app.logger.info(f"Summarizer Task {task_id}: Background thread started.")

        # Store the task ID in the session to track progress
        session['current_summary_task_id'] = task_id

        # Flash any non-fatal validation errors (e.g., skipped files)
        for error in validation_errors: flash(error, 'warning') # Flash as warning if some files succeeded
        return redirect(url_for('index')) # Redirect to index to show progress

    except Exception as e:
        # Catch unexpected errors during setup (e.g., creating temp dir)
        error_id = uuid.uuid4()
        app.logger.error(f"Unhandled exception during summary request setup (Error ID: {error_id}).", exc_info=True)
        flash(f"A critical setup error occurred (Ref: {error_id}).", 'error')
        # Cleanup temp dir if created before the error
        if temp_dir_base and os.path.exists(temp_dir_base):
            try: shutil.rmtree(temp_dir_base)
            except Exception as cleanup_err: app.logger.error(f"Error cleaning temp dir {temp_dir_base} after setup error: {cleanup_err}")
        return redirect(url_for('index'))


@app.route('/generate_story', methods=['POST'])
def generate_story():
    # Clear potentially active tasks and results
    session.pop('current_summary_task_id', None)
    session.pop('download_summary_raw', None)
    session.pop('current_story_task_id', None)
    session.pop('story_result_raw', None)

    github_url = request.form.get('github_url')
    if not github_url or not github_url.strip():
        flash('GitHub repository URL is required.', 'error')
        return redirect(url_for('index'))

    github_url = github_url.strip() # Remove leading/trailing whitespace

    # Basic validation *before* starting the potentially long background task
    try:
        owner, repo = github_utils.parse_github_url(github_url)
    except GitHubUrlError as e:
         flash(f'Invalid GitHub URL: {e}', 'error')
         return redirect(url_for('index'))
    except Exception as e: # Catch any other parsing error
        flash(f'Error validating URL: {e}', 'error')
        return redirect(url_for('index'))

    try:
        # Generate task ID
        task_id = str(uuid.uuid4())

        # Start the background thread
        thread = threading.Thread(target=run_story_generation_async, args=(task_id, github_url))
        thread.daemon = True
        thread.start()
        app.logger.info(f"Story Task {task_id}: Background thread started for URL: {github_url}")

        # Store task ID in session
        session['current_story_task_id'] = task_id

        return redirect(url_for('index')) # Redirect to show progress

    except Exception as e:
        # Catch unexpected errors during thread setup/start
        error_id = uuid.uuid4()
        app.logger.error(f"Unhandled exception during story request setup (Error ID: {error_id}).", exc_info=True)
        flash(f"A critical setup error occurred while starting story generation (Ref: {error_id}).", 'error')
        return redirect(url_for('index'))


@app.route('/download_summary')
def download_summary():
    # Retrieve raw summary text stored in the session after successful completion
    summary_content = session.get('download_summary_raw')

    if summary_content is None:
        flash('No valid summary available for download or session expired.', 'error')
        return redirect(url_for('index'))
    # Basic check if the stored content itself is an error message
    if isinstance(summary_content, str) and summary_content.startswith("Error:"):
         flash('Cannot download: The previous summarization resulted in an error.', 'error')
         return redirect(url_for('index'))


    from io import BytesIO
    mem_file = BytesIO()
    try:
        # Encode the summary content to UTF-8 bytes
        mem_file.write(summary_content.encode('utf-8'))
        mem_file.seek(0) # Rewind the file pointer to the beginning
    except Exception as e:
        app.logger.error(f"Error encoding summary for download: {e}", exc_info=True)
        flash('Failed to prepare summary for download.', 'error')
        return redirect(url_for('index'))

    app.logger.info("Providing summary file for download.")
    # Send the in-memory file as an attachment
    return send_file(
        mem_file,
        as_attachment=True,
        download_name='summary.txt', # Filename for the user
        mimetype='text/plain; charset=utf-8'
    )

if __name__ == '__main__':
    # Ensure the session directory exists before starting
    session_dir = app.config["SESSION_FILE_DIR"]
    if not os.path.exists(session_dir):
        try:
            os.makedirs(session_dir)
            app.logger.info(f"Created session directory: {session_dir}")
        except OSError as e:
            app.logger.error(f"Could not create session directory {session_dir}: {e}")
            # Depending on severity, you might want to exit here
            # exit(1)

    # Use host='0.0.0.0' to make it accessible on the network
    # debug=True enables auto-reloading and provides debug info (DISABLE in production)
    # threaded=True handles multiple requests concurrently (though gevent is used with gunicorn)
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
    # Note: When running with Gunicorn (as specified in Procfile/render.yaml),
    # Gunicorn manages the workers and concurrency, `app.run` is not used.
    # The debug=False and threaded=True here are mostly for local testing without Gunicorn.
