---
layout: default
title: "Pocket Summarizer Design"
---

# Pocket Summarizer: Design Documentation

This document outlines the design and architecture of the Pocket Summarizer application, built using Python, Flask, and the PocketFlow framework. It's intended for understanding the system's components, data flow, and implementation details, potentially for LLM ingestion or developer onboarding.

## 1. Requirements

### 1.1. Core Goal
To provide a web application allowing users to upload multiple text-based files (`.txt`, `.md`), have them summarized cohesively by an AI model (Perplexity), and receive the final summary with options for detail level and output format (rendered Markdown, raw text, download, copy).

### 1.2. Key Features
*   **Multi-File Upload:** Accept multiple `.txt` and `.md` files per request.
*   **Drag & Drop Interface:** Allow users to drag files onto a designated area for uploading.
*   **AI Summarization:** Utilize the Perplexity AI API (via `llama-3-sonar` models) to generate summaries.
*   **Selectable Summary Levels:** Offer "Short", "Medium", and "Comprehensive" options for the final combined summary detail.
*   **Asynchronous Processing:** Handle the summarization process in the background to avoid blocking the web server and provide a responsive UI.
*   **Live Status Updates:** Use Server-Sent Events (SSE) to push real-time progress updates from the backend to the frontend during processing.
*   **Output Views:** Display the final summary as both rendered Markdown and raw text, with a toggle.
*   **Output Actions:** Allow users to copy the raw summary text to the clipboard and download it as a `.txt` file.
*   **Theming:** Apply a "Honey/Bear" visual theme suitable for the Bearhacks event.

### 1.3. Technology Stack
*   **Backend:** Python 3
*   **Web Framework:** Flask
*   **Workflow Orchestration:** PocketFlow (custom minimalist framework provided)
*   **Session Management:** Flask-Session (filesystem backend)
*   **Real-time Updates:** Flask-SSE (requires Redis backend)
*   **Background Tasks:** Python `threading` module (simplification for hackathon)
*   **LLM API:** Perplexity AI API (accessed via `openai` Python library compatibility mode)
*   **Markdown Processing:** `Markdown` library
*   **Frontend:** HTML5, CSS3, JavaScript (vanilla)
*   **Dependencies:** See `requirements.txt` (includes `Flask`, `openai`, `python-dotenv`, `werkzeug`, `Flask-Session`, `Flask-SSE`, `Markdown`, `redis`)

## 2. Flow Design

The application employs an asynchronous request-response pattern orchestrated by Flask, PocketFlow (within a background thread), and Server-Sent Events (SSE).

### 2.1. High-Level User Interaction Flow
1.  **Upload (GET `/`):** User visits the main page. The server renders the initial upload form.
2.  **Submit (POST `/process`):**
    *   User selects/drops files, chooses summary level, and submits the form.
    *   Flask (`app.py`) receives the request.
    *   Validates inputs (file count, size, type, summary level).
    *   Saves valid uploaded files to a unique temporary directory.
    *   Generates a unique `task_id`.
    *   Starts a background thread (`run_pocketflow_async`), passing `task_id`, temporary file details, and summary level.
    *   Stores the `task_id` in the user's session (`session['current_task_id']`).
    *   Redirects the user back to the main page (`GET /`).
3.  **Processing (GET `/` + SSE `/stream`):**
    *   The browser loads the main page (`GET /`).
    *   Flask (`app.py`) sees `current_task_id` in the session but no results yet in `task_results`. It renders the page in "processing" mode, passing `is_processing=True` and the `task_id` to the template.
    *   Frontend JavaScript (`index.html`) detects `is_processing` and `task_id`. It establishes an SSE connection to `/stream?channel=<task_id>`.
    *   The in-page loading indicator and live status area are displayed.
4.  **Background PocketFlow Execution (Thread):**
    *   The `run_pocketflow_async` function executes the PocketFlow graph.
    *   Nodes within the flow (`FileProcessorNode`, `CombineSummariesNode`) perform their tasks.
    *   Nodes use a helper (`publish_sse`) to send status updates (`{'type': 'status', 'message': '...'}`) via SSE using the `task_id` as the channel.
    *   Frontend JS receives these messages and updates the live status display (`#latest-status`).
5.  **Completion (Thread + SSE):**
    *   The background thread finishes PocketFlow execution.
    *   It stores the final summary and any errors in the global `task_results` dictionary, keyed by `task_id`.
    *   It publishes a final SSE message (`{'type': 'completed', ...}` or `{'type': 'error', ...}`) on the task's channel.
6.  **Results Display (SSE -> Reload -> GET `/`):**
    *   Frontend JS receives the `completed` or `error` SSE message.
    *   It closes the SSE connection.
    *   It triggers a page reload (`window.location.reload()`).
    *   The browser requests the main page again (`GET /`).
    *   Flask (`app.py`) sees `current_task_id` in the session *and* finds corresponding results in `task_results`.
    *   It retrieves (`pop`) the results from `task_results` and clears the `task_id` from the session.
    *   It renders the Markdown summary to HTML.
    *   It stores the raw summary in the session (`session['download_summary_raw']`) for the download button.
    *   It renders the template, passing the rendered HTML, raw text, and final status log (if implemented). `is_processing` is now `False`.
    *   The template displays the results section (rendered/raw views, copy/download buttons) and hides the processing indicator.

### 2.2. PocketFlow Graph
A simple linear flow executed within the background thread:

```mermaid
graph LR
    Start --> A[FileProcessorNode];
    A -- default --> B(CombineSummariesNode);
    B --> End;
```

*   **`FileProcessorNode`:** A `BatchNode` that iterates through each valid uploaded file.
*   **`CombineSummariesNode`:** A standard `Node` that aggregates results from the previous step.

## 3. Utilities (`pocketflow_logic/utils/`)

*   **`file_handler.py`:**
    *   **Purpose:** Handles secure saving of uploaded files, validation, and reading content.
    *   **Key Functions:**
        *   `save_uploaded_files(files, temp_dir)`: Validates count, size (<1MB), type (`.txt`, `.md`). Uses `werkzeug.secure_filename` and UUIDs for safe, unique temporary filenames within the provided `temp_dir`. Returns structured details and errors.
        *   `read_file_content(filepath)`: Reads UTF-8 text content from a file path.
*   **`llm_caller.py`:**
    *   **Purpose:** Provides an interface to the Perplexity AI API using the `openai` library in compatibility mode. Handles API key configuration, prompt formatting, model selection, and basic error handling.
    *   **Configuration:** Reads `PERPLEXITY_API_KEY` from `.env`. Sets `base_url` to `https://api.perplexity.ai`.
    *   **Models:** Uses `llama-3-sonar-small-8b-chat` for initial summaries and `llama-3-sonar-large-8b-chat` for combination by default.
    *   **Key Functions:**
        *   `call_llm(prompt, model)`: Sends the request to the Perplexity API via the configured `openai` client. Handles common API errors (Auth, Rate Limit, Connection, etc.) and returns either the text content or an error string.
        *   `get_initial_summary(text_content)`: Formats the initial summary prompt and calls `call_llm` with the small model.
        *   `get_combined_summary(summaries_text, level)`: Formats the combination prompt using the provided `level` ("short", "medium", "comprehensive") and calls `call_llm` with the large model.

## 4. Node Design (`pocketflow_logic/nodes.py`)

Nodes are executed within the background thread (`run_pocketflow_async`) and receive the `task_id` via the `shared` dictionary to publish SSE updates.

*   **`FileProcessorNode(BatchNode)`:**
    *   **`prep(shared)`:** Retrieves `task_id`, publishes initial SSE status, gets list of valid `temp_file_details` from `shared`. Returns the list of file detail dicts.
    *   **`exec(item)`:** Processes one file detail dict (`item`). Publishes SSE status ("Processing 'file.txt'...", "Reading...", "Requesting summary..."). Calls `file_handler.read_file_content`. Calls `llm_caller.get_initial_summary`. Publishes SSE status ("Received summary..."). Returns `{'original_name': ..., 'summary': ...}`.
    *   **`exec_fallback(prep_res, exc)`:** Handles errors during `exec` after retries. Publishes SSE error status. Returns error summary structure.
    *   **`post(shared, prep_res, exec_res_list)`:** Collects results from `exec_res_list`, stores them in `shared['file_summaries']`. Publishes final processing count via SSE. Returns `"default"` action.
*   **`CombineSummariesNode(Node)`:**
    *   **`prep(shared)`:** Retrieves `task_id`, publishes SSE status. Retrieves `file_summaries` and `summary_level` from `shared`. Filters valid summaries, combines them into a single string. Publishes SSE status ("Combining N summaries..."). Returns `(combined_text, failed_files, processed_files, summary_level)`.
    *   **`exec(inputs)`:** Unpacks inputs. Publishes SSE status ("Requesting final summary..."). Calls `llm_caller.get_combined_summary` with `combined_text` and `summary_level`. Publishes SSE status ("Received final summary..."). Returns `(final_summary, failed_files)`.
    *   **`exec_fallback(prep_res, exc)`:** Handles errors during final combination LLM call. Publishes SSE error status. Returns error summary structure.
    *   **`post(shared, prep_res, exec_res)`:** Unpacks results. Appends notes about failed files to the `final_summary` string. Stores the result in `shared['final_summary']`. *Note: Status publishing is handled by `run_pocketflow_async` upon completion.*

## 5. Implementation Notes

*   **Flask Structure (`app.py`):** Defines routes (`/`, `/process`, `/download_summary`), configures Flask extensions (Session, SSE), manages application context for the background thread, handles temporary result storage (`task_results` dict).
*   **Background Task (`threading`):** Uses Python's built-in `threading` for simplicity. The `run_pocketflow_async` function encapsulates the PocketFlow execution. Requires `with app.app_context():` for extensions like `sse.publish` to work correctly.
*   **SSE (`Flask-SSE`):** Requires a running Redis server. Used for pushing status messages from the background thread/nodes to the connected frontend client via the `/stream` endpoint. Nodes use a helper `publish_sse` which ensures app context.
*   **Temporary Result Storage (`task_results` dict):** A simple global dictionary stores the final results keyed by `task_id`. This is **not suitable for production** (not persistent, potential race conditions if scaled, memory usage). Results are popped once retrieved by the GET `/` route.
*   **Session (`Flask-Session`):** Uses the filesystem backend to store `current_task_id` and `download_summary_raw` server-side, avoiding cookie size limits.
*   **Frontend JS (`index.html` `<script>`):** Handles drag-and-drop, client-side validation, SSE connection, live status updates, UI state changes (showing/hiding loader/results), view toggling (rendered/raw), and copy-to-clipboard functionality.
*   **Markdown (`Markdown` library):** Used in the GET `/` route to convert the raw summary text to HTML for display. Uses `| safe` filter in Jinja2 template (acceptable risk given source).

## 6. Optimization & Reliability Considerations

*   **Background Tasks:** Replace `threading` with a robust task queue like Celery or RQ for better scalability, error handling, and resource management in production.
*   **Result Storage:** Replace the global `task_results` dict with a persistent store (e.g., Redis, database) for reliability and scalability.
*   **SSE Backend:** Ensure Redis is properly configured and potentially scaled for production SSE usage.
*   **Temporary File Cleanup:** The current implementation relies on the OS or manual cleanup for the `temp_dir` created by `/process` if the app crashes mid-thread. A more robust solution would involve the background thread explicitly deleting the directory upon completion or error.
*   **Markdown Sanitization:** For increased security against potential (though unlikely) injection via LLM output, use a library like `bleach` to sanitize the HTML generated by the `Markdown` library before rendering.
*   **Error Handling:** More granular error reporting via SSE and better handling of thread failures could be implemented.
*   **Client-Side Validation:** While present, it can be bypassed; server-side validation remains crucial.
