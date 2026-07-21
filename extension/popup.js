fetch("http://127.0.0.1:8090/api/health")
  .then((r) => r.json())
  .then(() => (document.getElementById("status").textContent = "backend: online"))
  .catch(() => (document.getElementById("status").textContent = "backend: offline"));

chrome.storage.local.get("openrouterKey").then(({ openrouterKey }) => {
  if (openrouterKey) document.getElementById("saved").textContent = "key set";
});
document.getElementById("save").addEventListener("click", async () => {
  const v = document.getElementById("key").value.trim();
  if (!v) return;
  await chrome.storage.local.set({ openrouterKey: v });
  document.getElementById("saved").textContent = "key set";
});
