# Pocket Summarizer (Bearhacks Edition)

A web application built with Flask and PocketFlow that summarizes multiple uploaded text files (`.txt`, `.md`) using the Perplexity AI API. Features selectable summary lengths, live progress updates, and a modern UI.

## Features

*   **Multi-File Upload:** Upload multiple `.txt` and `.md` files simultaneously.
*   **Drag & Drop:** Modern drag-and-drop interface for file uploads (also includes traditional browse).
*   **AI Summarization:** Leverages the Perplexity AI API (`llama-3-sonar` models) for summarization.
*   **Selectable Summary Levels:** Choose between "Short", "Medium", or "Comprehensive" final summaries.
*   **Live Status Updates:** Real-time feedback on the summarization process using Server-Sent Events (SSE).
*   **Asynchronous Processing:** File processing happens in the background without blocking the UI.
*   **Dual Output Views:** View the summary as rendered Markdown or raw text.
*   **Output Actions:** Copy the raw summary text to the clipboard or download it as a `.txt` file.
*   **Themed UI:** Simple "Honey/Bear" theme.

## Tech Stack

*   **Backend:** Python 3, Flask
*   **Workflow:** PocketFlow (minimalist framework included)
*   **Real-time:** Flask-SSE (requires Redis)
*   **Sessions:** Flask-Session (filesystem backend)
*   **Background Tasks:** Python `threading`
*   **LLM:** Perplexity AI API (via `openai` library)
*   **Markdown:** `Markdown` library
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript

## Project Structure

```
pocket_summarizer/
├── app.py             # Flask application (routes, SSE, background task logic)
├── pocketflow/        # PocketFlow library code
│   └── __init__.py
├── pocketflow_logic/  # Core summarization workflow
│   ├── nodes.py         # PocketFlow Node definitions (FileProcessor, CombineSummaries)
│   ├── flow.py          # PocketFlow Flow definition (create_summary_flow)
│   └── utils/           # Helper modules
│       ├── file_handler.py # File saving, validation, reading
│       └── llm_caller.py   # Perplexity API interaction
├── static/            # CSS, JS, Images
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
    cd pocket_summarizer
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
    python3 app.py
    ```
4.  Open your web browser and navigate to `http://127.0.0.1:5000` (or the address provided).

**Note on Production:** The default Flask development server is not suitable for production. Use a production-ready WSGI server like Gunicorn: `gunicorn -w 4 app:app`. You would also likely want a more robust Redis setup and potentially replace `threading` with Celery/RQ.

## Limitations (Hackathon Scope)

*   **Result Storage:** Uses a simple in-memory Python dictionary (`task_results`) which is not persistent and not suitable for multiple concurrent users or production loads.
*   **Background Tasks:** Uses basic Python `threading`, which has limitations compared to dedicated task queues.
*   **Temporary Files:** Relies on OS/manual cleanup for temporary file directories if the application crashes mid-process.
*   **Markdown Sanitization:** Uses basic Markdown rendering; for enhanced security against potential LLM output issues, HTML sanitization (e.g., with `bleach`) could be added.
