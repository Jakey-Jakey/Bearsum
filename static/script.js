// static/script.js
document.addEventListener('DOMContentLoaded', function() {
    // --- Element References ---
    const summaryForm = document.getElementById('upload-form');
    const storyForm = document.getElementById('story-form');
    const submitButtonSummary = document.getElementById('submit-button-summary');
    const submitButtonStory = document.getElementById('submit-button-story');
    const processingIndicatorWrapper = document.getElementById('processing-indicator-wrapper');
    const processingTaskName = document.getElementById('processing-task-name');
    const resultsContainerWrapper = document.getElementById('results-container-wrapper');
    const latestStatusElement = document.getElementById('latest-status');
    const summaryViewWrapper = document.getElementById('summary-view-wrapper');
    const summaryRenderedView = document.getElementById('summary-rendered');
    const summaryRawView = document.getElementById('summary-raw');
    const summaryRawTextElement = document.getElementById('summary-text-raw');
    const summaryViewToggles = document.querySelectorAll('.summary-section .view-toggle .btn-toggle');
    const copyButtonSummary = document.getElementById('copy-button-summary');
    const storyRenderedView = document.getElementById('story-rendered');
    const copyButtonStory = document.getElementById('copy-button-story');
    const fileInput = document.getElementById('files');
    const dropZone = document.getElementById('drop-zone');
    const fileListDisplay = document.getElementById('file-list-display');
    const browseFilesLink = document.getElementById('browse-files-link');
    const githubUrlInput = document.getElementById('github_url');
    const tabButtons = document.querySelectorAll('.tab-button'); // For new tab functionality
    const newTaskButton = document.getElementById('new-task-button');
    const bearToggle = document.getElementById('bear-toggle'); // Easter egg bear button
	
	window.addEventListener('keydown', function(e) {
    // Reset tooltip when holding 'T' key and refreshing the page
    if (e.key.toLowerCase() === 't') {
        localStorage.removeItem('bearTooltipSeen');
        // Add a flag to show that we're ready to reset
        document.body.classList.add('tooltip-reset-ready');
        // Show a temporary indicator
        const resetIndicator = document.createElement('div');
        resetIndicator.className = 'tooltip-reset-indicator';
        resetIndicator.textContent = 'Bear tooltip will reappear on refresh!';
        document.body.appendChild(resetIndicator);
        setTimeout(() => {
            resetIndicator.remove();
        }, 2000);
    }
});

    // --- Config ---
    const MAX_FILES = parseInt(summaryForm?.dataset.maxFiles || '5');
    const MAX_FILE_SIZE_MB = parseInt(summaryForm?.dataset.maxFileSizeMb || '1');
    const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
    const ALLOWED_EXTENSIONS = ['txt', 'md'];

    // --- Initial State from Flask ---
    // Convert Flask variables to JS variables
    const isProcessingSummary = JSON.parse(document.getElementById('is-processing-summary')?.value || 'false');
    const isProcessingStory = JSON.parse(document.getElementById('is-processing-story')?.value || 'false');
    const summaryTaskId = document.getElementById('summary-task-id')?.value || '';
    const storyTaskId = document.getElementById('story-task-id')?.value || '';
    let activeTaskId = isProcessingSummary ? summaryTaskId : (isProcessingStory ? storyTaskId : null);
    let activeTaskType = isProcessingSummary ? 'summary' : (isProcessingStory ? 'story' : null);
    let eventSource = null;

    console.log("Initial State:", { isProcessingSummary, isProcessingStory, summaryTaskId, storyTaskId, activeTaskId, activeTaskType });

    // --- Easter Egg: Bear Toggle for Storyteller Mode ---
    if (bearToggle) {
        bearToggle.addEventListener('click', function() {
            // Check which mode we're in
            const isInStoryteller = document.body.classList.contains('storyteller-mode');
            
            if (!isInStoryteller) {
                // Switch to storyteller mode
                document.body.classList.add('storyteller-mode');
                document.body.classList.add('dark-theme'); // Apply dark theme
                switchTab('storyteller-tab');
                
                // Animate the bear
                bearToggle.classList.add('bear-activated');
                setTimeout(() => {
                    bearToggle.classList.remove('bear-activated');
                }, 1000);
            } else {
                // Switch back to summarizer mode
                document.body.classList.remove('storyteller-mode');
                document.body.classList.remove('dark-theme'); // Remove dark theme
                switchTab('summarizer-tab');
                
                // Animate the bear
                bearToggle.classList.add('bear-deactivated');
                setTimeout(() => {
                    bearToggle.classList.remove('bear-deactivated');
                }, 1000);
            }
            
            // Mark that the user has seen the tooltip
            document.body.classList.add('bear-tooltip-seen');
            localStorage.setItem('bearTooltipSeen', 'true');
            localStorage.setItem('storytellerMode', !isInStoryteller);
        });
        
        // Check for saved preferences
        if (localStorage.getItem('storytellerMode') === 'true') {
            document.body.classList.add('storyteller-mode');
            document.body.classList.add('dark-theme');
            // We'll set the tab in the tab initialization code
        }
        
        if (localStorage.getItem('bearTooltipSeen') === 'true') {
            document.body.classList.add('bear-tooltip-seen');
        }
    }

    // --- Tab Functionality ---
    function switchTab(tabId) {
        // Get current active tab
        const currentActiveTab = document.querySelector('.tab-content:not(.hidden)');
        const targetTab = document.getElementById(tabId);
        
        if (!targetTab) return;
        
        // If no tab is currently shown or the same tab is clicked, show immediately
        if (!currentActiveTab || currentActiveTab.id === tabId) {
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.add('hidden');
            });
            targetTab.classList.remove('hidden');
        } else {
            // Animate current tab out
            currentActiveTab.classList.add('tab-fade-out');
            
            // After fadeout, hide current and show target
            setTimeout(() => {
                currentActiveTab.classList.add('hidden');
                currentActiveTab.classList.remove('tab-fade-out');
                
                // Show target tab with animation
                targetTab.classList.remove('hidden');
                targetTab.classList.add('tab-fade-in');
                
                // Remove animation class after it completes
                setTimeout(() => {
                    targetTab.classList.remove('tab-fade-in');
                }, 300);
            }, 300);
        }
        
        // Update active state for tab buttons
        document.querySelectorAll('.tab-button').forEach(button => {
            if (button.getAttribute('data-tab') === tabId) {
                button.classList.add('active');
            } else {
                button.classList.remove('active');
            }
        });
        
        // Store active tab in localStorage
        localStorage.setItem('activeTab', tabId);
    }

    // Initialize tabs
    if (tabButtons && tabButtons.length > 0) {
        tabButtons.forEach(button => {
            button.addEventListener('click', function() {
                const tabId = this.getAttribute('data-tab');
                
                // If switching to storyteller, apply dark theme
                if (tabId === 'storyteller-tab') {
                    document.body.classList.add('dark-theme');
                    document.body.classList.add('storyteller-mode');
                } else {
                    document.body.classList.remove('dark-theme');
                    document.body.classList.remove('storyteller-mode');
                }
                
                switchTab(tabId);
            });
        });
        
        // Restore active tab from localStorage or default to summarizer
        const activeTab = localStorage.getItem('activeTab') || 'summarizer-tab';
        
        // If we have storyteller mode preference, override tab selection
        if (localStorage.getItem('storytellerMode') === 'true') {
            switchTab('storyteller-tab');
        } else {
            switchTab(activeTab);
        }
    }

    // --- Helper: Update File List Display ---
    function updateFileList(files) {
        if (!fileListDisplay) return;
        fileListDisplay.innerHTML = '';
        if (!files || files.length === 0) {
            fileListDisplay.innerHTML = '<p><em>No files selected.</em></p>';
            return;
        }

        const list = document.createElement('ul');
        Array.from(files).forEach((file, index) => {
            const li = document.createElement('li');
            let errorMsg = '';
            const fileExt = file.name.split('.').pop()?.toLowerCase() || '';
            if (file.size > MAX_FILE_SIZE_BYTES) {
                errorMsg = ` <span class="file-error">(Too large: > ${MAX_FILE_SIZE_MB}MB)</span>`;
            } else if (!ALLOWED_EXTENSIONS.includes(fileExt)) {
                errorMsg = ` <span class="file-error">(Invalid type)</span>`;
            }
            li.innerHTML = `${file.name} <span class="file-size">(${(file.size / 1024).toFixed(1)} KB)</span>${errorMsg}`;
            if (errorMsg) li.classList.add('has-error');
            li.style.animationDelay = `${index * 0.05}s`;
            list.appendChild(li);
        });
        
        if (files.length > MAX_FILES) {
            const errorLi = document.createElement('li');
            errorLi.innerHTML = `<span class="file-error">Error: Too many files selected (max ${MAX_FILES}).</span>`;
            errorLi.classList.add('has-error');
            errorLi.style.animationDelay = `${files.length * 0.05}s`;
            list.appendChild(errorLi);
        }
        
        fileListDisplay.appendChild(list);
    }

    // --- Helper: Validate Files ---
    function validateFiles(files) {
        let valid = true;
        if (!files || files.length === 0) {
            valid = false;
        } else if (files.length > MAX_FILES) {
            valid = false;
        } else {
            for (const file of files) {
                const fileExt = file.name.split('.').pop()?.toLowerCase() || '';
                if (file.size > MAX_FILE_SIZE_BYTES || !ALLOWED_EXTENSIONS.includes(fileExt)) {
                    valid = false;
                    break;
                }
            }
        }
        return valid;
    }

    // --- Helper: Show/Hide Wrappers ---
    function showElementWrapper(wrapper) {
        if (wrapper) {
            console.log("Showing wrapper:", wrapper.id);
            wrapper.classList.remove('hidden');
        } else {
            console.error("Attempted to show null wrapper");
        }
    }
    
    function hideElementWrapper(wrapper) {
        if (wrapper) {
            console.log("Hiding wrapper:", wrapper.id);
            wrapper.classList.add('hidden');
        } else {
            console.error("Attempted to hide null wrapper");
        }
    }

    // --- Helper: Set View Wrapper Height ---
    function setViewWrapperHeight(wrapper, viewSelector = ':not(.hidden)') {
        if (!wrapper) return;
        const activeView = wrapper.querySelector(viewSelector);
        if (activeView) {
            wrapper.style.minHeight = `${activeView.scrollHeight + 10}px`;
        } else {
            wrapper.style.minHeight = '100px';
        }
    }

    // --- Helper: Reset Forms ---
    function resetForms() {
        if (summaryForm) summaryForm.reset();
        if (storyForm) storyForm.reset();
        if (fileInput && fileListDisplay) {
            fileInput.value = '';
            updateFileList(null);
        }
    }

    // --- Helper: Hide Forms Show Results ---
    function hideFormsShowResults() {
        const forms = document.querySelectorAll('.input-form-section');
        forms.forEach(form => {
            form.classList.add('hidden');
        });
        
        if (newTaskButton) {
            newTaskButton.classList.remove('hidden');
        }
    }

    // --- Helper: Show Forms Hide Results ---
    function showFormsHideResults() {
        const forms = document.querySelectorAll('.input-form-section');
        forms.forEach(form => {
            form.classList.remove('hidden');
        });
        
        if (newTaskButton) {
            newTaskButton.classList.add('hidden');
        }
        
        hideElementWrapper(resultsContainerWrapper);
    }

    // New Task Button Functionality
    if (newTaskButton) {
        newTaskButton.addEventListener('click', function() {
            resetForms();
            showFormsHideResults();
        });
    }

    // --- Drag and Drop Helpers ---
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        dropZone?.classList.add('dragover');
    }
    
    function unhighlight(e) {
        dropZone?.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        try {
            fileInput.files = files;
            updateFileList(files);
        } catch (err) {
            console.error("Error setting file input files:", err);
            alert("There was an error processing the dropped files. Please try the 'browse' link instead.");
            updateFileList(null);
        }
    }

    // --- Drag and Drop Logic ---
    if (dropZone && fileInput && fileListDisplay) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        dropZone.addEventListener('drop', handleDrop, false);
        
        if (browseFilesLink) {
            browseFilesLink.addEventListener('click', (e) => {
                e.preventDefault();
                fileInput.click();
            });
        }
        
        dropZone.addEventListener('click', (e) => {
            if (!browseFilesLink || !e.target.isSameNode(browseFilesLink)) {
                fileInput.click();
            }
        });

        fileInput.addEventListener('change', function() {
            updateFileList(this.files);
        });

        updateFileList(fileInput.files);
    }

    // --- SSE Connection Function ---
    function connectSSE(taskId, taskType) {
        if (!taskId || !processingIndicatorWrapper || !resultsContainerWrapper || !latestStatusElement) return;
        
        if (eventSource) {
            console.log("Closing existing SSE connection.");
            eventSource.close();
            eventSource = null;
        }

        console.log(`Connecting to SSE stream for ${taskType} task: ${taskId}`);
        eventSource = new EventSource(`/stream?channel=${taskId}`);
        activeTaskId = taskId;
        activeTaskType = taskType;

        eventSource.onopen = function() {
            console.log("SSE connection opened.");
            showElementWrapper(processingIndicatorWrapper);
            hideFormsShowResults(); // Hide forms when processing starts
            
            if (processingTaskName) {
                processingTaskName.textContent = taskType === 'summary' ? 'Summarizing Files...' : 'Generating Story...';
            }
            
            latestStatusElement.textContent = 'Connection established... waiting for updates.';
            latestStatusElement.classList.remove('animate-new');
            latestStatusElement.style.color = '';
            
            if (submitButtonSummary) submitButtonSummary.disabled = true;
            if (submitButtonStory) submitButtonStory.disabled = true;
        };

        eventSource.onmessage = function(event) {
            console.log("SSE message received:", event.data);
            console.log("Target URL:", event.target.url, "Active Task ID:", activeTaskId);
            
            try {
                const data = JSON.parse(event.data);
                // Ensure message is for the active task
                if (activeTaskId && event.target.url.includes(activeTaskId)) {
                    if (data.type === 'status' && latestStatusElement) {
                        console.log("Updating status:", data.message);
                        latestStatusElement.textContent = data.message;
                        latestStatusElement.classList.remove('animate-new');
                        void latestStatusElement.offsetWidth;
                        latestStatusElement.classList.add('animate-new');
                    }
                    
                    if (data.type === 'completed' || data.type === 'error') {
                        console.log(`Task ${activeTaskId} ${data.type}. Closing SSE and reloading.`);
                        if (eventSource) {
                            eventSource.close();
                            eventSource = null;
                        }
                        
                        latestStatusElement.textContent = `${taskType.charAt(0).toUpperCase() + taskType.slice(1)} ${data.type}. Reloading results...`;
                        // Clear active task info *before* reload
                        activeTaskId = null;
                        activeTaskType = null;
                        
                        setTimeout(() => {
                            console.log("Reloading page now.");
                            window.location.reload();
                        }, 1200);
                    }
                } else {
                    console.warn(`Ignoring SSE message - Active Task ID mismatch or null. Active: ${activeTaskId}, Target URL: ${event.target.url}`);
                }
            } catch (e) {
                console.error("Failed to parse SSE message or update UI:", e);
                if (latestStatusElement) latestStatusElement.textContent = "Error processing status update.";
            }
        };

        eventSource.onerror = function(err) {
            console.error("SSE connection error:", err);
            // Check if the error is relevant to the active task
            if (activeTaskId && event && event.target && event.target.url && event.target.url.includes(activeTaskId)) {
                if (latestStatusElement) {
                     latestStatusElement.textContent = "Status update connection failed. Please refresh manually for results.";
                     latestStatusElement.style.color = 'var(--color-error-text)';
                     latestStatusElement.classList.remove('animate-new');
                }
                hideElementWrapper(processingIndicatorWrapper);
                if (submitButtonSummary) submitButtonSummary.disabled = false;
                if (submitButtonStory) submitButtonStory.disabled = false;
                activeTaskId = null;
                activeTaskType = null;
            } else {
                 console.warn("SSE error occurred, but not for the active task or no task active.");
            }
            if (eventSource) { 
                eventSource.close(); 
                eventSource = null; 
            }
        };
    }

    // --- Initial Page Load Logic ---
    // Initialize by checking if we're processing something
    if (isProcessingSummary && summaryTaskId) {
        connectSSE(summaryTaskId, 'summary');
        hideFormsShowResults(); // Hide forms when processing
    } else if (isProcessingStory && storyTaskId) {
        connectSSE(storyTaskId, 'story');
        hideFormsShowResults(); // Hide forms when processing
    } else {
        hideElementWrapper(processingIndicatorWrapper);
        if (resultsContainerWrapper && !resultsContainerWrapper.classList.contains('hidden')) {
            showElementWrapper(resultsContainerWrapper);
            hideFormsShowResults(); // Hide forms when results are shown
            if (summaryViewWrapper) { 
                setViewWrapperHeight(summaryViewWrapper); 
            }
        } else {
            // No results or processing - show forms
            showFormsHideResults();
        }
        
        if (submitButtonSummary) submitButtonSummary.disabled = false;
        if (submitButtonStory) submitButtonStory.disabled = false;
    }

    // --- Form Submission Logic ---
    function handleFormSubmit(event, taskType) {
        console.log(`Handling submit for task type: ${taskType}`);
        
        let isValid = false;
        let loadingText = 'Processing...';
        const formElement = event.target.closest('form');

        // --- Validation ---
        if (taskType === 'summary') {
            const files = fileInput?.files;
            isValid = validateFiles(files);
            if (!isValid) {
                alert("Please select valid files (check type, size, and count) before submitting.");
                event.preventDefault(); // Prevent submission only if invalid
                return; 
            }
            loadingText = 'Summarizing Files...';
        } else if (taskType === 'story') {
            const url = githubUrlInput?.value?.trim();
            isValid = url && url.startsWith("https://github.com/");
            if (!isValid) {
                alert("Please enter a valid HTTPS GitHub repository URL (e.g., https://github.com/owner/repo).");
                event.preventDefault(); // Prevent submission only if invalid
                return;
            }
            loadingText = 'Generating Story...';
        } else {
            console.error("Unknown task type in handleFormSubmit:", taskType);
            event.preventDefault(); // Prevent submission for unknown type
            return;
        }

        // For valid submissions, update UI but don't prevent the natural form submission
        console.log("Form is valid. Updating UI before natural submission.");
        
        // Disable buttons
        if (submitButtonSummary) submitButtonSummary.disabled = true;
        if (submitButtonStory) submitButtonStory.disabled = true;

        // Show loading indicator
        if (processingTaskName) processingTaskName.textContent = loadingText;
        if (latestStatusElement) {
            latestStatusElement.textContent = 'Submitting request...';
            latestStatusElement.classList.remove('animate-new');
        }
        
        showElementWrapper(processingIndicatorWrapper);
        hideElementWrapper(resultsContainerWrapper);
        hideFormsShowResults();
        
        // Let the form submit naturally by not calling event.preventDefault()
        // The browser will handle form submission and any page reloading
    }

    // Attach form submission handlers
    if (summaryForm && submitButtonSummary) {
        summaryForm.addEventListener('submit', (e) => handleFormSubmit(e, 'summary'));
    }
    if (storyForm && submitButtonStory) {
        storyForm.addEventListener('submit', (e) => handleFormSubmit(e, 'story'));
    }

    // --- View Toggling Logic ---
    if (summaryViewToggles.length > 0 && summaryRenderedView && summaryRawView && summaryViewWrapper) {
        summaryViewToggles.forEach(button => {
            button.addEventListener('click', function() {
                const viewToShow = this.getAttribute('data-view');
                summaryViewToggles.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
                
                if (viewToShow === 'rendered') {
                    summaryRenderedView.classList.remove('hidden');
                    summaryRawView.classList.add('hidden');
                } else {
                    summaryRenderedView.classList.add('hidden');
                    summaryRawView.classList.remove('hidden');
                }
                
                setTimeout(() => setViewWrapperHeight(summaryViewWrapper), 50);
            });
        });
        // Initial height setting done during page load logic
    }

    // --- Copy Button Logic ---
    function handleCopyClick(button) {
        const targetId = button.getAttribute('data-target');
        const targetElement = document.getElementById(targetId);
        
        if (!targetElement) { 
            console.error(`Copy target #${targetId} not found.`);
            return;
        }
        
        let textToCopy = targetElement.innerText || targetElement.value || targetElement.textContent;
        textToCopy = textToCopy?.trim();
        
        if (!textToCopy) {
            console.warn(`No text in #${targetId} to copy.`);
            return;
        }
        
        if (!navigator.clipboard) {
            alert('Clipboard API not available.');
            return;
        }
        
        navigator.clipboard.writeText(textToCopy).then(() => {
            const originalText = button.innerText;
            button.innerText = 'Copied!';
            button.disabled = true;
            setTimeout(() => {
                button.innerText = originalText;
                button.disabled = false;
            }, 1500);
        }, (err) => {
            console.error('Copy failed: ', err);
            const originalText = button.innerText;
            button.innerText = 'Copy Failed';
            setTimeout(() => {
                button.innerText = originalText;
            }, 1500);
        });
    }

    // Setup copy buttons
    [copyButtonSummary, copyButtonStory].forEach(button => {
        if (button) {
            const targetId = button.getAttribute('data-target');
            const targetElement = document.getElementById(targetId);
            const content = targetElement?.innerText?.trim() || targetElement?.value?.trim() || targetElement?.textContent?.trim();
            const isError = content?.startsWith("Error:") || content?.includes('(Could not render');
            
            if (!targetElement || !content || isError) {
                button.style.display = 'none';
            } else {
                button.style.display = 'inline-block';
                button.addEventListener('click', () => handleCopyClick(button));
            }
        }
    });

    // Recalculate view wrapper height on window resize
    window.addEventListener('resize', () => {
        if (summaryViewWrapper && !summaryViewWrapper.classList.contains('hidden')) {
            setViewWrapperHeight(summaryViewWrapper);
        }
    });
});
