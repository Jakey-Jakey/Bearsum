# Pocket Summarizer & Storyteller: System Design

**Document Purpose:** This document details the technical design and architecture of the Pocket Summarizer & Storyteller application based on the provided codebase. It is intended for technical analysis, including understanding by Large Language Models (LLMs).

## 1. High-Level Goal

To provide a web application allowing users to:
1.  Upload multiple text-based files (`.txt`, `.md`), have them summarized cohesively by an AI model (Perplexity), and receive the final summary with real-time progress updates.
2.  Input a public GitHub repository URL, have its README content and recent commit activity analyzed by an AI model (Perplexity), and receive a short, fictional "hackathon story" with real-time progress updates.

## 2. Core Features (Implemented)

*   **File Summarizer:**
    *   Multi-file upload (`.txt`, `.md`) via drag-and-drop or browse.
    *   File validation (count, size, extension).
    *   Selectable summary levels ("Short", "Medium", "Comprehensive").
    *   Asynchronous processing using Python `threading`.
    *   Perplexity API integration for initial per-file summaries and final combined summary.
    *   Real-time status updates via Server-Sent Events (SSE).
    *   Display results as rendered Markdown and raw text.
    *   Copy raw text and download summary functionality.
*   **GitHub Storyteller:**
    *   Input public GitHub repository URL.
    *   URL validation and owner/repo parsing.
    *   Asynchronous fetching of repository README content and recent commit history via GitHub API v3.
    *   Asynchronous processing using Python `threading`.
    *   Perplexity API integration to generate a fictional narrative based on README and commits.
    *   Real-time status updates via Server-Sent Events (SSE).
    *   Display result as rendered Markdown.
    *   Copy story text functionality.
*   **User Interface:**
    *   Tabbed interface to switch between Summarizer and Storyteller views.
    *   Theme toggle button (activates dark theme and switches to Storyteller tab).
    *   Responsive design.
    *   Clear loading/processing indicators.

## 3. Technology Stack

*   **Backend Framework:** Flask (`>=2.0`)
*   **Language:** Python 3
*   **Asynchronous Operations:** Python `threading` module, Flask-SSE (`>=0.2.1`)
*   **Real-time Backend:** Redis (`>=4.0`, required by Flask-SSE)
*   **AI Integration:** Perplexity API (via `openai>=1.0` client library, using `r1-1776` models)
*   **API Interaction:** `requests>=2.25` (for GitHub API)
*   **Session Management:** Flask-Session (`>=0.4`, filesystem backend)
*   **Configuration:** `python-dotenv>=0.19`
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript
*   **Markdown Processing:** `Markdown>=3.3`
*   **Utility:** `werkzeug>=2.0` (Flask dependency)

## 4. System Architecture Overview

*   **Frontend (`templates/index.html`, `static/script.js`, `static/style.css`):** A single-page interface rendered by Flask. Vanilla JavaScript handles user interactions (form submissions, drag/drop, validation, tab switching, theme toggle), UI state updates (showing/hiding elements, status messages), and Server-Sent Event (SSE) connection management. CSS provides styling, theming (including dark mode), and animations.
*   **Backend (`app.py`):** The core Flask application serves the HTML interface, handles POST requests for initiating summarization (`/process`) and story generation (`/generate_story`), manages user sessions using Flask-Session, starts background processing threads, and provides the SSE endpoint (`/stream`) for real-time updates.
*   **Asynchronous Processing (`threading` in `app.py`):** Background tasks (`run_summarizer_async`, `run_story_generation_async`) are executed in separate Python threads spawned from the Flask request handlers. This prevents long-running AI/API calls from blocking the main web server process. Each thread operates within a Flask application context (`with app.app_context():`) to access necessary components like the SSE publisher.
*   **Real-time Communication (`Flask-SSE`, `Redis`):** Background threads publish status updates and completion/error events using `sse.publish(message, channel=task_id)`. The frontend JavaScript establishes an `EventSource` connection to `/stream?channel=<task_id>` to receive these events and update the UI accordingly. A running Redis server is mandatory for Flask-SSE operation.
*   **Task State Management (`task_results` dictionary, Flask-Session):** A global Python dictionary named `task_results` within `app.py` serves as temporary, in-memory storage for task status. It's keyed by a unique task ID (UUID) generated per request. Each entry stores the task type (`summary`/`story`), state (`processing`/`completed`/`error`), the final result (summary/story text or error message), and a list of errors. Flask-Session is used to store the `task_id` currently active for the user's browser session (`current_summary_task_id` or `current_story_task_id`). **Note:** `task_results` is volatile and does not persist across application restarts.
*   **Utility Modules (`pocketflow_logic/utils/`):** Helper modules encapsulate specific functionalities:
    *   `file_handler.py`: Manages uploaded file validation (count, size, type based on `MAX_FILES`, `MAX_FILE_SIZE_MB`, `ALLOWED_EXTENSIONS`), secure filename generation, and temporary file saving/reading.
    *   `llm_caller.py`: Interfaces with the Perplexity API using the `openai` client library. Handles API key configuration, defines model names (`INITIAL_SUMMARY_MODEL`, `COMBINATION_MODEL`, `STORY_MODEL` set to `r1-1776`), centralizes prompt templates, makes API calls (`call_llm`), and includes basic error handling for API responses.
    *   `github_utils.py`: Interacts with the public GitHub API v3 using `requests`. Includes functions to parse GitHub URLs (`parse_github_url`), fetch README content (`get_readme_content`), and fetch recent commit data (`get_recent_commits`). Defines custom exceptions (`GitHubUrlError`, `RepoNotFoundError`, `GitHubApiError`) for specific failure modes.
*   **PocketFlow Framework (`pocketflow/`, `pocketflow_logic/flow.py`, `nodes.py`):** The codebase includes the PocketFlow library and definitions for a summarization workflow (`FileProcessorNode`, `CombineSummariesNode`, `create_summary_flow`). **Important:** The current implementation in `app.py::run_summarizer_async` bypasses this framework and executes the summarization logic directly through calls to the utility modules. The PocketFlow code is present but not functionally integrated into the main application path executed by `app.py`.

## 5. Detailed Workflow - File Summarizer

1.  **Trigger:** User submits the summarizer form via POST request to `/process`. Request includes uploaded files (`files`) and selected detail level (`summary_level`).
2.  **Route Handling (`app.py::process_files`):**
    *   Retrieves uploaded files and `summary_level`.
    *   Creates a temporary directory using `tempfile.mkdtemp()`.
    *   Calls `pocketflow_logic.utils.file_handler.save_uploaded_files` to validate files (count <= `MAX_FILES`, size <= `MAX_FILE_SIZE_MB`, extension in `ALLOWED_EXTENSIONS`) and save valid ones to the temp directory, returning details and errors.
    *   If no valid files are saved, flashes errors and redirects to index.
    *   Generates a unique `task_id` using `uuid.uuid4()`.
    *   Stores the `task_id` in the user's session: `session['current_summary_task_id'] = task_id`.
    *   Extracts details (`original_name`, `temp_path`, `size`) for successfully saved files.
    *   Starts a new background thread targeting `run_summarizer_async`, passing `task_id`, file details list, `summary_level`, and original filenames list.
    *   Flashes any validation errors from `save_uploaded_files`.
    *   Redirects the user to the index page (`/`).
3.  **Background Processing (`app.py::run_summarizer_async` within Thread):**
    *   Enters Flask application context (`with app.app_context():`).
    *   Initializes task state in the global `task_results` dictionary: `task_results[task_id] = {'type': 'summary', 'state': 'processing', 'errors': []}`.
    *   Publishes initial status via SSE: `sse.publish({"type": "status", "message": "Initializing summarization..."}, channel=task_id)`.
    *   Iterates through the list of saved file details:
        *   Publishes SSE status: `Processing file {i+1}/{total_files}: '{original_name}'...`.
        *   Calls `pocketflow_logic.utils.file_handler.read_file_content` to get file text. Handles read errors (returns `None`) and empty files. Appends errors to a local `errors` list and stores placeholder in `all_summaries` dict.
        *   If content is valid, publishes SSE status: `Requesting summary for '{original_name}'...`.
        *   Calls `pocketflow_logic.utils.llm_caller.get_initial_summary` with file content. This uses `INITIAL_SUMMARY_MODEL`.
        *   Handles potential "Error:" prefix in the LLM response, logging and appending to `errors`.
        *   Publishes SSE status: `Received summary for '{original_name}'.` or `LLM Error...`.
        *   Stores the received summary or error string in the `all_summaries` dictionary, keyed by original filename.
    *   Filters `all_summaries` to create `valid_summaries` dictionary (excluding errors/skipped).
    *   If `valid_summaries` is empty, constructs an error message, sets `final_state` to "error", stores error in `task_results`.
    *   If `valid_summaries` exists:
        *   Publishes SSE status: `Combining {len(valid_summaries)} summaries ({summary_level} level)...`.
        *   Constructs `combined_text` by joining valid summaries with headers.
        *   Calls `pocketflow_logic.utils.llm_caller.get_combined_summary` with `combined_text` and `summary_level`. This uses `COMBINATION_MODEL`.
        *   Checks final summary for "Error:" prefix. Sets `final_state` accordingly ("completed" or "error").
        *   Appends a note about failed/skipped files to the final summary string.
    *   Stores the final summary string (or error message) in `task_results[task_id]['result']`.
    *   Stores any accumulated errors in `task_results[task_id]['errors']`.
    *   Updates `task_results[task_id]['state']` to the determined `final_state`.
    *   Publishes final SSE status (`completed` or `error`): `sse.publish({"type": final_state, ...}, channel=task_id)`.
    *   Cleans up the temporary directory using `shutil.rmtree(temp_dir)`.
4.  **Frontend Update (`static/script.js`):**
    *   Upon page load after redirect, checks `is_processing_summary` flag (passed from Flask).
    *   If true, calls `connectSSE(summary_task_id, 'summary')`.
    *   `connectSSE` creates an `EventSource` listening to `/stream?channel=<task_id>`.
    *   Displays the processing indicator UI section.
    *   Updates the status message (`#latest-status`) based on incoming SSE `status` events.
    *   Upon receiving an SSE event with `type: 'completed'` or `type: 'error'`, it closes the `EventSource`, updates the status one last time, and triggers a page reload (`window.location.reload()`).
5.  **Result Display (`app.py::index` after reload):**
    *   The `index` route checks `session.get('current_summary_task_id')`.
    *   If the ID exists, it checks the global `task_results` dictionary.
    *   If the task state is 'completed' or 'error', it `pop`s the entry from `task_results`.
    *   Removes `current_summary_task_id` from the session.
    *   If the result is not an error, it renders the Markdown summary to HTML using the `Markdown` library.
    *   Stores the raw summary text in `session['download_summary_raw']` for the download link.
    *   Flashes any errors stored in the retrieved task results.
    *   Renders `templates/index.html`, passing the rendered HTML (`summary_html`), raw text (`summary_raw`), and setting `is_processing_summary` to `False`. The template then displays the results section.

## 6. Detailed Workflow - GitHub Storyteller

1.  **Trigger:** User submits the storyteller form via POST request to `/generate_story`. Request includes the `github_url`.
2.  **Route Handling (`app.py::generate_story`):**
    *   Retrieves `github_url` from the form data.
    *   Performs initial validation: checks if URL is non-empty and strips whitespace.
    *   Calls `pocketflow_logic.utils.github_utils.parse_github_url` to validate the URL format (`https://github.com/owner/repo`) and extract owner/repo *before* starting the thread. If validation fails (raises `GitHubUrlError`), flashes an error message and redirects to index.
    *   Generates a unique `task_id` using `uuid.uuid4()`.
    *   Stores the `task_id` in the user's session: `session['current_story_task_id'] = task_id`.
    *   Starts a new background thread targeting `run_story_generation_async`, passing `task_id` and the validated `github_url`.
    *   Redirects the user to the index page (`/`).
3.  **Background Processing (`app.py::run_story_generation_async` within Thread):**
    *   Enters Flask application context (`with app.app_context():`).
    *   Initializes task state in `task_results`: `task_results[task_id] = {'type': 'story', 'state': 'processing', 'errors': []}`.
    *   Publishes SSE status: `Validating GitHub URL...`.
    *   Calls `pocketflow_logic.utils.github_utils.parse_github_url` again to get owner/repo. Handles `GitHubUrlError` by setting an error message and re-raising.
    *   **Fetch README:**
        *   Publishes SSE status: `Fetching README for {owner}/{repo}...`.
        *   Calls `pocketflow_logic.utils.github_utils.get_readme_content(owner, repo)`.
        *   Handles `GitHubApiError` (e.g., rate limit): logs warning, adds warning to `task_results[task_id]['errors']`, publishes warning SSE, sets `readme_content` to `None`, continues.
        *   Handles other exceptions during README fetch: logs error, adds warning to errors, publishes warning SSE, sets `readme_content` to `None`, continues.
        *   Handles `None` return (e.g., 404 Not Found): publishes status `README not found...`, `readme_content` remains `None`.
    *   **Fetch Commits:**
        *   Publishes SSE status: `Fetching recent commits for {owner}/{repo}...`.
        *   Calls `pocketflow_logic.utils.github_utils.get_recent_commits(owner, repo, days=3, limit=30)`.
        *   Handles `RepoNotFoundError`: Sets specific error message, re-raises (fatal).
        *   Handles `GitHubApiError`: Sets specific error message, re-raises (fatal).
    *   **Context Aggregation & LLM Call:**
        *   Checks if both `commits` list and `readme_content` are empty/None. If so, sets an error message ("No recent commits found and no README available..."), sets `final_state` to "error", stores error, publishes error SSE, and skips LLM call.
        *   If content exists, publishes SSE status: `Formatting context...`.
        *   Constructs `combined_context` string:
            *   Appends README content (if available), potentially truncated to 10000 characters.
            *   Appends formatted commit history (Author, Date, Message preview) if commits exist.
        *   Publishes SSE status: `Asking the AI storyteller...`.
        *   Calls `pocketflow_logic.utils.llm_caller.get_hackathon_story(repo, combined_context)`. This uses `STORY_MODEL`.
        *   Checks response for "Error:" prefix. If error, sets error message and raises `ValueError`.
        *   If successful, stores the generated story Markdown in `task_results[task_id]['result']` and sets `final_state` to "completed".
    *   **Error Handling:** Catches `GitHubUrlError`, `RepoNotFoundError`, `GitHubApiError`, `ValueError` (from LLM error), and general `Exception`. Logs errors appropriately, stores the primary error message in `task_results[task_id]['result']` and `['errors']`, sets `final_state` to "error".
    *   **Finalization:**
        *   Updates `task_results[task_id]['state']` based on `final_state`.
        *   Provides default error messages if needed.
        *   Publishes final SSE status (`completed` or `error`).
4.  **Frontend Update (`static/script.js`):** Similar to Summarizer flow, using `is_processing_story` flag and `story_task_id`. Connects to SSE, updates UI, reloads on completion/error.
5.  **Result Display (`app.py::index` after reload):** Similar to Summarizer flow. Checks `session.get('current_story_task_id')`, retrieves/pops results from `task_results`, clears session key. Renders the story Markdown to HTML. Passes `story_html` and `story_raw` (raw Markdown) to the template for display.

## 7. Key Utility Details

*   **`llm_caller.py`:**
    *   Initializes `openai` client targeting Perplexity API (`https://api.perplexity.ai`) using `PERPLEXITY_API_KEY`.
    *   Defines models used: `INITIAL_SUMMARY_MODEL`, `COMBINATION_MODEL`, `STORY_MODEL` are all set to `"r1-1776"`.
    *   Contains prompt templates as multi-line strings (`INITIAL_SUMMARY_PROMPT_TEMPLATE`, `COMBINATION_PROMPT_TEMPLATE`, `HACKATHON_STORY_PROMPT_TEMPLATE`).
    *   `call_llm(prompt, model)`: Sends the prompt to the specified model using `client.chat.completions.create`. Handles common `openai` exceptions (RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError, APIStatusError). Returns cleaned response content (strips `<think>` blocks) or an "Error: ..." string.
    *   Helper functions (`get_initial_summary`, `get_combined_summary`, `get_hackathon_story`) format the specific prompts using the templates and call `call_llm`.
*   **`github_utils.py`:**
    *   Uses `requests` for HTTP calls to `https://api.github.com`.
    *   `parse_github_url(url)`: Uses `urllib.parse` and regex (`VALID_NAME_REGEX`) to validate and extract `owner`, `repo` from a GitHub URL string. Raises `GitHubUrlError` on invalid input.
    *   `get_readme_content(owner, repo)`: Fetches `/repos/{owner}/{repo}/readme`. Handles 200 (decodes base64 content), 404 (returns `None`), 403 (raises `GitHubApiError`), other errors (raises `GitHubApiError`). Includes timeout and handles `requests.exceptions`. Returns decoded string or `None`.
    *   `get_recent_commits(owner, repo, days=3, limit=30)`: Fetches `/repos/{owner}/{repo}/commits` with `since` and `per_page` parameters. Parses response JSON, extracting author name, date, and first line of commit message for the specified limit. Handles 404 (raises `RepoNotFoundError`), 403 (raises `GitHubApiError`), 422 (returns empty list), other errors (raises `GitHubApiError`). Includes timeout and handles `requests.exceptions`. Returns a list of commit dictionaries.
    *   Defines custom exceptions: `GitHubUrlError(ValueError)`, `RepoNotFoundError(Exception)`, `GitHubApiError(Exception)`.
*   **`file_handler.py`:**
    *   Constants: `ALLOWED_EXTENSIONS = {'txt', 'md'}`, `MAX_FILE_SIZE_MB = 1`, `MAX_FILES = 5`.
    *   `allowed_file(filename)`: Checks file extension.
    *   `save_uploaded_files(files, temp_dir)`: Iterates through Flask `FileStorage` objects. Checks file count against `MAX_FILES`. Validates extension using `allowed_file`. Checks file size against `MAX_FILE_SIZE_BYTES`. Uses `secure_filename` and prepends a UUID for unique, safe filenames in the `temp_dir`. Saves valid files using `file.save()`. Returns a list of dictionaries with file details (including `error` if validation failed) and a separate list of error messages.
    *   `read_file_content(filepath)`: Opens and reads a file with UTF-8 encoding. Returns content string or `None` on error.

## 8. Frontend Logic (`static/script.js`)

*   **Initialization:** Reads initial state (processing flags, task IDs) from hidden input fields populated by Flask. Determines if a task is active on load.
*   **Event Listeners:** Attaches listeners for:
    *   Form submissions (`#upload-form`, `#story-form`).
    *   File input changes (`#files`).
    *   Drag/drop events on `#drop-zone` (enter, over, leave, drop).
    *   Clicking the "Browse Files" link/drop zone.
    *   View toggle buttons (`.btn-toggle`).
    *   Copy buttons (`#copy-button-summary`, `#copy-button-story`).
    *   Tab buttons (`.tab-button`).
    *   Theme toggle button (`#bear-toggle`).
    *   New task button (`#new-task-button`).
*   **File Handling:** `updateFileList` displays selected files and validation errors. `validateFiles` performs client-side checks. Drag/drop handlers manage file input state.
*   **SSE Management (`connectSSE`):** Creates/closes `EventSource`. Handles `onopen`, `onmessage`, `onerror`. Updates UI (`#latest-status`, processing indicator visibility). Triggers page reload on task end (`completed`/`error`). Manages `activeTaskId` to ensure messages are relevant.
*   **UI State:** Functions like `showElementWrapper`, `hideElementWrapper`, `switchTab`, `setViewWrapperHeight` manage the visibility and layout of different sections (forms, processing indicator, results, tabs). Uses `localStorage` to persist active tab and theme preference.
*   **Theme Toggle (`#bear-toggle` listener):** Adds/removes `dark-theme` and `storyteller-mode` classes on `body`. Calls `switchTab` to change view. Manages `localStorage` for persistence and tooltip visibility (`bearTooltipSeen`).
*   **Form Submission (`handleFormSubmit`):** Performs client-side validation based on task type. If valid, updates UI to show loading state and allows the natural form submission to proceed (triggering backend processing). If invalid, prevents submission and alerts user.
*   **Copy Functionality (`handleCopyClick`):** Uses `navigator.clipboard.writeText` to copy content from target elements (`#summary-text-raw`, `#story-rendered`). Provides visual feedback on the button.

## 9. Backend Logic (`app.py`)

*   **Setup:** Initializes Flask app, loads `.env`, configures logging, Flask-Session (filesystem), Flask-SSE (Redis URL), defines file limits in `app.config`. Includes security check for default `SECRET_KEY` in non-debug mode.
*   **Routes:**
    *   `/` (GET): Main page. Checks session for active task IDs. Queries `task_results` dictionary. If task completed/errored, retrieves results, clears task from `task_results` and session. Renders Markdown if applicable. Passes processing flags, results, and task IDs to `index.html`. Manages flashing errors.
    *   `/process` (POST): Handles file summarizer submission. Validates input, calls `file_handler.save_uploaded_files`, starts `run_summarizer_async` thread, stores task ID in session, redirects to `/`.
    *   `/generate_story` (POST): Handles story generator submission. Validates URL format *before* threading, starts `run_story_generation_async` thread, stores task ID in session, redirects to `/`.
    *   `/download_summary` (GET): Retrieves raw summary from `session['download_summary_raw']`, creates in-memory file (`BytesIO`), sends it as an attachment (`summary.txt`).
    *   `/stream` (GET): Endpoint for Flask-SSE connections. Handled by the extension.
*   **Background Functions (`run_summarizer_async`, `run_story_generation_async`):** Execute the core logic for each feature within separate threads. Interact with utility modules (`file_handler`, `llm_caller`, `github_utils`). Use `sse.publish` to send progress updates. Update the shared `task_results` dictionary with state and results. Handle exceptions within the thread.
*   **Task Management:** Relies on the global `task_results` dictionary (key: task ID, value: dict with type, state, result, errors) and Flask session variables (`current_summary_task_id`, `current_story_task_id`) to link user sessions to ongoing tasks.

## 10. Scalability & Production Considerations

*   **Concurrency:** Python `threading` is limited by the Global Interpreter Lock (GIL) for CPU-bound tasks, but suitable for I/O-bound tasks like API calls here. However, it doesn't offer robust process management or scaling across multiple machines. Use Celery/RQ with workers for production.
*   **State Management:** The in-memory `task_results` dictionary is unsuitable for production (data loss on restart, not scalable). Use Redis (already required for SSE) or a database for persistent and scalable task state tracking.
*   **SSE:** Flask-SSE with Redis is viable but ensure Redis is configured for persistence and high availability if needed. Alternatives like WebSockets might offer more flexibility.
*   **Deployment:** Use Gunicorn or uWSGI behind a reverse proxy like Nginx.
*   **Error Monitoring:** Integrate more robust error tracking (e.g., Sentry).
*   **API Rate Limits:** Implement handling for Perplexity and GitHub API rate limits (e.g., backoff strategies, potentially using authenticated GitHub requests if limits become an issue).
*   **Security:** Ensure `FLASK_SECRET_KEY` is securely managed. Consider input sanitization if LLM outputs are ever used in ways beyond simple Markdown rendering (e.g., if rendered directly into complex HTML contexts).
