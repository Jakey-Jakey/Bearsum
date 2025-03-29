// static/script.js
document.addEventListener('DOMContentLoaded', function() {
    // --- Element References ---
    const uploadForm = document.getElementById('upload-form');
    const submitButton = document.getElementById('submit-button');
    const processingIndicator = document.getElementById('processing-indicator');
    const resultsArea = document.getElementById('results-area');
    const latestStatusElement = document.getElementById('latest-status');
    const copyButton = document.getElementById('copy-button');
    const summaryRawTextElement = document.getElementById('summary-text-raw');
    const viewToggles = document.querySelectorAll('.view-toggle .btn-toggle');
    const renderedView = document.getElementById('summary-rendered');
    const rawView = document.getElementById('summary-raw');
    const fileInput = document.getElementById('files'); // The hidden file input
    const dropZone = document.getElementById('drop-zone');
    const fileListDisplay = document.getElementById('file-list-display');
    const browseFilesLink = document.getElementById('browse-files-link'); // Link to trigger hidden input

    // --- Config (Get from data attributes or global scope if needed) ---
    // Example: Assuming max files/size are available if needed for JS validation
    const MAX_FILES = parseInt(uploadForm?.dataset.maxFiles || '5');
    const MAX_FILE_SIZE_MB = parseInt(uploadForm?.dataset.maxFileSizeMb || '1');
    const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
    const ALLOWED_EXTENSIONS = ['txt', 'md'];

    // --- Initial State from Flask ---
    const isProcessing = uploadForm?.dataset.isProcessing === 'true'; // Get from data attribute
    const taskId = uploadForm?.dataset.taskId; // Get from data attribute
    let eventSource = null;

    // --- Helper: Update File List Display ---
    function updateFileList(files) {
        if (!fileListDisplay) return;
        fileListDisplay.innerHTML = ''; // Clear previous list
        if (!files || files.length === 0) {
            fileListDisplay.innerHTML = '<p><em>No files selected. Drag & drop or browse.</em></p>';
            return;
        }

        const list = document.createElement('ul');
        Array.from(files).forEach(file => {
            const li = document.createElement('li');
            // Basic validation display
            let errorMsg = '';
            if (file.size > MAX_FILE_SIZE_BYTES) {
                errorMsg = ` <span class="file-error">(Too large: > ${MAX_FILE_SIZE_MB}MB)</span>`;
            } else if (!ALLOWED_EXTENSIONS.includes(file.name.split('.').pop()?.toLowerCase() || '')) {
                 errorMsg = ` <span class="file-error">(Invalid type)</span>`;
            }

            li.innerHTML = `${file.name} <span class="file-size">(${(file.size / 1024).toFixed(1)} KB)</span>${errorMsg}`;
            if (errorMsg) li.classList.add('has-error'); // Add class if error exists
            list.appendChild(li);
        });
        fileListDisplay.appendChild(list);

        // Check overall file count
        if (files.length > MAX_FILES) {
             const errorLi = document.createElement('li');
             errorLi.innerHTML = `<span class="file-error">Error: Too many files selected (max ${MAX_FILES}).</span>`;
             errorLi.classList.add('has-error');
             list.appendChild(errorLi);
        }
    }

     // --- Helper: Validate Files ---
     function validateFiles(files) {
        let valid = true;
        if (files.length > MAX_FILES) {
            valid = false; // Too many files overall
        }
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE_BYTES || !ALLOWED_EXTENSIONS.includes(file.name.split('.').pop()?.toLowerCase() || '')) {
                valid = false; // Individual file error
                break;
            }
        }
        return valid;
    }


    // --- Drag and Drop Logic ---
    if (dropZone && fileInput && fileListDisplay) {
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false); // Prevent browser opening file
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        // Highlight drop zone when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        function highlight(e) {
            dropZone.classList.add('dragover');
        }

        function unhighlight(e) {
            dropZone.classList.remove('dragover');
        }

        // Handle dropped files
        dropZone.addEventListener('drop', handleDrop, false);

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;

            // Assign dropped files to the hidden file input
            try {
                 fileInput.files = files;
                 updateFileList(files); // Update UI
            } catch (err) {
                 console.error("Error setting file input files:", err);
                 alert("There was an error processing the dropped files. Please try the 'browse' link instead.");
            }
        }

        // Trigger hidden file input when drop zone or link is clicked
        if (browseFilesLink) {
             browseFilesLink.addEventListener('click', (e) => {
                 e.preventDefault(); // Prevent link navigation if it's an <a>
                 fileInput.click();
             });
        }
         // Optionally make the whole dropzone clickable
         dropZone.addEventListener('click', () => {
             // Avoid triggering if the click was on the link itself
             if (!browseFilesLink || !event.target.isSameNode(browseFilesLink)) {
                fileInput.click();
             }
         });


        // Update file list when files are selected via the hidden input
        fileInput.addEventListener('change', function() {
            updateFileList(this.files);
        });

        // Initial file list update on page load (if any files somehow persisted - unlikely)
        updateFileList(fileInput.files);
    }


    // --- SSE Connection Function ---
    function connectSSE(taskId) {
        // ... (SSE connection logic remains the same as Response #34) ...
        if (!taskId || !processingIndicator || !resultsArea || !latestStatusElement) return;
        console.log(`Connecting to SSE stream for task: ${taskId}`);
        eventSource = new EventSource(`/stream?channel=${taskId}`);
        eventSource.onopen = function() { /* ... */ };
        eventSource.onmessage = function(event) { /* ... */ };
        eventSource.onerror = function(err) { /* ... */ };
    }

    // --- Initial Page Load Logic ---
    if (isProcessing && taskId) {
        connectSSE(taskId);
    } else {
        if (processingIndicator) processingIndicator.classList.add('hidden');
    }

    // --- Form Submission Logic ---
    if (uploadForm && processingIndicator && resultsArea && fileInput && submitButton) {
        uploadForm.addEventListener('submit', function(event) {
            // --- Client-side Validation ---
            const files = fileInput.files;
            if (files.length === 0) {
                alert("Please select or drop files to upload.");
                event.preventDefault();
                return;
            }
            if (!validateFiles(files)) {
                 alert("Please fix the errors in the selected files (check type, size, and count) before submitting.");
                 event.preventDefault();
                 return;
            }
            // --- End Validation ---

            processingIndicator.classList.remove('hidden');
            resultsArea.classList.add('hidden');
            submitButton.disabled = true;
            if (latestStatusElement) latestStatusElement.textContent = 'Submitting files...';
        });
    }

    // --- View Toggling Logic ---
    // ... (remains the same as Response #34) ...
    if (viewToggles.length > 0 && renderedView && rawView) { /* ... */ }

    // --- Copy Button Logic ---
    // ... (remains the same as Response #34) ...
    if (copyButton && summaryRawTextElement) { /* ... */ }

}); // End DOMContentLoaded