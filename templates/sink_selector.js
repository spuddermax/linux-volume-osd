// Initialize sink selection functionality
(function () {
	console.log("Initializing sink selection in volume template");

	// Define our sink selection function - will connect to bridge when available
	window.sinkSelected = function (sinkName) {
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
			const waitForBridge = setInterval(function () {
				attempts++;
				console.log("Attempt " + attempts + " to find bridge");

				if (window.bridge) {
					console.log("Bridge found on attempt " + attempts);
					window.bridge.selectSink(sinkName);
					clearInterval(waitForBridge);
					return true;
				} else if (attempts >= maxAttempts) {
					console.error(
						"Bridge not available after " + maxAttempts + " attempts"
					);
					clearInterval(waitForBridge);

					// Show an error message to the user
					if (window.showToast) {
						window.showToast(
							"Could not switch output - please try again",
							3000
						);
					}
				}
			}, 200);

			return false;
		}
	};

	// Check for WebChannel
	if (typeof QWebChannel === "undefined") {
		console.error("QWebChannel not loaded");
		if (window.showToast) {
			window.showToast("Communication error - please restart app", 3000);
		}
	} else {
		console.log("QWebChannel is available");
	}

	// Event delegation for sink clicks - handle all clicks in one place
	document.addEventListener("click", function (event) {
		const sinkItem = findClickedSinkItem(event.target);
		if (sinkItem) {
			const sinkName = sinkItem.dataset.sinkName;
			console.log("Sink clicked: " + sinkName);
			if (sinkName && !sinkItem.classList.contains("active-sink")) {
				console.log("Calling sinkSelected with: " + sinkName);
				window.sinkSelected(sinkName);
			}
		}
	});

	// Helper to find the sink item that was clicked (even if click is on a child element)
	function findClickedSinkItem(element) {
		let current = element;
		while (current && !current.classList.contains("sink-item")) {
			if (current === document.body) return null;
			current = current.parentElement;
		}
		return current;
	}
})();

// Debug helper
document.addEventListener("click", function (e) {
	console.log("Document clicked at: " + e.clientX + ", " + e.clientY);
	console.log("Target: ", e.target);
	if (window.bridge) {
		window.bridge.log("Document clicked, bridge is available");
	} else {
		console.warn("Bridge not available on document click");
	}
});

// Initialize the WebChannel for communication with Python
(function initWebChannel() {
	console.log("Initializing WebChannel...");

	// Setup a global placeholder for our bridge until it's ready
	if (!window.bridge) {
		// Temporary bridge with logging until the real one is available
		window.bridge = {
			_isPlaceholder: true,
			log: function (msg) {
				console.log("Bridge placeholder: " + msg);
			},
			selectSink: function (sinkName) {
				console.log("Bridge placeholder - selectSink: " + sinkName);
				showToast("Trying to connect to audio system...", 2000);
			},
		};
	}

	function connectWebChannel() {
		if (typeof QWebChannel === "undefined") {
			console.error(
				"QWebChannel is not defined! Make sure qwebchannel.js is loaded properly."
			);
			setTimeout(connectWebChannel, 500);
			return;
		}

		try {
			console.log("Setting up QWebChannel...");
			new QWebChannel(qt.webChannelTransport, function (channel) {
				if (channel.objects && channel.objects.bridge) {
					// Replace our placeholder with the real bridge
					console.log("Bridge object connected successfully!");

					// Store the old bridge to check if it was a placeholder
					const wasPlaceholder = window.bridge && window.bridge._isPlaceholder;

					// Set the real bridge
					window.bridge = channel.objects.bridge;

					// Log the successful connection
					window.bridge.log("WebChannel bridge connected successfully");

					// Set up the sinkSelected function that the volume template will use
					window.sinkSelected = function (sinkName) {
						console.log("Global sinkSelected called with: " + sinkName);
						window.bridge.selectSink(sinkName);
						return true;
					};

					if (wasPlaceholder) {
						showToast("Connection established", 1000);
					}
				} else {
					console.error("Bridge object not found in channel objects!");
					setTimeout(connectWebChannel, 500);
				}
			});
		} catch (error) {
			console.error("Error in QWebChannel setup:", error);
			setTimeout(connectWebChannel, 1000);
		}
	}

	// Try to connect immediately
	connectWebChannel();

	// And also set a backup timer (sometimes qt.webChannelTransport isn't available immediately)
	setTimeout(function () {
		if (window.bridge && window.bridge._isPlaceholder) {
			console.log(
				"Still using placeholder bridge after timeout, retrying connection..."
			);
			connectWebChannel();
		}
	}, 1000);
})();
