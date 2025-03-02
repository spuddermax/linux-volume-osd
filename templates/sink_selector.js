// Initialize sink selection functionality
(function() {
    console.log("Initializing sink selection in volume template");
    
    // Define our sink selection function - will connect to bridge when available
    window.sinkSelected = function(sinkName) {
        console.log("sinkSelected called with: " + sinkName);
        
        // Try using the bridge if available
        if (window.bridge) {
            console.log("Using bridge.selectSink");
            window.bridge.selectSink(sinkName);
            return true;
        } else {
            console.error("Bridge not available yet");
            
            // Keep trying to find the bridge in case it's just not initialized yet
            let attempts = 0;
            const maxAttempts = 5;
            const waitForBridge = setInterval(function() {
                attempts++;
                console.log("Attempt " + attempts + " to find bridge");
                
                if (window.bridge) {
                    console.log("Bridge found on attempt " + attempts);
                    window.bridge.selectSink(sinkName);
                    clearInterval(waitForBridge);
                    return true;
                } else if (attempts >= maxAttempts) {
                    console.error("Bridge not available after " + maxAttempts + " attempts");
                    clearInterval(waitForBridge);
                    
                    // Show an error message to the user
                    if (window.showToast) {
                        window.showToast("Could not switch output - please try again", 3000);
                    }
                }
            }, 200);
            
            return false;
        }
    };

    // Check for WebChannel
    if (typeof QWebChannel === 'undefined') {
        console.error("QWebChannel not loaded");
        if (window.showToast) {
            window.showToast("Communication error - please restart app", 3000);
        }
    } else {
        console.log("QWebChannel is available");
    }
    
    // Event delegation for sink clicks - handle all clicks in one place
    document.addEventListener('click', function(event) {
        const sinkItem = findClickedSinkItem(event.target);
        if (sinkItem) {
            const sinkName = sinkItem.dataset.sinkName;
            console.log("Sink clicked: " + sinkName);
            if (sinkName && !sinkItem.classList.contains('active-sink')) {
                console.log("Calling sinkSelected with: " + sinkName);
                window.sinkSelected(sinkName);
            }
        }
    });
    
    // Helper to find the sink item that was clicked (even if click is on a child element)
    function findClickedSinkItem(element) {
        let current = element;
        while (current && !current.classList.contains('sink-item')) {
            if (current === document.body) return null;
            current = current.parentElement;
        }
        return current;
    }
})();
