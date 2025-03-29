# Pocket Summarizer & Storyteller (Bearhacks Edition)

A web application built with Flask that summarizes multiple uploaded text files (`.txt`, `.md`) using the Perplexity AI API, and *also* generates fictional "hackathon stories" based on recent GitHub commit activity. Features selectable summary lengths, live progress updates via SSE, and a polished, animated UI.

## Features

*   **Multi-File Upload:** Upload multiple `.txt` and `.md` files simultaneously for summarization.
*   **Drag & Drop:** Modern drag-and-drop interface for file uploads (also includes traditional browse).
*   **AI Summarization:** Leverages the Perplexity AI API (`llama-3-sonar` models) for summarization.
*   **Selectable Summary Levels:** Choose between "Short", "Medium", or "Comprehensive" final summaries.
*   **GitHub Story Generator:** Paste a public GitHub repository URL to generate a short, fictional narrative inspired by recent commit activity.
*   **Live Status Updates:** Real-time feedback on both summarization and story generation processes using Server-Sent Events (SSE).
*   **Asynchronous Processing:** File processing and story generation happen in the background without blocking the UI.
*   **Dual Summary Views:** View the summary as rendered Markdown or raw text.
*   **Output Actions:** Copy the raw summary text to the clipboard or download it as a `.txt` file. Copy the generated story text.
*   **Polished UI:** Refined "Honey/Bear" theme with subtle animations and transitions for a modern user experience.

## Tech Stack

*   **Backend:** Python 3, Flask
*   **Real-time:** Flask-SSE (requires Redis)
*   **Sessions:** Flask-Session (filesystem backend)
*   **Background Tasks:** Python `threading`
*   **LLM:** Perplexity AI API (via `openai` library)
*   **GitHub API:** `requests` library
*   **Markdown:** `Markdown` library
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript

## Project Structure

```
pocket_summarizer/
├── app.py             # Flask application (routes, SSE, background task logic)
├── pocketflow/        # PocketFlow library code 
│   └── __init__.py
├── pocketflow_logic/  # Core application logic
│   ├── __init__.py
│   ├── flow.py          # PocketFlow Flow definition (if used)
│   ├── nodes.py         # PocketFlow Node definitions (if used)
│   └── utils/           # Helper modules
│       ├── __init__.py
│       ├── file_handler.py # File saving, validation, reading
│       ├── llm_caller.py   # Perplexity API interaction
│       └── github_utils.py # GitHub API interaction  <-- NEW
├── static/            # CSS, JS
│   ├── script.js        # (Note: JS is embedded in index.html in current version)
│   └── style.css
├── templates/         # HTML templates
│   └── index.html
├── requirements.txt   # Python dependencies
├── .env.example       # Environment variable template
└── .gitignore
```

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.8+
    *   `pip` and `venv`
    *   **Redis Server:** Required for Flask-SSE live updates. Install locally or use Docker.
        *   *Docker (Recommended):* `docker run -d -p 6379:6379 --name pocket-summarizer-redis redis`
        *   *Windows:* Download from [microsoftarchive/redis](https://github.com/microsoftarchive/redis/releases) and run `redis-server.exe`.
        *   *macOS:* `brew install redis && brew services start redis`
        *   *Linux:* `sudo apt update && sudo apt install redis-server`

2.  **Clone the Repository:**
    ```bash
    git clone <repository-url>
    cd pocket-summarizer # Or your project directory name
    ```

3.  **Create and Activate Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate    # Windows
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: This now includes the `requests` library)*

5.  **Configure Environment Variables:**
    *   Copy `.env.example` to `.env`: `cp .env.example .env`
    *   Edit the `.env` file:
        *   Add your **Perplexity AI API Key** to `PERPLEXITY_API_KEY`. Get one from [Perplexity Labs](https://docs.perplexity.ai/).
        *   Generate a strong, random **Flask Secret Key** and add it to `FLASK_SECRET_KEY`. You can generate one using:
            ```bash
            python -c 'import secrets; print(secrets.token_hex(24))'
            ```
        *   (Optional) If your Redis server is not running on `redis://localhost:6379/0`, set the correct `REDIS_URL`.

## Running the Application

1.  **Ensure Redis is running.**
2.  **Activate your virtual environment** (`source venv/bin/activate`).
3.  **Start the Flask Development Server:**
    ```bash
    flask run
    # OR
    python app.py # Use python, not python3 if python maps to Python 3
    ```
4.  Open your web browser and navigate to `http://127.0.0.1:5000` (or the address provided).

**Note on Production:** The default Flask development server is not suitable for production. Use a production-ready WSGI server like Gunicorn: `gunicorn -w 4 app:app`. You would also likely want a more robust Redis setup and potentially replace `threading` with Celery/RQ.

## Using the Features

*   **Summarizer:**
    1.  Drag & drop `.txt` or `.md` files onto the designated area, or use the "Browse Files" button.
    2.  Select the desired summary detail level ("Short", "Medium", "Comprehensive").
    3.  Click "Summarize Files".
    4.  Wait for the processing indicator and live status updates.
    5.  View the result in Rendered or Raw Text format. Use the Copy/Download buttons as needed.
*   **Story Generator:**
    1.  Paste the full HTTPS URL of a **public** GitHub repository into the "GitHub Repository URL" field (e.g., `https://github.com/your-username/your-repo`).
    2.  Click "Generate Story".
    3.  Wait for the processing indicator and live status updates (fetching commits, generating story).
    4.  View the generated fictional story. Use the Copy button if desired.

## Limitations (Hackathon Scope)

*   **Result Storage:** Uses a simple in-memory Python dictionary (`task_results`) which is not persistent and not suitable for multiple concurrent users or production loads. Results are lost on server restart.
*   **Background Tasks:** Uses basic Python `threading`, which has limitations compared to dedicated task queues (e.g., error handling, scalability).
*   **Temporary File Cleanup:** Summarizer relies on the background thread for temp file cleanup; if the app crashes mid-process, files might remain. Story generator does not create temp files.
*   **GitHub API Limits:** Story generator uses unauthenticated requests to the GitHub API, which are subject to stricter rate limits. Heavy use may result in temporary blocks. Only public repositories are supported.
*   **Markdown Sanitization:** Uses basic Markdown rendering; for enhanced security against potential LLM output issues, HTML sanitization (e.g., with `bleach`) could be added.
