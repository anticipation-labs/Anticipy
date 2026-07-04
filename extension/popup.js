function render(state) {
  const dot = document.getElementById("dot");
  const status = document.getElementById("status");
  const pair = document.getElementById("pair");
  if (state && state.connected) {
    dot.classList.add("on");
    status.classList.add("on");
    status.textContent = state.paired ? "paired and connected" : "engine connected, not paired";
  } else {
    dot.classList.remove("on");
    status.classList.remove("on");
    status.textContent = state && state.paired ? "paired, engine offline" : "not paired";
  }
  if (pair) pair.style.display = state && state.paired ? "none" : "grid";
}

function load() {
  chrome.runtime.sendMessage("status", (state) => render(state || {}));
}

const DEFAULT_ENGINE_HTTP = "http://127.0.0.1:8787";

document.getElementById("pairButton").addEventListener("click", () => {
  const input = document.getElementById("code");
  const engineInput = document.getElementById("engine");
  const error = document.getElementById("error");
  const code = (input.value || "").trim();
  // Default to the localhost engine, but let a hosted user paste their cloud https URL.
  const engineHttp = ((engineInput && engineInput.value) || "").trim() || DEFAULT_ENGINE_HTTP;
  error.textContent = "";
  if (!code) {
    error.textContent = "Enter the code from setup.";
    return;
  }
  if (!/^https?:\/\//i.test(engineHttp)) {
    error.textContent = "Engine URL must start with http:// or https://";
    return;
  }
  chrome.runtime.sendMessage({
    type: "pair_device",
    pairing_code: code,
    label: "Chrome extension",
    engine_http: engineHttp,
  }, (response) => {
    if (!response || !response.ok) {
      error.textContent = (response && response.error) || "Pairing failed.";
      return;
    }
    load();
  });
});

load();
