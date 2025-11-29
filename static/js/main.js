/**
 * Main JavaScript for onboarding system
 * Handles view toggling and form submission
 */

// Toggle between chatbot and legacy form views
document.addEventListener('DOMContentLoaded', function() {
    const modeToggle = document.getElementById('modeToggle');
    const chatbotView = document.getElementById('chatbotView');
    const legacyView = document.getElementById('legacyView');
    const onboardingForm = document.getElementById('onboardingForm');
    
    // Chatbot elements
    const chatbotInput = document.getElementById('chatbotInput');
    const chatbotSend = document.getElementById('chatbotSend');
    const chatbotMessages = document.getElementById('chatbotMessages');
    
    // Get initial labels - toggle starts with "Form" when in chatbot mode
    let isChatbotMode = true;
    const chatbotLabel = 'Agentic';
    const legacyLabel = 'Form';
    
    // Enable chatbot inputs (remove disabled state)
    if (chatbotInput && chatbotSend) {
        chatbotInput.disabled = false;
        chatbotSend.disabled = false;
    }
    
    // Toggle view function
    modeToggle.addEventListener('click', function() {
        isChatbotMode = !isChatbotMode;
        
        if (isChatbotMode) {
            // Switch to chatbot view
            chatbotView.classList.add('active');
            legacyView.classList.remove('active');
            // Visually handled by CSS, but keep textContent for accessibility
            modeToggle.setAttribute('aria-label', legacyLabel);
        } else {
            // Switch to legacy form view
            legacyView.classList.add('active');
            chatbotView.classList.remove('active');
            modeToggle.setAttribute('aria-label', chatbotLabel);
        }
    });
    
    // Chatbot functionality
    function sendChatMessage() {
        const message = chatbotInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        addMessageToChat(message, 'user');
        chatbotInput.value = '';
        chatbotInput.disabled = true;
        chatbotSend.disabled = true;
        
        // Show loading indicator
        const loadingMessage = addMessageToChat('Thinking...', 'bot');
        
        // Send to backend
        fetch('/api/agent_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => response.json())
        .then(result => {
            // Remove loading message
            loadingMessage.remove();
            
            if (result.success) {
                if (Array.isArray(result.response)) {
                    result.response.forEach(msg => addMessageToChat(msg, 'bot'));
                } else {
                    addMessageToChat(result.response, 'bot');
                }
            } else {
                addMessageToChat('Error: ' + (result.error || 'Failed to get response'), 'bot');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            loadingMessage.remove();
            addMessageToChat('An error occurred. Please try again.', 'bot');
        })
        .finally(() => {
            chatbotInput.disabled = false;
            chatbotSend.disabled = false;
            chatbotInput.focus();
        });
    }
    
    function addMessageToChat(message, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        const p = document.createElement('p');
        p.textContent = message;
        messageDiv.appendChild(p);
        chatbotMessages.appendChild(messageDiv);
        chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
        return messageDiv;
    }
    
    // Chatbot send button click
    if (chatbotSend) {
        chatbotSend.addEventListener('click', sendChatMessage);
    }
    
    // Chatbot input enter key
    if (chatbotInput) {
        chatbotInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });
    }
    
    // Handle form submission
    if (onboardingForm) {
        onboardingForm.addEventListener('submit', function(e) {
            e.preventDefault();

            // Show loading state on the submit button
            const submitBtn = onboardingForm.querySelector('.submit-btn');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.dataset.originalText = submitBtn.textContent;
                submitBtn.textContent = 'Submitting...';
                submitBtn.classList.add('loading');
            }
            
            // Collect form data into a plain object matching backend expectations
            const formData = new FormData(onboardingForm);
            const payload = {};
            
            for (const [key, value] of formData.entries()) {
                payload[key] = value.trim();
            }

            // Submit to backend
            fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    alert('Registration successful! Thank you for completing the onboarding process.');
                    onboardingForm.reset();
                } else {
                    alert('Error: ' + (result.error || 'Registration failed. Please try again.'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred. Please try again.');
            })
            .finally(() => {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = submitBtn.dataset.originalText || 'Complete Registration';
                    submitBtn.classList.remove('loading');
                }
            });
        });
    }
});

