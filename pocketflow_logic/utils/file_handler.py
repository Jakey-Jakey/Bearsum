# pocketflow_logic/utils/file_handler.py
import os
import uuid
from werkzeug.utils import secure_filename
import logging

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'txt', 'md'}
MAX_FILE_SIZE_MB = 1
MAX_FILES = 5

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_files(files, temp_dir):
    """
    Saves uploaded files securely to a temporary directory.

    Args:
        files (list): List of FileStorage objects from Flask request.
        temp_dir (str): Path to the temporary directory for this request.

    Returns:
        list: A list of dictionaries, each containing details of a saved file:
              [{'original_name': str, 'temp_path': str, 'size': int, 'error': str/None}, ...]
              Includes an 'error' key if validation fails for a file.
        list: A list of error messages encountered during validation/saving.
    """
    saved_file_details = []
    errors = []
    file_count = 0

    for file in files:
        # Check if we have already processed the maximum allowed number of files
        if file_count >= MAX_FILES:
            if file and file.filename: # Check if there are more files attempted beyond the limit
                 errors.append(f"Exceeded maximum number of files ({MAX_FILES}). File '{file.filename}' and subsequent files ignored.")
            else: # Generic message if no more filenames are available
                 errors.append(f"Exceeded maximum number of files ({MAX_FILES}). Additional files ignored.")
            break # Stop processing more files

        if file and file.filename:
            original_filename = file.filename
            if allowed_file(original_filename):
                # Check file size (read content once to get size, potentially inefficient for huge files, but ok for 1MB limit)
                # Use try-except for robustness, e.g., if file object is weird
                try:
                    file.seek(0, os.SEEK_END)
                    file_size = file.tell()
                    file.seek(0) # Reset cursor
                except Exception as e:
                    log.error(f"Could not determine size for file '{original_filename}': {e}")
                    errors.append(f"Could not determine size for file '{original_filename}'.")
                    saved_file_details.append({'original_name': original_filename, 'temp_path': None, 'size': -1, 'error': 'Could not determine size'})
                    continue # Skip this file

                if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    log.warning(f"File '{original_filename}' ({file_size} bytes) exceeds size limit ({MAX_FILE_SIZE_MB}MB).")
                    errors.append(f"File '{original_filename}' exceeds size limit ({MAX_FILE_SIZE_MB}MB).")
                    saved_file_details.append({'original_name': original_filename, 'temp_path': None, 'size': file_size, 'error': 'Exceeds size limit'})
                    continue # Skip saving this file

                # Sanitize and create unique filename
                secure_name = secure_filename(original_filename)
                unique_filename = f"{uuid.uuid4()}_{secure_name}"
                temp_path = os.path.join(temp_dir, unique_filename)

                try:
                    file.save(temp_path)
                    log.info(f"Saved file '{original_filename}' to '{temp_path}' ({file_size} bytes).")
                    saved_file_details.append({'original_name': original_filename, 'temp_path': temp_path, 'size': file_size, 'error': None})
                    file_count += 1 # Increment count only for successfully saved files
                except Exception as e:
                    log.error(f"Could not save file '{original_filename}' to '{temp_path}': {e}", exc_info=True)
                    errors.append(f"Could not save file '{original_filename}'.")
                    saved_file_details.append({'original_name': original_filename, 'temp_path': None, 'size': file_size, 'error': f'Failed to save'})

            else:
                log.warning(f"File type not allowed for '{original_filename}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
                errors.append(f"File type not allowed for '{original_filename}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
                saved_file_details.append({'original_name': original_filename, 'temp_path': None, 'size': 0, 'error': 'File type not allowed'})
        elif file and not file.filename:
             # This case might happen if an empty file input is submitted
             log.debug("Ignoring empty file input.")
             pass # Ignore empty file inputs silently

    # Add error if no valid files were ultimately saved AND there were no other specific errors reported
    if file_count == 0 and not errors:
         errors.append("No valid files were uploaded or saved.")

    return saved_file_details, errors

def read_file_content(filepath):
    """Reads content from a given file path."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        log.error(f"Error reading file {filepath}: {e}", exc_info=True)
        return None # Return None to indicate failure