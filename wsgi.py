# wsgi.py
import os
from app import app # Import the Flask app instance from your main app file

# Ensure the session directory exists if using filesystem (though we'll switch to Redis)
# This might still be needed during initial app import before config is fully applied
# Note: This directory is primarily for the *fallback* scenario if Redis fails.
session_dir = app.config.get("SESSION_FILE_DIR", "./flask_session")
if app.config.get("SESSION_TYPE") == "filesystem" and not os.path.exists(session_dir):
    try:
        os.makedirs(session_dir)
        app.logger.info(f"Created session directory from wsgi.py (for fallback): {session_dir}")
    except OSError as e:
        # Handle potential race conditions or permission errors if needed
        app.logger.warning(f"Could not create session directory from wsgi.py: {e}")

# The following block is NOT needed for uWSGI deployment but can be useful
# for direct execution testing (e.g., python wsgi.py).
# uWSGI will directly interact with the 'app' object imported above.
# if __name__ == "__main__":
#     app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
