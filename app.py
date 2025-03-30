# app.py
# --- Imports ---
import os
import uuid
import tempfile
import shutil
import logging
import threading
import markdown
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify, send_file
# >>> Import Flask-Session and redis <<<
from flask_session import Session # Ensure this is imported
import redis # <<< ADD THIS IMPORT
# >>> END MODIFICATION <<<
from flask_sse import sse
from dotenv import load_dotenv
# Import utilities
from pocketflow_logic.utils import file_handler, llm_caller # Ensure llm_caller is imported
# --- ADD Import for GitHub utils and exceptions ---
from pocketflow_logic.utils import github_utils
from pocketflow_logic.utils.github_utils import GitHubUrlError, RepoNotFoundError, GitHubApiError
# -------------------------------------------------

# --- Configuration ---
load_dotenv() # Load .env file for local development (Render uses env vars directly)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
app.logger.setLevel(logging.INFO)

# --- Flask-Session Configuration (MODIFIED FOR REDIS ON RENDER) ---
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-replace-me!") # Keep using env var

# CRITICAL: Configure session to use Redis
# Render automatically provides the REDIS_URL environment variable for its managed Redis instances
redis_url = os.getenv("REDIS_URL")
if not redis_url:
    app.logger.warning("REDIS_URL environment variable not set. Session storage may fail.")
    # Fallback to filesystem for local dev IF NEEDED, but strongly discouraged for Render
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = "./flask_session" # Ensure this directory exists or is created
    app.logger.warning("Falling back to filesystem sessions. THIS WILL NOT WORK RELIABLY ON RENDER.")
else:
    app.logger.info(f"Configuring Flask-Session to use Redis at inferred URL (from REDIS_URL env var)")
    app.config["SESSION_TYPE"] = "redis"
    # Flask-Session expects a redis.Redis client instance
    # Create the client using the URL provided by Render
    try:
        # Add ssl_cert_reqs=None if using Redis 6+ with TLS without custom certs (Render often handles this)
        # Set decode_responses=True if you store complex structures directly, usually False is fine as Flask-Session pickles.
        app.config["SESSION_REDIS"] = redis.from_url(redis_url, ssl_cert_reqs=None, decode_responses=False) # Added ssl_cert_reqs=None
        app.logger.info("Redis client for Flask-Session configured successfully.")
    except Exception as e:
        app.logger.error(f"Failed to create Redis client from REDIS_URL: {e}", exc_info=True)
        app.logger.error("Sessions will likely fail. Check REDIS_URL and Redis service status.")
        # Optionally fallback or raise an error
        app.config["SESSION_TYPE"] = "filesystem" # Fallback as last resort, but log error prominently
        app.config["SESSION_FILE_DIR"] = "./flask_session"
        app.logger.critical("CRITICAL: Fell back to filesystem sessions due to Redis connection error. DEPLOYMENT WILL BE UNRELIABLE.")

# These filesystem settings are now only used if REDIS_URL is missing (fallback case)
# app.config["SESSION_FILE_DIR"] = "./flask_session" # Keep for fallback case if dir needs creation
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True # Recommended for security

# Initialize Flask-Session AFTER configuration
# If Session(app) was called earlier, ensure it's called here.
Session(app)

# --- Flask-SSE Configuration ---
# Use the detected redis_url if available, otherwise use default for local dev
app.config["REDIS_URL"] = redis_url if redis_url else os.getenv("REDIS_URL_FALLBACK", "redis://localhost:6379/0") # Use detected URL or fallback/local default
app.register_blueprint(sse, url_prefix='/stream')

# --- Simple In-Memory Task Storage (HACKATHON ONLY - Results lost on deploy/restart) ---
# Structure: { task_id: {'type': 'summary'/'story', 'result': ..., 'errors': [], 'state': 'processing'/'completed'/'error'} }
task_results = {}

# --- Security check for default SECRET_KEY ---
# This check remains important for production environments like Render
if not app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
    app.logger.critical("SECURITY ALERT: Running in non-debug mode with default SECRET_KEY!")
    # Consider raising RuntimeError only if not running on a platform that injects keys,
    # but it's safer to require it explicitly.
    raise RuntimeError("FLASK_SECRET_KEY must be set to a strong, unique value in production (non-debug) mode via environment variables.")
elif app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
     app.logger.warning("SECURITY WARNING: Using default SECRET_KEY in debug mode. Set FLASK_SECRET_KEY environment variable for production.")

# --- Pass file limits to template context ---
app.config['MAX_FILES'] = file_handler.MAX_FILES
app.config['MAX_FILE_SIZE_MB'] = file_handler.MAX_FILE_SIZE_MB

# --- Background Task Function (Summarizer) ---
# (run_summarizer_async remains unchanged - uWSGI with enable-threads handles it)
def run_summarizer_async(task_id, temp_file_details, summary_level, original_filenames):
    """Runs the file summarization in a background thread."""
    with app.app_context():
        app.logger.info(f"Summarizer Task {task_id}: Background thread started.")
        task_results[task_id] = {'type': 'summary', 'state': 'processing', 'errors': []}
        final_state = "unknown"
        all_summaries = {}
        errors = []
        temp_dir = None # Initialize temp_dir

        try:
            sse.publish({"type": "status", "message": "Initializing summarization..."}, channel=task_id)

            total_files = len(temp_file_details)
            if total_files > 0:
                 temp_dir = os.path.dirname(temp_file_details[0]['temp_path'])

            for i, file_detail in enumerate(temp_file_details):
                original_name = file_detail['original_name']
                temp_path = file_detail['temp_path']
                sse.publish({"type": "status", "message": f"Processing file {i+1}/{total_files}: '{original_name}'..."}, channel=task_id)

                content = file_handler.read_file_content(temp_path)
                if content is None:
                    errors.append(f"Could not read file: {original_name}")
                    all_summaries[original_name] = "Error: Could not read file content"
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
                    errors.append(f"LLM Error for '{original_name}': {summary}")
                    sse.publish({"type": "status", "message": f"LLM Error for '{original_name}'."}, channel=task_id)
                else:
                    sse.publish({"type": "status", "message": f"Received summary for '{original_name}'."}, channel=task_id)

            valid_summaries = {name: summ for name, summ in all_summaries.items() if isinstance(summ, str) and not summ.startswith("Error:") and not summ.startswith("Skipped:")}

            if not valid_summaries:
                 if not errors: errors.append("No valid summaries could be generated.")
                 final_summary = f"Error: Could not generate summaries for any file. Reported issues: {'; '.join(errors)}" if errors else "Error: No summaries generated."
                 final_state = "error"
            else:
                sse.publish({"type": "status", "message": f"Combining {len(valid_summaries)} summaries ({summary_level} level)..."}, channel=task_id)
                combined_text = "\n\n".join([f"--- Summary for {name} ---\n{summary}" for name, summary in valid_summaries.items()])
                final_summary = llm_caller.get_combined_summary(combined_text, level=summary_level)

                failed_files = [name for name, summ in all_summaries.items() if name not in valid_summaries]
                if failed_files:
                    note = f"\n\nNote: The following files could not be summarized or were skipped: {', '.join(failed_files)}"
                    if isinstance(final_summary, str) and not final_summary.startswith("Error:"):
                        final_summary += note
                    elif isinstance(final_summary, str) and final_summary.startswith("Error:"):
                         final_summary += f" ({note})"

                if isinstance(final_summary, str) and final_summary.startswith("Error:"):
                     errors.append(f"Final Combination Error: {final_summary}")
                     final_state = "error"
                else:
                     final_state = "completed"

            task_results.setdefault(task_id, {})["result"] = final_summary
            if errors:
                 task_results.setdefault(task_id, {}).setdefault("errors", []).extend(errors)
                 if final_state != "error": final_state = "error"

        except Exception as e:
            error_id = uuid.uuid4()
            app.logger.error(f"Summarizer Task {task_id}: Unhandled exception (Error ID: {error_id}).", exc_info=True)
            task_results.setdefault(task_id, {}).setdefault("errors", []).append(f"A critical background error occurred (Ref: {error_id}).")
            task_results.setdefault(task_id, {})["result"] = f"Processing failed due to a background error (Ref: {error_id})."
            final_state = "error"
        finally:
            results_entry = task_results.setdefault(task_id, {})
            results_entry["state"] = final_state if final_state != "unknown" else "error"
            results_entry.setdefault("result", "Error: Summarization failed unexpectedly.")
            results_entry.setdefault("errors", [])
            if not results_entry["errors"] and results_entry["state"] == "error":
                 results_entry["errors"].append("An unknown error occurred during summarization.")

            app.logger.info(f"Summarizer Task {task_id}: FINAL state={results_entry['state']}, errors={results_entry['errors']}, result_preview='{str(results_entry.get('result'))[:100]}...'")
            sse.publish({"type": results_entry['state'], "message": f"Summarization {results_entry['state']}."}, channel=task_id)

            # Cleanup temp files
            if temp_dir and os.path.exists(temp_dir):
                 try:
                     shutil.rmtree(temp_dir)
                     app.logger.info(f"Summarizer Task {task_id}: Cleaned up temp directory {temp_dir}")
                 except Exception as cleanup_err:
                     app.logger.error(f"Summarizer Task {task_id}: Error cleaning up temp dir {temp_dir}: {cleanup_err}")


# --- Background Task Function (Story Generator) --- UPDATED ---
# (run_story_generation_async remains unchanged - uWSGI with enable-threads handles it)
def run_story_generation_async(task_id: str, github_url: str):
    """Fetches commits AND README, then generates a hackathon story."""
    with app.app_context():
        app.logger.info(f"Story Task {task_id}: Background thread started for URL: {github_url}")
        task_results[task_id] = {'type': 'story', 'state': 'processing', 'errors': []}
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
                    sse.publish({"type": "status", "message": "README not found or unreadable. Proceeding without it."}, channel=task_id)
            except GitHubApiError as e:
                app.logger.warning(f"Story Task {task_id}: GitHub API error fetching README for {owner}/{repo}: {e}. Attempting to proceed with commits.")
                task_results[task_id].setdefault("errors", []).append(f"Warning: Could not fetch README due to API error ({e}). Story context may be limited.")
                sse.publish({"type": "status", "message": f"Warning: Error fetching README ({e}). Trying commits only."}, channel=task_id)
                readme_content = None # Ensure it's None
            except Exception as e_readme:
                 error_id_readme = uuid.uuid4()
                 app.logger.error(f"Story Task {task_id}: Unexpected error fetching README for {owner}/{repo} (Error ID: {error_id_readme}).", exc_info=True)
                 task_results[task_id].setdefault("errors", []).append(f"Warning: Unexpected error fetching README (Ref: {error_id_readme}).")
                 sse.publish({"type": "status", "message": "Warning: Unexpected error fetching README. Trying commits only."}, channel=task_id)
                 readme_content = None # Ensure it's None

            # 3. Fetch Commits
            sse.publish({"type": "status", "message": f"Fetching recent commits for {owner}/{repo}..."}, channel=task_id)
            try:
                commits = github_utils.get_recent_commits(owner, repo, days=3, limit=30)
            except RepoNotFoundError as e:
                error_message = str(e)
                raise
            except GitHubApiError as e:
                error_message = f"GitHub API Error fetching commits: {e}"
                raise

            # Check if we have *any* content (commits or README)
            if not commits and not readme_content:
                 error_message = f"No recent commits found and no README available for '{owner}/{repo}'. Cannot generate story."
                 final_state = "error"
                 task_results.setdefault(task_id, {}).setdefault("errors", []).append(error_message)
                 task_results.setdefault(task_id, {})["result"] = f"Could not generate story: {error_message}"
                 app.logger.warning(f"Story Task {task_id}: {error_message}")

            else:
                # 4. Format Context (README + Commits)
                sse.publish({"type": "status", "message": "Formatting context for AI storyteller..."}, channel=task_id)
                context_parts = []

                if readme_content:
                    readme_limit = 10000
                    truncated_readme = readme_content[:readme_limit]
                    if len(readme_content) > readme_limit:
                        truncated_readme += "\n... (README truncated)"
                        app.logger.info(f"Story Task {task_id}: Truncated README for context (limit {readme_limit} chars).")

                    context_parts.append("--- README CONTENT START ---")
                    context_parts.append(truncated_readme)
                    context_parts.append("--- README CONTENT END ---")

                if commits:
                    formatted_commits_list = []
                    for i, c in enumerate(commits):
                        try:
                            dt_obj = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
                            formatted_date = dt_obj.strftime('%Y-%m-%d %H:%M UTC')
                        except (ValueError, TypeError, KeyError):
                            formatted_date = c.get('date', 'Unknown Date') # Fallback
                        message_preview = c.get('message', '')[:100] + ('...' if len(c.get('message', '')) > 100 else '')
                        formatted_commits_list.append(
                            f"{i+1}. Author: {c.get('author', 'N/A')}, Date: {formatted_date}, Message: {message_preview}"
                        )
                    formatted_commits_str = "\n".join(formatted_commits_list)

                    context_parts.append("\n--- COMMIT HISTORY START ---")
                    context_parts.append(formatted_commits_str)
                    context_parts.append("--- COMMIT HISTORY END ---")
                    sse.publish({"type": "status", "message": f"Found {len(commits)} recent commits."}, channel=task_id)
                elif not readme_content:
                     app.logger.error(f"Story Task {task_id}: Logic error - No commits and no readme, but proceeded.")
                     raise ValueError("Internal error: No content to generate story from.")

                combined_context = "\n\n".join(context_parts)

                # 5. Call LLM for Story
                sse.publish({"type": "status", "message": "Asking the AI storyteller..."}, channel=task_id)
                story_result = llm_caller.get_hackathon_story(repo, combined_context)

                if isinstance(story_result, str) and story_result.startswith("Error:"):
                    error_message = f"Story Generation Failed: {story_result}"
                    raise ValueError(error_message)

                # 6. Success
                task_results.setdefault(task_id, {})["result"] = story_result
                final_state = "completed"
                sse.publish({"type": "status", "message": "Story generation complete!"}, channel=task_id)

        except (GitHubUrlError, RepoNotFoundError, GitHubApiError, ValueError, Exception) as e:
            error_id = uuid.uuid4()
            if not error_message:
                 error_message = f"A critical background error occurred (Ref: {error_id})."
            if isinstance(e, (GitHubUrlError, RepoNotFoundError, GitHubApiError)):
                 app.logger.error(f"Story Task {task_id}: Background task failed. Error: {error_message}")
            else:
                 app.logger.error(f"Story Task {task_id}: Background task failed. Error: {e} (Error ID: {error_id}).", exc_info=True)

            task_results.setdefault(task_id, {}).setdefault("errors", []).append(error_message)
            task_results.setdefault(task_id, {})["result"] = f"Could not generate story: {error_message}"
            final_state = "error"

        finally:
            results_entry = task_results.setdefault(task_id, {})
            results_entry["state"] = final_state if final_state != "unknown" else "error"
            results_entry.setdefault("result", "Error: Story generation failed unexpectedly.")
            results_entry.setdefault("errors", [])
            if not results_entry["errors"] and results_entry["state"] == "error":
                 results_entry["errors"].append("An unknown error occurred during story generation.")

            app.logger.info(f"Story Task {task_id}: FINAL state={results_entry['state']}, errors={results_entry['errors']}, result_preview='{str(results_entry.get('result'))[:100]}...'")
            sse.publish({"type": results_entry['state'], "message": f"Story generation {results_entry['state']}."}, channel=task_id)


# --- Flask Routes ---
# (index, process_files, generate_story, download_summary routes remain unchanged)
@app.route('/', methods=['GET'])
def index():
    app.logger.info(f"Index route accessed. Session: {dict(session)}, Task Results Keys: {list(task_results.keys())}")

    summary_task_id = session.get('current_summary_task_id')
    story_task_id = session.get('current_story_task_id')
    results = None
    task_id_to_clear = None
    is_processing_summary = False
    is_processing_story = False
    active_task_id_for_template = None

    task_to_check = None
    task_type = None

    if summary_task_id:
        task_to_check = summary_task_id
        task_type = 'summary'
    elif story_task_id:
        task_to_check = story_task_id
        task_type = 'story'

    if task_to_check and task_to_check in task_results:
        task_entry = task_results.get(task_to_check)
        task_state = task_entry.get('state')
        app.logger.info(f"Checking Task {task_to_check} (Type: {task_type}). Found in task_results with state: {task_state}")

        if task_state in ['completed', 'error']:
            results = task_results.pop(task_to_check) # Pop result when done
            task_id_to_clear = f'current_{task_type}_task_id'
            app.logger.info(f"{task_type.capitalize()} Task {task_to_check}: Results retrieved (state={task_state}) and cleared.")
        elif task_state == 'processing':
            app.logger.info(f"{task_type.capitalize()} Task {task_to_check}: Still processing.")
            if task_type == 'summary':
                is_processing_summary = True
            else: # task_type == 'story'
                is_processing_story = True
            active_task_id_for_template = task_to_check
        else:
             app.logger.warning(f"Task {task_to_check} found with unexpected state '{task_state}'. Treating as error and popping.")
             results = task_results.pop(task_to_check, {'state': 'error', 'errors': [f"Task ended in unexpected state: {task_state}"], 'type': task_type}) # Pop safely
             results['state'] = 'error'
             task_id_to_clear = f'current_{task_type}_task_id'

    elif task_to_check:
         app.logger.warning(f"Task {task_to_check} (Type: {task_type}) found in session but not in task_results. Clearing session.")
         task_id_to_clear = f'current_{task_type}_task_id'

    if task_id_to_clear:
        session.pop(task_id_to_clear, None)

    # Clear download caches if NOT processing that specific task type
    if not is_processing_summary:
         session.pop('download_summary_raw', None)
    if not is_processing_story:
         session.pop('story_result_raw', None)

    summary_html, summary_raw = None, None
    story_html, story_raw = None, None

    if results:
        errors = results.get("errors")
        if errors:
            for error in errors: flash(error, 'error')

        result_content = results.get("result")
        result_type = results.get('type')

        if result_type == 'summary':
            if isinstance(result_content, str) and result_content.startswith("Error:"):
                flash(f"Summarization failed: {result_content}", 'error')
                summary_raw = None
            elif result_content:
                summary_raw = result_content
                try:
                     summary_html = markdown.markdown(summary_raw, extensions=['fenced_code', 'sane_lists'])
                     session['download_summary_raw'] = summary_raw # Store raw text for download
                except Exception as md_err:
                     app.logger.error(f"Markdown rendering failed for summary: {md_err}")
                     flash("Failed to render summary preview.", 'error')
                     summary_html = None
                     session.pop('download_summary_raw', None)
            else:
                 summary_raw = None

        elif result_type == 'story':
            if isinstance(result_content, str) and result_content.startswith("Error:"):
                 flash(f"Story generation failed: {result_content}", 'error')
                 story_raw = None
            elif result_content:
                story_raw = result_content
                try:
                     story_html = markdown.markdown(story_raw, extensions=['fenced_code', 'sane_lists'])
                     session['story_result_raw'] = story_raw # Store raw story for potential copy/download
                except Exception as md_err:
                     app.logger.error(f"Markdown rendering failed for story: {md_err}")
                     flash("Failed to render story preview.", 'error')
                     story_html = None
                     session.pop('story_result_raw', None)
            else:
                 story_raw = None

    app.logger.info(f"Rendering index. Processing Summary: {is_processing_summary}, Processing Story: {is_processing_story}")
    app.logger.info(f"Summary Result Available: {summary_raw is not None}, Story Result Available: {story_raw is not None}")

    template_summary_task_id = summary_task_id if is_processing_summary else None
    template_story_task_id = story_task_id if is_processing_story else None

    return render_template('index.html',
                           config=app.config,
                           summary_html=summary_html,
                           summary_raw=summary_raw,
                           story_html=story_html,
                           story_raw=story_raw,
                           is_processing_summary=is_processing_summary,
                           is_processing_story=is_processing_story,
                           summary_task_id=template_summary_task_id,
                           story_task_id=template_story_task_id
                           )


@app.route('/process', methods=['POST'])
def process_files():
    # Clear potentially active tasks and results from session
    session.pop('current_story_task_id', None)
    session.pop('current_summary_task_id', None)
    session.pop('download_summary_raw', None)
    session.pop('story_result_raw', None)

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

    temp_dir_base = None
    processing_errors = []
    try:
        temp_dir_base = tempfile.mkdtemp()
        app.logger.info(f"Created temp dir base for summary request: {temp_dir_base}")

        saved_details, validation_errors = file_handler.save_uploaded_files(uploaded_files, temp_dir_base)
        processing_errors.extend(validation_errors)
        successfully_saved_files = [d for d in saved_details if d.get('temp_path') and not d.get('error')]

        if not successfully_saved_files:
             if not processing_errors: processing_errors.append("No valid files could be processed for summary.")
             for error in processing_errors: flash(error, 'error')
             app.logger.warning(f"Summary file validation/saving failed: {processing_errors}")
             if temp_dir_base and os.path.exists(temp_dir_base):
                 try: shutil.rmtree(temp_dir_base)
                 except Exception as cleanup_err: app.logger.error(f"Error cleaning temp dir {temp_dir_base}: {cleanup_err}")
             return redirect(url_for('index'))

        task_id = str(uuid.uuid4())
        original_filenames = [d['original_name'] for d in successfully_saved_files]
        thread_file_details = [{'original_name': d['original_name'], 'temp_path': d['temp_path'], 'size': d['size']} for d in successfully_saved_files]

        thread = threading.Thread(target=run_summarizer_async, args=(
            task_id, thread_file_details, summary_level, original_filenames
        ))
        thread.daemon = True # Daemon threads exit when the main process exits
        thread.start()
        app.logger.info(f"Summarizer Task {task_id}: Background thread started.")
        session['current_summary_task_id'] = task_id

        for error in validation_errors: flash(error, 'error') # Flash errors encountered during saving
        return redirect(url_for('index')) # Redirect immediately, background task runs independently

    except Exception as e:
        error_id = uuid.uuid4()
        app.logger.error(f"Unhandled exception during summary request setup (Error ID: {error_id}).", exc_info=True)
        flash(f"A critical setup error occurred (Ref: {error_id}).", 'error')
        if temp_dir_base and os.path.exists(temp_dir_base):
            try: shutil.rmtree(temp_dir_base)
            except Exception as cleanup_err: app.logger.error(f"Error cleaning temp dir {temp_dir_base} after setup error: {cleanup_err}")
        return redirect(url_for('index'))


@app.route('/generate_story', methods=['POST'])
def generate_story():
    # Clear potentially active tasks and results from session
    session.pop('current_summary_task_id', None)
    session.pop('download_summary_raw', None)
    session.pop('current_story_task_id', None)
    session.pop('story_result_raw', None)

    github_url = request.form.get('github_url')
    if not github_url or not github_url.strip():
        flash('GitHub repository URL is required.', 'error')
        return redirect(url_for('index'))

    github_url = github_url.strip()

    # Basic validation before starting thread
    try:
        owner, repo = github_utils.parse_github_url(github_url)
    except GitHubUrlError as e:
         flash(f'Invalid GitHub URL: {e}', 'error')
         return redirect(url_for('index'))
    except Exception as e: # Catch any other parsing error
        flash(f'Error validating URL: {e}', 'error')
        return redirect(url_for('index'))

    try:
        task_id = str(uuid.uuid4())
        thread = threading.Thread(target=run_story_generation_async, args=(task_id, github_url))
        thread.daemon = True
        thread.start()
        app.logger.info(f"Story Task {task_id}: Background thread started for URL: {github_url}")
        session['current_story_task_id'] = task_id

        return redirect(url_for('index')) # Redirect immediately

    except Exception as e:
        error_id = uuid.uuid4()
        app.logger.error(f"Unhandled exception during story request setup (Error ID: {error_id}).", exc_info=True)
        flash(f"A critical setup error occurred while starting story generation (Ref: {error_id}).", 'error')
        return redirect(url_for('index'))


@app.route('/download_summary')
def download_summary():
    summary_content = session.get('download_summary_raw')
    if summary_content is None or (isinstance(summary_content, str) and summary_content.startswith("Error:")):
        flash('No valid summary available for download.', 'error')
        return redirect(url_for('index'))

    from io import BytesIO
    mem_file = BytesIO()
    try:
        mem_file.write(summary_content.encode('utf-8'))
        mem_file.seek(0)
    except Exception as e:
        app.logger.error(f"Error encoding summary for download: {e}", exc_info=True)
        flash('Failed to prepare summary for download.', 'error')
        return redirect(url_for('index'))
    app.logger.info("Providing summary file for download.")
    return send_file(
        mem_file, as_attachment=True, download_name='summary.txt', mimetype='text/plain; charset=utf-8'
    )

# --- Ensure session directory exists (for filesystem fallback ONLY) ---
# This check runs at import time if SESSION_TYPE is filesystem
session_dir_fallback = app.config.get("SESSION_FILE_DIR")
if app.config["SESSION_TYPE"] == "filesystem" and session_dir_fallback and not os.path.exists(session_dir_fallback):
     try:
        os.makedirs(session_dir_fallback)
        app.logger.info(f"Created session directory for fallback at startup: {session_dir_fallback}")
     except OSError as e:
        # This might happen due to permissions or race conditions
        app.logger.warning(f"Could not create session directory for fallback at startup: {e}")

# --- Remove the __main__ block for WSGI deployment ---
# The following block should be removed or commented out.
# Execution will be handled by uWSGI via the 'wsgi.py' file.
#
# if __name__ == '__main__':
#     # Ensure the session directory exists if using filesystem
#     # (This check is duplicated above and might run too late here)
#     # if app.config["SESSION_TYPE"] == "filesystem" and not os.path.exists(app.config["SESSION_FILE_DIR"]):
#     #     os.makedirs(app.config["SESSION_FILE_DIR"])
#     #     app.logger.info(f"Created session directory: {app.config['SESSION_FILE_DIR']}")
#
#     # debug=True is NOT recommended for production
#     # threaded=True is less relevant when using uWSGI workers/threads
#     app.run(debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 5000))) # Use PORT from env var
