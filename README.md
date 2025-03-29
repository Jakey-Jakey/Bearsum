# 🐻 Pocket Summarizer

A polished web application built with Flask that offers powerful AI-powered tools in one interface:

**File Summarizer** - Upload multiple text files and get a concise AI-generated summary

Both tools leverage the Perplexity AI API (using Llama 3 models) to generate high-quality, readable content.

![Screenshot of application](https://placeholder-for-your-screenshot.com)

## ✨ Features

### Core Functionality
- **Multi-file summarization** of `.txt` and `.md` files with adjustable detail levels
- **GitHub commit-to-story generation** that turns code commits into creative narratives
- **Live progress updates** during processing via Server-Sent Events
- **Asynchronous processing** that keeps the UI responsive

### User Experience
- **Modern drag-and-drop interface** for file uploads
- **Real-time status updates** during processing
- **Polished animations and transitions** throughout the interface
- **Responsive design** with careful attention to interactive details
- **Task-focused workflow** that adapts the interface based on the current state
- **Dark mode support** for comfortable viewing in different environments

### Technical Highlights
- **Flask backend** with Redis-powered SSE for real-time updates
- **Vanilla JavaScript** frontend (no framework dependencies)
- **Modular architecture** for easy maintenance and extension
- **Comprehensive error handling** for a robust user experience

## 🚀 Setup and Installation

### Prerequisites
- Python 3.8+
- Redis server (for SSE real-time updates)
- Perplexity AI API key

### Installation

1. **Clone the repository**
```bash
   git clone https://github.com/yourusername/pocket-summarizer.git
   cd pocket-summarizer
```

2. **Set up a virtual environment**
```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```
   pip install -r requirements.txt
```

4. **Redis Setup**
   - **Docker (recommended):**
  ```
     docker run -d -p 6379:6379 --name pocket-summarizer-redis redis
```
   - **Windows:** Download from [microsoftarchive/redis](https://github.com/microsoftarchive/redis/releases)
   - **macOS:** `brew install redis && brew services start redis`
   - **Linux:** `sudo apt update && sudo apt install redis-server`

5. **Environment Configuration**
   - Copy `.env.example` to `.env`
   - Add your Perplexity API key to `PERPLEXITY_API_KEY`
   - Generate a Flask secret key: `python -c 'import secrets; print(secrets.token_hex(24))'`
   - Add this key to `FLASK_SECRET_KEY`

## 🎮 Usage

### Starting the Application
```bash
flask run
# OR
python app.py
```

Navigate to `http://127.0.0.1:5000` in your browser.

### Using the File Summarizer
1. Drag & drop text files onto the upload area (or click to browse)
2. Select your desired summary length (Short, Medium, or Comprehensive)
3. Click "Summarize Files"
4. Watch the progress updates
5. View your summary in rendered or raw format
6. Copy or download the result as needed

## 🛠️ Project Structure

```
pocket_summarizer/
├── app.py             # Flask application (routes, SSE, background task logic)
├── static/            # CSS, JS
│   ├── script.js      # JavaScript functionality
│   └── style.css      # Styling and animations
├── templates/         # HTML templates
│   └── index.html     # Main application interface
├── pocketflow/        # PocketFlow library code 
├── pocketflow_logic/  # Core application logic
│   ├── flow.py        # PocketFlow Flow definition
│   ├── nodes.py       # PocketFlow Node definitions
│   └── utils/         # Helper modules
│       ├── file_handler.py  # File operations
│       ├── llm_caller.py    # Perplexity API interactions
│       └── github_utils.py  # GitHub API interactions
├── requirements.txt   # Python dependencies
└── .env.example       # Environment variable template
```

## 🧑‍💻 Development Notes

- **For Production:** Replace the Flask development server with Gunicorn
- **Error Handling:** The application includes comprehensive error handling for API failures, invalid inputs, and other edge cases
- **Session Management:** Uses Flask-Session with filesystem backend
- **Background Tasks:** Uses Python's threading module (consider Celery for production)

## 🌟 Acknowledgements

- Built during the Bearhacks hackathon
- Uses the [Perplexity AI API](https://docs.perplexity.ai/)
- Uses [Pocketflow](https://github.com/The-Pocket/PocketFlow/)
