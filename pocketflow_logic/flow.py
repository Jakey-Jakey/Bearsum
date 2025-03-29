# pocketflow_logic/flow.py
from pocketflow import Flow
from .nodes import FileProcessorNode, CombineSummariesNode

def create_summary_flow():
    """
    Creates and configures the PocketFlow for summarizing uploaded files.

    Returns:
        Flow: An instance of the configured PocketFlow.
    """
    # Instantiate nodes with desired configurations (e.g., retries)
    # Retry individual file processing twice with a 2-second wait on failure
    file_processor = FileProcessorNode(max_retries=3, wait=2)

    # Retry final combination once with a 2-second wait
    summary_combiner = CombineSummariesNode(max_retries=2, wait=2)

    # Define the flow: process files first, then combine summaries
    file_processor >> summary_combiner

    # Create the Flow instance starting with the file processor
    summary_flow = Flow(start=file_processor)

    return summary_flow