fetch("http://127.0.0.1:8090/api/health")
  .then((r) => r.json())
  .then(() => (document.getElementById("status").textContent = "backend: online"))
  .catch(() => (document.getElementById("status").textContent = "backend: offline"));
