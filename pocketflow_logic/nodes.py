# pocketflow_logic/nodes.py
import logging
from pocketflow import Node, BatchNode
# --- Import sse from Flask app context ---
# This is tricky; direct import isn't ideal.
# Better: Pass publisher function/object via shared store.
# Hackathon approach: Use global sse object (requires app context).
from flask_sse import sse
from flask import current_app # To get app context
# ---------------------------------------
from .utils import file_handler, llm_caller

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Helper to publish SSE events within app context
def publish_sse(task_id, event_data):
     try:
        # Check if we are already in an app context
        _ = current_app.name
        sse.publish(event_data, channel=task_id)
     except RuntimeError:
        # If not in context (e.g., raw thread), create one
        with current_app.app_context():
             sse.publish(event_data, channel=task_id)
     except Exception as e:
         # Log error if SSE publish fails
         log.error(f"Task {task_id}: Failed to publish SSE event {event_data.get('type')}: {e}")


class FileProcessorNode(BatchNode):
    """Processes individual files: reads content and gets initial summary."""
    def prep(self, shared):
        """Prepare list of file details and get task_id."""
        log.info("FileProcessorNode: Prep - Reading temp file details")
        self.task_id = shared.get('task_id', 'unknown_task') # Get task_id
        publish_sse(self.task_id, {"type": "status", "message": "Starting file processing..."})
        valid_files = [d for d in shared.get("temp_file_details", []) if d.get('temp_path')]
        log.info(f"FileProcessorNode: Found {len(valid_files)} valid files to process.")
        if not valid_files:
             publish_sse(self.task_id, {"type": "status", "message": "No valid files found to process."})
        return valid_files

    def exec(self, item):
        """Execute processing for a single file item."""
        original_name = item.get('original_name', 'unknown_file')
        temp_path = item.get('temp_path')
        task_id = self.task_id # Use stored task_id

        log.info(f"FileProcessorNode: Exec - Processing '{original_name}'")
        publish_sse(task_id, {"type": "status", "message": f"Processing file: '{original_name}'..."})

        if not temp_path:
            log.warning(f"FileProcessorNode: Skipped '{original_name}' due to missing temp_path.")
            publish_sse(task_id, {"type": "status", "message": f"Skipping '{original_name}': File not saved correctly."})
            return {'original_name': original_name, 'summary': 'Skipped: File not saved correctly'}

        publish_sse(task_id, {"type": "status", "message": f"Reading '{original_name}'..."})
        content = file_handler.read_file_content(temp_path)
        if content is None:
            log.error(f"FileProcessorNode: Failed to read content for '{original_name}'.")
            publish_sse(task_id, {"type": "status", "message": f"Error reading '{original_name}'."})
            return {'original_name': original_name, 'summary': 'Error: Could not read file content'}
        if not content.strip():
             log.warning(f"FileProcessorNode: File '{original_name}' is empty.")
             publish_sse(task_id, {"type": "status", "message": f"Skipping '{original_name}': File is empty."})
             return {'original_name': original_name, 'summary': 'Skipped: File is empty'}

        publish_sse(task_id, {"type": "status", "message": f"Requesting summary for '{original_name}'..."})
        summary = llm_caller.get_initial_summary(content)

        if isinstance(summary, str) and summary.startswith("Error:"):
             publish_sse(task_id, {"type": "status", "message": f"LLM Error for '{original_name}': {summary}"})
             log.warning(f"LLM Error during initial summary for '{original_name}': {summary}")
        else:
             publish_sse(task_id, {"type": "status", "message": f"Received summary for '{original_name}'."})
             log.info(f"FileProcessorNode: Summary received for '{original_name}'.")

        return {'original_name': original_name, 'summary': summary}

    def exec_fallback(self, prep_res, exc):
        """Fallback handler if exec fails after all retries for an item."""
        original_name = prep_res.get('original_name', 'unknown_file')
        error_type = type(exc).__name__
        task_id = self.task_id
        log.error(f"FileProcessorNode: Fallback triggered for '{original_name}' due to {error_type}: {exc}", exc_info=True)
        publish_sse(task_id, {"type": "status", "message": f"Error processing '{original_name}' after retries: {error_type}."})
        return {'original_name': original_name, 'summary': f'Error: Processing failed after retries ({error_type})'}

    def post(self, shared, prep_res, exec_res_list):
        """Store individual summaries (or errors) in the shared store."""
        log.info("FileProcessorNode: Post - Storing individual summaries")
        task_id = self.task_id
        shared["file_summaries"] = {}
        processed_count = 0
        for res in exec_res_list:
            if isinstance(res, dict) and 'original_name' in res and 'summary' in res:
                shared["file_summaries"][res['original_name']] = res['summary']
                processed_count += 1
            else:
                 log.error(f"FileProcessorNode: Received unexpected result format: {res}")
                 original_name = "unknown_file_malformed_result"
                 shared["file_summaries"][original_name] = "Error: Internal processing error (malformed result)"

        log.info(f"FileProcessorNode: Stored {len(shared['file_summaries'])} results.")
        publish_sse(task_id, {"type": "status", "message": f"Finished processing {processed_count} files."})
        return "default"

class CombineSummariesNode(Node):
    """Combines summaries, respecting the requested level."""
    def prep(self, shared):
        """Prepare combined text, failed files list, summary level, and get task_id."""
        log.info("CombineSummariesNode: Prep - Reading and filtering file summaries")
        self.task_id = shared.get('task_id', 'unknown_task') # Get task_id
        publish_sse(self.task_id, {"type": "status", "message": "Preparing final summary..."})

        summaries = shared.get("file_summaries", {})
        summary_level = shared.get("summary_level", "medium")
        log.info(f"CombineSummariesNode: Target summary level: {summary_level}")
        publish_sse(self.task_id, {"type": "status", "message": f"Target summary level: {summary_level}."})

        valid_summaries_text = []
        failed_files = []
        processed_files = list(summaries.keys())

        for name, summary in summaries.items():
            if isinstance(summary, str) and (summary.startswith("Error:") or summary.startswith("Skipped:")):
                failed_files.append(name)
            elif isinstance(summary, str) and summary.strip():
                valid_summaries_text.append(f"--- Summary for {name} ---\n{summary}")
            else:
                 failed_files.append(name)
                 log.warning(f"CombineSummariesNode: Treating summary for '{name}' as invalid/empty.")

        combined_text = "\n\n".join(valid_summaries_text)
        log.info(f"CombineSummariesNode: Prepared combined text ({len(combined_text)} chars) from {len(valid_summaries_text)} valid summaries. {len(failed_files)} files failed/skipped.")
        if not valid_summaries_text:
             publish_sse(self.task_id, {"type": "status", "message": "No valid summaries found to combine."})
        else:
             publish_sse(self.task_id, {"type": "status", "message": f"Combining {len(valid_summaries_text)} valid summaries."})

        return combined_text, failed_files, processed_files, summary_level

    def exec(self, inputs):
        """Execute the combination using the LLM with the specified level."""
        combined_text, failed_files, processed_files, summary_level = inputs
        task_id = self.task_id

        log.info(f"CombineSummariesNode: Exec - Requesting final '{summary_level}' combination from LLM.")

        if not combined_text:
             log.warning("CombineSummariesNode: No valid summaries available to combine.")
             publish_sse(task_id, {"type": "status", "message": "Skipping final combination: No valid summaries."})
             if processed_files:
                 fail_msg = f"Error: Could not generate summaries for any of the processed files: {', '.join(processed_files)}."
             else:
                 fail_msg = "Error: No files were processed or summaries generated."
             return fail_msg, failed_files

        publish_sse(task_id, {"type": "status", "message": f"Requesting final '{summary_level}' summary from LLM..."})
        final_summary = llm_caller.get_combined_summary(combined_text, level=summary_level)

        if isinstance(final_summary, str) and final_summary.startswith("Error:"):
            publish_sse(task_id, {"type": "status", "message": f"LLM Error during final combination: {final_summary}"})
            log.warning(f"LLM Error during final combination: {final_summary}")
        else:
            publish_sse(task_id, {"type": "status", "message": "Received final summary from LLM."})
            log.info("CombineSummariesNode: Final summary received.")

        return final_summary, failed_files

    def exec_fallback(self, prep_res, exc):
        """Fallback if combining summaries LLM call fails."""
        combined_text, failed_files, processed_files, summary_level = prep_res
        error_type = type(exc).__name__
        task_id = self.task_id
        log.error(f"CombineSummariesNode: Fallback triggered during final '{summary_level}' combination due to {error_type}: {exc}", exc_info=True)
        publish_sse(task_id, {"type": "status", "message": f"Error during final summary generation: {error_type}."})
        fallback_summary = f"Error: Failed to generate the final combined summary ({error_type})."
        return fallback_summary, failed_files

    def post(self, shared, prep_res, exec_res):
        """Store the final combined summary (or error) in the shared store."""
        # Note: This runs in the background thread. The result is stored
        # in the global task_results dict by run_pocketflow_async.
        # This post method still updates the 'shared' dict within the thread's context.
        log.info("CombineSummariesNode: Post - Storing final summary in thread context")
        task_id = self.task_id
        final_summary, failed_files = exec_res

        if failed_files:
            note = f"Note: The following files could not be summarized or were skipped: {', '.join(failed_files)}"
            if isinstance(final_summary, str) and not final_summary.startswith("Error:"):
                 final_summary += f"\n\n{note}"
            elif isinstance(final_summary, str) and final_summary.startswith("Error:"):
                 final_summary += f" ({note})"
            publish_sse(task_id, {"type": "status", "message": f"{len(failed_files)} file(s) failed or were skipped."})

        shared["final_summary"] = final_summary
        log.info("CombineSummariesNode: Final summary stored in thread context.")
        # Don't publish "Processing complete" here, let run_pocketflow_async handle final event.