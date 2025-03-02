// Simple bridge tester
document.addEventListener('DOMContentLoaded', function() {
    console.log("Bridge tester loaded");
    var div = document.createElement('div');
    div.innerHTML = "Bridge: " + (window.bridge ? "Available" : "Not available");
    div.style.position = "absolute";
    div.style.top = "5px";
    div.style.left = "5px";
    div.style.fontSize = "10px";
    div.style.color = window.bridge ? "green" : "red";
    document.body.appendChild(div);
});
