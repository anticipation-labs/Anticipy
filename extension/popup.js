// Ask the background worker for its engine-connection state and render it.
chrome.runtime.sendMessage("status", (state) => {
  const dot = document.getElementById("dot");
  const status = document.getElementById("status");
  if (state && state.connected) {
    dot.classList.add("on");
    status.classList.add("on");
    status.textContent = "connected · engine v" + (state.version || "?");
  } else {
    status.textContent = "engine offline";
  }
});
