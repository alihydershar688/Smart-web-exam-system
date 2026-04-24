// File Upload and Exam Creation JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeFileUpload();
});

function initializeFileUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const uploadedFiles = document.getElementById('uploadedFiles');
    const filesList = document.getElementById('filesList');
    const nextStep1 = document.getElementById('nextStep1');

    // Drag and drop functionality
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', function() {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
    });

    function handleFiles(files) {
        if (files.length > 0) {
            filesList.innerHTML = '';
            
            Array.from(files).forEach(file => {
                if (isValidFileType(file)) {
                    addFileToList(file);
                } else {
                    alert(`File ${file.name} is not a supported format.`);
                }
            });

            uploadedFiles.style.display = 'block';
            nextStep1.disabled = false;
        }
    }

    function isValidFileType(file) {
        const validTypes = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        ];
        return validTypes.includes(file.type);
    }

    function addFileToList(file) {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        
        const fileSize = (file.size / (1024 * 1024)).toFixed(2);
        
        fileItem.innerHTML = `
            <div class="file-icon">📄</div>
            <div class="file-info">
                <div class="file-name">${file.name}</div>
                <div class="file-size">${fileSize} MB</div>
            </div>
            <button class="file-remove" onclick="removeFile(this)">🗑️</button>
        `;
        
        filesList.appendChild(fileItem);
    }
}

function removeFile(button) {
    const fileItem = button.parentElement;
    fileItem.remove();
    
    const filesList = document.getElementById('filesList');
    if (filesList.children.length === 0) {
        document.getElementById('uploadedFiles').style.display = 'none';
        document.getElementById('nextStep1').disabled = true;
    }
}

function nextStep(step) {
    // Hide all steps
    document.querySelectorAll('.wizard-step').forEach(step => {
        step.classList.remove('active');
    });
    
    // Show target step
    document.getElementById(`step${step}`).classList.add('active');
    
    // Special handling for step 2 (AI Processing)
    if (step === 2) {
        simulateAIProcessing();
    }
}

function previousStep(step) {
    nextStep(step);
}

function simulateAIProcessing() {
    const progressBar = document.getElementById('processingProgress');
    const nextButton = document.getElementById('nextStep2');
    let progress = 0;
    
    const interval = setInterval(() => {
        progress += Math.random() * 10;
        if (progress >= 100) {
            progress = 100;
            clearInterval(interval);
            nextButton.disabled = false;
        }
        progressBar.style.width = `${progress}%`;
    }, 200);
}

function createExam() {
    // Simulate exam creation
    const submitBtn = document.querySelector('.wizard-actions .btn-success');
    const originalText = submitBtn.textContent;
    
    submitBtn.textContent = 'Creating Exam...';
    submitBtn.disabled = true;
    
    setTimeout(() => {
        alert('Exam created successfully!');
        window.location.href = 'dashboard-teacher.html';
    }, 2000);
}
