// bridge_tester.js - Helps debug the QWebChannel bridge connection

// Global variables to track bridge state
var bridgeTester = {
    initialized: false,
    bridgeAvailable: false,
    checkInterval: null,
    lastCheckTime: 0,
    checkCount: 0,
    maxChecks: 20
};

// Function to initialize the bridge tester
function initBridgeTester() {
    console.log("Bridge tester initializing...");
    
    // Don't initialize twice
    if (bridgeTester.initialized) {
        console.log("Bridge tester already initialized");
        return;
    }
    
    bridgeTester.initialized = true;
    
    // Create status element
    var statusDiv = document.createElement('div');
    statusDiv.id = 'bridge-status';
    statusDiv.style.position = 'absolute';
    statusDiv.style.top = '5px';
    statusDiv.style.left = '5px';
    statusDiv.style.padding = '3px';
    statusDiv.style.backgroundColor = 'rgba(0,0,0,0.5)';
    statusDiv.style.color = 'red';
    statusDiv.style.fontSize = '10px';
    statusDiv.style.zIndex = '9999';
    statusDiv.innerText = 'Bridge: Checking...';
    
    // Add to document
    document.body.appendChild(statusDiv);
    
    // Start checking for bridge
    checkBridge();
    
    // Set interval to check bridge periodically
    bridgeTester.checkInterval = setInterval(checkBridge, 500);
    
    // Add click handler to test bridge
    document.addEventListener('click', function(e) {
        if (e.altKey) {
            testBridge();
        }
    });
    
    console.log("Bridge tester initialized");
}

// Function to check if bridge is available
function checkBridge() {
    bridgeTester.checkCount++;
    bridgeTester.lastCheckTime = Date.now();
    
    var statusDiv = document.getElementById('bridge-status');
    if (!statusDiv) return;
    
    if (window.bridge) {
        bridgeTester.bridgeAvailable = true;
        statusDiv.style.color = 'lime';
        statusDiv.innerText = 'Bridge: Connected ✓';
        
        // Clear interval after max checks
        if (bridgeTester.checkCount >= bridgeTester.maxChecks) {
            clearInterval(bridgeTester.checkInterval);
            
            // Hide status after success
            setTimeout(function() {
                statusDiv.style.opacity = '0.5';
            }, 3000);
        }
    } else {
        statusDiv.style.color = 'red';
        statusDiv.innerText = 'Bridge: Not Found ✗ (' + bridgeTester.checkCount + ')';
        
        // Clear interval after max checks if bridge never found
        if (bridgeTester.checkCount >= bridgeTester.maxChecks) {
            clearInterval(bridgeTester.checkInterval);
            statusDiv.innerText = 'Bridge: Failed to connect ✗';
        }
    }
}

// Function to test the bridge by sending a log message
function testBridge() {
    console.log("Testing bridge...");
    
    var statusDiv = document.getElementById('bridge-status');
    if (!statusDiv) return;
    
    if (window.bridge) {
        try {
            window.bridge.log("Bridge test at " + new Date().toISOString());
            console.log("Bridge log message sent successfully");
            
            // Test sink selection if available
            if (typeof window.bridge.selectSink === 'function') {
                statusDiv.innerText = 'Bridge: Test message sent ✓';
                statusDiv.style.color = 'lime';
            } else {
                statusDiv.innerText = 'Bridge: Connected but missing selectSink ⚠️';
                statusDiv.style.color = 'orange';
            }
        } catch (e) {
            console.error("Bridge test error: " + e);
            statusDiv.innerText = 'Bridge: Error testing ⚠️';
            statusDiv.style.color = 'orange';
        }
    } else {
        console.error("Bridge not available for testing");
        statusDiv.innerText = 'Bridge: Not available ✗';
        statusDiv.style.color = 'red';
    }
}

// Initialize when document is ready
if (document.readyState === "complete" || document.readyState === "interactive") {
    initBridgeTester();
} else {
    document.addEventListener("DOMContentLoaded", initBridgeTester);
}

// Export functions for external use
window.testBridge = testBridge;
window.checkBridge = checkBridge; 