# app.py
import os
import uuid
import tempfile
import shutil
import logging
import threading
import markdown
# --- Ensure send_file is imported ---
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify, send_file
# ------------------------------------
from flask_session import Session
from flask_sse import sse
from dotenv import load_dotenv

# Import PocketFlow flow creation function
from pocketflow_logic.flow import create_summary_flow

# Import utilities
from pocketflow_logic.utils import file_handler

# --- Configuration ---
load_dotenv()
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
app.logger.setLevel(logging.INFO)

# --- Flask-Session Configuration ---
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-replace-me!")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "./flask_session"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
Session(app)
# ---------------------------------

# --- Flask-SSE Configuration ---
app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app.register_blueprint(sse, url_prefix='/stream')
# -----------------------------

# --- Simple In-Memory Task Storage (HACKATHON ONLY) ---
task_results = {}
# ------------------------------------------------------

# Security check for default SECRET_KEY
if not app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
    app.logger.critical("SECURITY ALERT: Running in non-debug mode with default SECRET_KEY!")
    raise RuntimeError("FLASK_SECRET_KEY must be set to a strong, unique value in production (non-debug) mode.")
elif app.debug and app.config["SECRET_KEY"] == "dev-secret-key-replace-me!":
     app.logger.warning("SECURITY WARNING: Using default SECRET_KEY in debug mode. Set FLASK_SECRET_KEY environment variable.")

# Pass file limits to template context via config
app.config['MAX_FILES'] = file_handler.MAX_FILES
app.config['MAX_FILE_SIZE_MB'] = file_handler.MAX_FILE_SIZE_MB

# --- Background Task Function ---
def run_pocketflow_async(task_id, temp_file_details, summary_level, original_filenames):
    """Runs the PocketFlow summarization in a background thread."""
    with app.app_context(): # Needed to access app context (e.g., for sse.publish)
        app.logger.info(f"Task {task_id}: Background thread started.")
        shared = {
            "request_id": task_id, # Use task_id as request_id
            "original_filenames": original_filenames,
            "temp_file_details": temp_file_details,
            "file_summaries": {},
            "final_summary": None,
            "errors": [],
            "summary_level": summary_level,
            "status_updates": [], # Nodes will publish via SSE using helper
            "task_id": task_id
        }

        final_state = "unknown"
        try:
            # Initialize status via SSE
            sse.publish({"type": "status", "message": "Initializing process..."}, channel=task_id)

            summary_flow = create_summary_flow()
            summary_flow.run(shared) # Execute the flow

            # Check for errors collected during the flow
            if shared.get("errors"):
                final_state = "error"
                # Also add pocketflow errors to the final results errors
                task_results.setdefault(task_id, {}).setdefault("errors", []).extend(shared["errors"])

            else:
                final_state = "completed"

        except Exception as e:
            error_id = uuid.uuid4()
            app.logger.error(f"Task {task_id}: Unhandled exception in background thread (Error ID: {error_id}).", exc_info=True)
            # Ensure errors list exists in results before appending
            task_results.setdefault(task_id, {}).setdefault("errors", []).append(f"A critical background error occurred (Ref: {error_id}).")
            # Ensure summary reflects failure
            task_results.setdefault(task_id, {})["summary"] = f"Processing failed due to a background error (Ref: {error_id})."
            final_state = "error"
        finally:
            # Store final results (ensure keys exist)
            results_entry = task_results.setdefault(task_id, {})
            results_entry["summary"] = shared.get("final_summary", results_entry.get("summary", "Error: No summary generated.")) # Use existing error summary if set
            results_entry.setdefault("errors", []) # Ensure errors list exists
            results_entry["status"] = shared.get("status_updates", []) # Note: nodes don't append here anymore, but keeping for structure
            results_entry["state"] = final_state
            app.logger.info(f"Task {task_id}: Stored final results. State: {final_state}")

            # Publish completion/error event via SSE
            sse.publish({"type": final_state, "message": f"Processing {final_state}."}, channel=task_id)


# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    task_id = session.get('current_task_id')
    results = None
    is_processing = False

    if task_id and task_id in task_results:
        # Task finished, results are ready
        results = task_results.pop(task_id) # Get results and remove from temp storage
        session.pop('current_task_id', None) # Clear task ID from session
        app.logger.info(f"Task {task_id}: Results retrieved and cleared.")

        # Prepare results for template
        summary_raw = results.get("summary")
        errors = results.get("errors")
        # Status updates are now primarily handled live via SSE,
        # but we could pass the final stored list if desired for a complete log.
        # status_updates = results.get("status")
        status_updates = None # Let's rely on SSE for status display for now
        summary_html = None

        if summary_raw and not summary_raw.startswith("Error:"):
            try:
                 summary_html = markdown.markdown(summary_raw, extensions=['fenced_code', 'sane_lists'])
                 session['download_summary_raw'] = summary_raw
            except Exception as md_err:
                 app.logger.error(f"Markdown rendering failed: {md_err}")
                 errors = (errors or []) + ["Failed to render summary preview."]
                 summary_html = None
                 session.pop('download_summary_raw', None)

        if errors:
            for error in errors:
                flash(error, 'error')

        return render_template('index.html',
                               config=app.config,
                               summary_html=summary_html,
                               summary_raw=summary_raw,
                               error_messages=None, # Use flash
                               status_updates=status_updates, # Pass final log if needed, else None
                               task_id=None,
                               is_processing=False)

    elif task_id:
        # Task ID exists in session but not yet in results -> still processing
        is_processing = True
        app.logger.info(f"Task {task_id}: Still processing, rendering page for SSE connection.")
        session.pop('download_summary_raw', None)

    else:
         session.pop('download_summary_raw', None)


    # Render initial page or processing page
    return render_template('index.html',
                           config=app.config,
                           task_id=task_id,
                           is_processing=is_processing)


@app.route('/process', methods=['POST'])
def process_files():
    session.pop('current_task_id', None)
    session.pop('download_summary_raw', None)

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

    temp_dir = None
    processing_errors = [] # Use a local list to collect errors during this request

    try:
        temp_dir = tempfile.mkdtemp()
        app.logger.info(f"Created temp dir for request: {temp_dir}")

        saved_details, validation_errors = file_handler.save_uploaded_files(uploaded_files, temp_dir)
        processing_errors.extend(validation_errors) # Add validation errors

        successfully_saved_files = [d for d in saved_details if d.get('temp_path') and not d.get('error')]

        if not successfully_saved_files:
             if not processing_errors:
                 processing_errors.append("No valid files could be processed.")
             # Flash errors directly before redirecting
             for error in processing_errors: flash(error, 'error')
             app.logger.warning(f"File validation/saving failed: {processing_errors}")
             # Cleanup temp dir early if no files saved
             if temp_dir and os.path.exists(temp_dir):
                 try: shutil.rmtree(temp_dir)
                 except Exception as cleanup_err: app.logger.error(f"Error cleaning up temp dir {temp_dir} after validation failure: {cleanup_err}")
             return redirect(url_for('index'))

        # Start Background Task
        task_id = str(uuid.uuid4())
        original_filenames = [d['original_name'] for d in successfully_saved_files]
        thread_file_details = [{'original_name': d['original_name'], 'temp_path': d['temp_path'], 'size': d['size']} for d in successfully_saved_files]

        # Pass temp_dir path to thread for potential cleanup later if implemented
        # For now, we still rely on potential leakage or manual cleanup if app crashes mid-thread
        thread = threading.Thread(target=run_pocketflow_async, args=(
            task_id, thread_file_details, summary_level, original_filenames
        ))
        thread.daemon = True
        thread.start()
        app.logger.info(f"Task {task_id}: Background thread started.")

        session['current_task_id'] = task_id

        # Flash initial validation errors if any
        for error in validation_errors: flash(error, 'error')

        return redirect(url_for('index'))

    except Exception as e:
        error_id = uuid.uuid4()
        app.logger.error(f"Unhandled exception during request setup (Error ID: {error_id}).", exc_info=True)
        flash(f"A critical setup error occurred (Ref: {error_id}).", 'error')
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except Exception as cleanup_err: app.logger.error(f"Error cleaning up temp dir {temp_dir} after setup error: {cleanup_err}")
        return redirect(url_for('index'))


@app.route('/download_summary')
def download_summary():
    summary_content = session.get('download_summary_raw') # Get raw summary stored by GET route

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
    # --- This line should now work after importing send_file ---
    return send_file(
        mem_file,
        as_attachment=True,
        download_name='summary.txt',
        mimetype='text/plain; charset=utf-8'
    )

if __name__ == '__main__':
    ## WARNING: debug=True is for development ONLY. Use a production WSGI server (e.g., Gunicorn) for deployment. ##
    app.run(debug=True, host='0.0.0.0', port=5000)