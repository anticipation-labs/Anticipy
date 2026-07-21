const BASE = "http://127.0.0.1:8090";

async function refresh() {
  const backendDot = document.getElementById("backendDot");
  const backendText = document.getElementById("backendText");
  try {
    const r = await fetch(`${BASE}/api/health`);
    if (r.ok) {
      backendDot.classList.add("on");
      backendText.textContent = "Connected to Anticipy";
    } else {
      throw new Error();
    }
  } catch {
    backendDot.classList.remove("on");
    backendText.textContent = "Not reachable yet — is your Anticipy backend running?";
  }

  const { openrouterKey } = await chrome.storage.local.get("openrouterKey");
  const keyDot = document.getElementById("keyDot");
  const keyText = document.getElementById("keyText");
  if (openrouterKey) {
    keyDot.classList.add("on");
    keyText.textContent = "Key saved";
  }
}

document.getElementById("save").addEventListener("click", async () => {
  const v = document.getElementById("key").value.trim();
  if (!v) return;
  await chrome.storage.local.set({ openrouterKey: v });
  document.getElementById("key").value = "";
  refresh();
});

refresh();
setInterval(refresh, 5000);
