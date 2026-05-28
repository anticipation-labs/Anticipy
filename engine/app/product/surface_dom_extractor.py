"""DOM accessibility-tree extractor for cheap LLM consumption.

Pairs with the vision adapter (``surface_runtime_vision.py``) and the
universal surface runtime (``universal_surface_runtime.py``). Produces a
compact semantic snapshot of the active Chrome tab so the planner can
reason over labeled actionable nodes instead of raw DOM strings.

The extractor talks to the loopback bridge at ``127.0.0.1:7777``.
Preferred path is ``POST /surface-command {command:"eval_js", code}``,
which routes through the Chrome extension service worker to
``chrome.scripting.executeScript``. When that endpoint is missing
(fallback bridge) we degrade gracefully and use ``/surface-proof`` for
url+title and synthesize a minimal tree from any DOM substring the
bridge returned, so the contract still holds without throwing.

No frozen paths are touched. No em-dashes anywhere.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BRIDGE_HOST = os.environ.get("ANTICIPY_SURFACE_HOST", "127.0.0.1")
try:
    BRIDGE_PORT = int(os.environ.get("ANTICIPY_SURFACE_PORT", "7777"))
except ValueError:
    BRIDGE_PORT = 7777
BRIDGE_SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")
MAX_NODES = 200
DEFAULT_MAX_CHARS = 15000


# ---------------------------------------------------------------- JS payload

# Walks the live DOM, picks elements that are actionable or carry a role,
# returns a compact JSON array. Runs inside the page; never sent raw to LLM.
_TREE_JS = r"""
(function(){try{
var SEL='[role], button, input, a, textarea, select, [contenteditable], [tabindex]:not([tabindex="-1"])';
var seen=new Set(),nodes=[],els=Array.from(document.body.querySelectorAll(SEL));
function txt(e){if(!e)return'';var t=(e.getAttribute('aria-label')||e.getAttribute('alt')||e.getAttribute('title')||e.getAttribute('placeholder')||e.textContent||'').trim();return t.replace(/\s+/g,' ').slice(0,120);}
function role(e){var r=e.getAttribute('role');if(r)return r;var g=e.tagName.toLowerCase();if(g==='a')return'link';if(g==='button')return'button';
if(g==='input'){var t=(e.getAttribute('type')||'text').toLowerCase();if(t==='submit'||t==='button')return'button';if(t==='search')return'searchbox';if(t==='checkbox')return'checkbox';if(t==='radio')return'radio';return'textbox';}
if(g==='textarea')return'textbox';if(g==='select')return'combobox';if(e.getAttribute('contenteditable')==='true')return'textbox';return g;}
function visible(e){var r=e.getBoundingClientRect();if(r.width<1||r.height<1)return false;var s=window.getComputedStyle(e);if(s.visibility==='hidden'||s.display==='none'||parseFloat(s.opacity||'1')<0.05)return false;return true;}
function actionable(e,r){if(e.disabled)return false;var t=e.tagName.toLowerCase();if(['a','button','input','select','textarea'].indexOf(t)!==-1)return true;if(e.getAttribute('contenteditable')==='true')return true;if(['button','link','menuitem','tab','checkbox','radio','searchbox','textbox','combobox','switch','option'].indexOf(r)!==-1)return true;if(e.hasAttribute('onclick'))return true;return false;}
var nid=0,idMap=new Map();
function getId(e){if(idMap.has(e))return idMap.get(e);nid+=1;idMap.set(e,nid);return nid;}
function parentId(e){var p=e.parentElement;while(p&&p!==document.body){if(idMap.has(p))return idMap.get(p);p=p.parentElement;}return 0;}
for(var i=0;i<els.length&&nodes.length<200;i++){var el=els[i];if(seen.has(el))continue;seen.add(el);if(!visible(el))continue;
var r=role(el),b=el.getBoundingClientRect(),id=getId(el);
nodes.push({node_id:id,role:r,name:txt(el),value:(el.value!==undefined?String(el.value).slice(0,80):''),bbox:[Math.round(b.left),Math.round(b.top),Math.round(b.width),Math.round(b.height)],is_actionable:actionable(el,r),parent_id:parentId(el),tag:el.tagName.toLowerCase()});}
var f=document.activeElement,fid=(f&&idMap.has(f))?idMap.get(f):0;
return JSON.stringify({root:{url:location.href,title:document.title},nodes:nodes,focused_id:fid});
}catch(e){return JSON.stringify({error:String(e),root:{url:location.href,title:document.title},nodes:[]});}})()
"""


# -------------------------------------------------------------- data shapes


@dataclass
class _BridgeReply:
    ok: bool
    data: dict[str, Any]
    error: str


# --------------------------------------------------------------- extractor


class DomExtractor:
    """Extracts and compacts the live DOM accessibility tree."""

    def __init__(
        self,
        *,
        host: str = BRIDGE_HOST,
        port: int = BRIDGE_PORT,
        secret: str = BRIDGE_SECRET,
        request_timeout: float = 15.0,
    ) -> None:
        self.base_url = f"http://{host}:{port}"
        self.secret = secret
        self.request_timeout = float(request_timeout)

    # ----------------------------------------------------------- http plumb

    def _post(self, path: str, payload: dict[str, Any]) -> _BridgeReply:
        body = json.dumps({**payload, "secret": self.secret}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {}
            return _BridgeReply(False, data if isinstance(data, dict) else {}, f"http {exc.code}")
        except Exception as exc:
            return _BridgeReply(False, {}, f"{type(exc).__name__}: {exc}")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return _BridgeReply(False, {}, "non-json reply")
        if not isinstance(data, dict):
            return _BridgeReply(False, {}, "non-dict reply")
        return _BridgeReply(bool(data.get("ok")), data, str(data.get("error") or ""))

    def _navigate(self, url: str) -> _BridgeReply:
        return self._post("/surface-command", {"command": "navigate", "url": url})

    def _eval_js(self, code: str) -> _BridgeReply:
        return self._post("/surface-command", {"command": "eval_js", "code": code})

    def _surface_proof(self) -> _BridgeReply:
        return self._post("/surface-proof", {"limit": 20000, "url_prefix": ""})

    # ------------------------------------------------------ public surface

    def extract_semantic_tree(self, url_or_tab: str | None = None) -> dict[str, Any]:
        """Return ``{root, nodes:[...]}`` for the current or seeded tab."""
        if url_or_tab and (url_or_tab.startswith("http://") or url_or_tab.startswith("https://")):
            nav = self._navigate(url_or_tab)
            if not nav.ok:
                return {
                    "root": {"url": url_or_tab, "title": ""},
                    "nodes": [],
                    "error": nav.error or "navigate failed",
                    "source": "bridge_navigate_error",
                }
            time.sleep(0.6)

        # Preferred path: bridge can run JS in the tab.
        js_reply = self._eval_js(_TREE_JS)
        if js_reply.ok:
            payload = js_reply.data.get("data") if isinstance(js_reply.data.get("data"), dict) else {}
            raw_result = payload.get("result") if isinstance(payload, dict) else None
            tree = self._parse_js_result(raw_result)
            if tree is not None:
                tree["source"] = "bridge_eval_js"
                tree["nodes"] = tree.get("nodes", [])[:MAX_NODES]
                return tree

        # Fallback: pull whatever the bridge proof endpoint can offer.
        proof = self._surface_proof()
        root = {
            "url": str(proof.data.get("url") or url_or_tab or ""),
            "title": str(proof.data.get("title") or ""),
        }
        dom_blob = str(proof.data.get("dom") or "")
        nodes = self._synthesize_from_dom_blob(dom_blob)[:MAX_NODES]
        return {
            "root": root,
            "nodes": nodes,
            "source": "bridge_surface_proof_fallback",
            "warning": "bridge does not expose eval_js; tree is heuristic",
        }

    def compact_for_llm(self, tree: dict[str, Any], max_chars: int = DEFAULT_MAX_CHARS) -> str:
        """Format ``tree`` as numbered text the planner can reference."""
        if not isinstance(tree, dict):
            return ""
        nodes = tree.get("nodes") or []
        root = tree.get("root") or {}
        lines: list[str] = []
        url = str(root.get("url") or "")
        title = str(root.get("title") or "")
        if url or title:
            head = f"PAGE url={url[:120]} title={title[:80]}"
            lines.append(head)
        for n in nodes:
            if not isinstance(n, dict):
                continue
            nid = n.get("node_id") or n.get("id") or 0
            role = str(n.get("role") or "").strip() or "node"
            name = str(n.get("name") or "").strip()
            value = str(n.get("value") or "").strip()
            actionable = bool(n.get("is_actionable"))
            parts = [f"[{nid}]", role]
            if name:
                safe = name.replace('"', "'")[:80]
                parts.append(f'"{safe}"')
            if value:
                safe_v = value.replace('"', "'")[:60]
                parts.append(f'value="{safe_v}"')
            if actionable:
                parts.append("[actionable]")
            line = " ".join(parts)
            lines.append(line)
            joined = "\n".join(lines)
            if len(joined) > max_chars:
                # Trim the last line if we just blew past the budget.
                lines.pop()
                lines.append("... (truncated)")
                break
        out = "\n".join(lines)
        if len(out) > max_chars:
            out = out[: max_chars - 16].rstrip() + "\n... (truncated)"
        return out

    def get_focused_element(self, tab: str | None = None) -> dict[str, Any]:
        """Return the currently focused element from the active tab."""
        tree = self.extract_semantic_tree(tab)
        focused_id = tree.get("focused_id") or 0
        for node in tree.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if int(node.get("node_id") or 0) == int(focused_id) and focused_id:
                return {
                    "node_id": node.get("node_id"),
                    "role": node.get("role"),
                    "name": node.get("name"),
                    "value": node.get("value"),
                }
        return {"node_id": 0, "role": "", "name": "", "value": ""}

    def wait_for_element(
        self,
        description: str,
        timeout_s: float = 10.0,
        *,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """Poll the tree until a node matches ``description``."""
        needle = (description or "").strip().lower()
        if not needle:
            return {"found": False, "node_id": 0, "bbox": [0, 0, 0, 0], "error": "empty description"}
        deadline = time.monotonic() + max(0.5, float(timeout_s))
        last_tree: dict[str, Any] = {}
        while time.monotonic() < deadline:
            tree = self.extract_semantic_tree()
            last_tree = tree
            for node in tree.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                hay = " ".join([
                    str(node.get("role") or ""),
                    str(node.get("name") or ""),
                    str(node.get("value") or ""),
                ]).lower()
                if needle in hay:
                    return {
                        "found": True,
                        "node_id": node.get("node_id"),
                        "bbox": node.get("bbox") or [0, 0, 0, 0],
                        "role": node.get("role"),
                        "name": node.get("name"),
                    }
            time.sleep(poll_interval)
        return {
            "found": False,
            "node_id": 0,
            "bbox": [0, 0, 0, 0],
            "error": f"no node matched '{description}' within {timeout_s}s",
            "last_node_count": len(last_tree.get("nodes") or []),
        }

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _parse_js_result(raw: Any) -> dict[str, Any] | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            txt = raw.strip()
            if not txt:
                return None
            try:
                obj = json.loads(txt)
            except Exception:
                return None
            return obj if isinstance(obj, dict) else None
        return None

    @staticmethod
    def _synthesize_from_dom_blob(dom_blob: str) -> list[dict[str, Any]]:
        """Heuristic node list when the bridge gives only a DOM string."""
        if not dom_blob:
            return []
        out: list[dict[str, Any]] = []
        # Crudely surface anchors, buttons, and inputs with name attributes.
        pattern = re.compile(
            r"<(a|button|input|textarea|select)\b([^>]*)>([^<]{0,80})",
            re.IGNORECASE,
        )
        nid = 0
        for match in pattern.finditer(dom_blob):
            nid += 1
            if nid > MAX_NODES:
                break
            tag = match.group(1).lower()
            attrs = match.group(2) or ""
            inner = (match.group(3) or "").strip()
            name_match = re.search(
                r'(?:aria-label|placeholder|title|name|value)=["\']([^"\']{1,80})["\']',
                attrs,
                re.IGNORECASE,
            )
            name = (name_match.group(1) if name_match else inner)[:80]
            role = "link" if tag == "a" else ("button" if tag == "button" else (
                "textbox" if tag in {"input", "textarea"} else (
                    "combobox" if tag == "select" else tag
                )
            ))
            out.append({
                "node_id": nid,
                "role": role,
                "name": name,
                "value": "",
                "bbox": [0, 0, 0, 0],
                "is_actionable": True,
                "parent_id": 0,
                "tag": tag,
            })
        return out


__all__ = ["DomExtractor"]
