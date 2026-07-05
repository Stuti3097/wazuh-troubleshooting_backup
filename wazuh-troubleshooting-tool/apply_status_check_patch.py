#!/usr/bin/env python3
"""
apply_status_check_patch.py

Adds "Check Status" buttons (Indexer / Manager / Dashboard) to the
Wazuh Troubleshooting Portal, backed by a new /status endpoint that
runs `systemctl status <service>`.

WHAT THIS DOES:
  1. backend/main.py   -> adds a new /status endpoint (whitelisted services only)
  2. frontend/app.js   -> adds the checkServiceStatus() JS function and
                          dynamically injects 3 buttons + an output panel
                          into the existing "Quick System Actions" panel
                          at page load. (No index.html editing needed —
                          this avoids fragile HTML text-matching.)

It does NOT touch index.html at all.

USAGE:
    python3 apply_status_check_patch.py /path/to/wazuh-troubleshooting-tool

    If you omit the path, it assumes the current directory is the
    project root (i.e. it expects ./backend/main.py and ./frontend/app.js
    to exist).

SAFETY:
  - Creates a timestamped .bak copy of each file before touching it.
  - Is idempotent: running it twice will NOT double-insert the patch
    (it checks for a marker string first).
"""

import sys
import os
import shutil
import datetime

MARKER = "PATCH:CHECK-SERVICE-STATUS-V1"


def backup(path):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_path = f"{path}.bak_{ts}"
    shutil.copy2(path, bak_path)
    print(f"  [backup] {path} -> {bak_path}")


def patch_main_py(project_root):
    path = os.path.join(project_root, "backend", "main.py")
    if not os.path.isfile(path):
        print(f"[SKIP] Could not find {path}")
        return False

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER in content:
        print(f"[OK] {path} already patched, skipping.")
        return True

    anchor = '@app.get("/filebeat-test")'
    if anchor not in content:
        print(f"[FAIL] Could not find anchor point in {path}.")
        print("       Your main.py may differ from the expected version.")
        print("       No changes were made to this file.")
        return False

    new_block = f'''# -----------------------------
# {MARKER}
# Check Service Status (systemctl status)
# -----------------------------
ALLOWED_STATUS_SERVICES = {{
    "wazuh-indexer",
    "wazuh-manager",
    "wazuh-dashboard"
}}

@app.get("/status")
def status(service: str = ""):
    if service not in ALLOWED_STATUS_SERVICES:
        return {{"service": service, "output": "Invalid service"}}

    output = run(f"systemctl status {{service}} --no-pager")
    is_active = run(f"systemctl is-active {{service}}")

    return {{
        "service": service,
        "is_active": is_active,
        "output": output
    }}

'''

    backup(path)
    content = content.replace(anchor, new_block + anchor, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[DONE] Patched {path} (added /status endpoint)")
    return True


def patch_app_js(project_root):
    path = os.path.join(project_root, "frontend", "app.js")
    if not os.path.isfile(path):
        print(f"[SKIP] Could not find {path}")
        return False

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER in content:
        print(f"[OK] {path} already patched, skipping.")
        return True

    js_block = f'''

// ─────────────────────────────────────────────────────────────────────────────
// {MARKER}
// CHECK SERVICE STATUS (systemctl status) — injected buttons + panel
// ─────────────────────────────────────────────────────────────────────────────
async function checkServiceStatus(service) {{
    const panel   = document.getElementById("statusOutputPanel");
    const titleEl = document.getElementById("statusOutputTitle");
    const badgeEl = document.getElementById("statusOutputBadge");
    const textEl  = document.getElementById("statusOutputText");
    const btnId   = "act-status-" + service.replace("wazuh-", "");
    const btn     = document.getElementById(btnId);

    if (panel) panel.style.display = "block";
    if (titleEl) titleEl.textContent = `systemctl status ${{service}}`;
    if (badgeEl) {{
        badgeEl.textContent = "CHECKING...";
        badgeEl.className = "badge warning";
    }}
    if (textEl) textEl.textContent = "Fetching status...";

    if (btn) {{
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Checking...";
    }}

    try {{
        let res = await fetch(BASE_URL + "/status?service=" + service);
        let data = await res.json();

        if (textEl) textEl.textContent = data.output || "(no output returned)";

        if (badgeEl) {{
            const active = data.is_active === "active";
            badgeEl.textContent = (data.is_active || "unknown").toUpperCase();
            badgeEl.className = "badge " + (active ? "healthy" : "critical");
        }}
    }} catch (e) {{
        if (textEl) textEl.textContent = "[ERROR] Failed to reach backend for status check.";
        if (badgeEl) {{
            badgeEl.textContent = "ERROR";
            badgeEl.className = "badge critical";
        }}
        console.error(e);
    }} finally {{
        if (btn) {{
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText;
        }}
    }}
}}
window.checkServiceStatus = checkServiceStatus;

function injectStatusCheckButtons() {{
    const grid = document.getElementById("quickActions");
    if (!grid) return;
    if (document.getElementById("act-status-indexer")) return; // already injected

    const services = [
        {{ id: "indexer",   name: "wazuh-indexer",   label: "Check Indexer Status" }},
        {{ id: "manager",   name: "wazuh-manager",   label: "Check Manager Status" }},
        {{ id: "dashboard", name: "wazuh-dashboard", label: "Check Dashboard Status" }}
    ];

    services.forEach(svc => {{
        const b = document.createElement("button");
        b.id = "act-status-" + svc.id;
        b.textContent = svc.label;
        b.onclick = () => checkServiceStatus(svc.name);
        grid.appendChild(b);
    }});

    const panel = document.createElement("div");
    panel.id = "statusOutputPanel";
    panel.style.marginTop = "15px";
    panel.style.display = "none";
    panel.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span id="statusOutputTitle" style="font-size:13px; font-weight:600; color:var(--text-secondary);"></span>
            <span id="statusOutputBadge" class="badge"></span>
        </div>
        <pre id="statusOutputText" class="terminal" style="height:180px;"></pre>
    `;
    grid.insertAdjacentElement("afterend", panel);
}}

window.addEventListener("DOMContentLoaded", injectStatusCheckButtons);
// If DOMContentLoaded already fired before this script ran, run immediately too.
if (document.readyState === "interactive" || document.readyState === "complete") {{
    injectStatusCheckButtons();
}}
'''

    backup(path)
    content = content + js_block

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[DONE] Patched {path} (added checkServiceStatus + button injection)")
    return True


DEFAULT_PROJECT_ROOT = "/home/vagrant/wazuh-troubleshooting_backup/wazuh-troubleshooting-tool"


MARKER2 = "PATCH:UNIFY-QUICK-ACTIONS-OUTPUT-V1"


def patch_app_js_unify_output(project_root):
    path = os.path.join(project_root, "frontend", "app.js")
    if not os.path.isfile(path):
        print(f"[SKIP] Could not find {path}")
        return False

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER2 in content:
        print(f"[OK] {path} already has the output-unification patch, skipping.")
        return True

    if MARKER not in content:
        print(f"[FAIL] {path} does not have the status-check patch applied yet.")
        print("       Run this script's base patch first (it runs automatically before this step).")
        return False

    js_block = f'''

// ─────────────────────────────────────────────────────────────────────────────
// {MARKER2}
// Override quickRestart() and checkFilebeat() so ALL Quick Action buttons
// (restart x3, filebeat test, status check x3) report into the SAME panel
// (#statusOutputPanel) right under the buttons, instead of the far-away
// #logs "System Check Logs" box. This function redefinition intentionally
// overrides the earlier quickRestart/checkFilebeat in this same file.
// ─────────────────────────────────────────────────────────────────────────────
async function quickRestart(service) {{
    const panel   = document.getElementById("statusOutputPanel");
    const titleEl = document.getElementById("statusOutputTitle");
    const badgeEl = document.getElementById("statusOutputBadge");
    const textEl  = document.getElementById("statusOutputText");
    const btnId   = "act-restart-" + service.replace("wazuh-", "");
    const btn     = document.getElementById(btnId);

    if (panel) panel.style.display = "block";
    if (titleEl) titleEl.textContent = `Restarting ${{service}}...`;
    if (badgeEl) {{
        badgeEl.textContent = "RESTARTING...";
        badgeEl.className = "badge warning";
    }}
    if (textEl) textEl.textContent = `Executing: systemctl restart ${{service}}\\nThis can take up to 30 seconds...`;

    if (btn) {{
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Restarting...";
    }}

    try {{
        let res = await fetch(BASE_URL + "/fix?service=" + service);
        let data = await res.json();

        if (titleEl) titleEl.textContent = `systemctl restart ${{service}}`;
        if (textEl) textEl.textContent = data.message || "(no output returned)";

        if (badgeEl) {{
            const ok = data.status_after_fix === "active" || data.status_after_fix === "ok";
            badgeEl.textContent = (data.status_after_fix || "unknown").toUpperCase();
            badgeEl.className = "badge " + (ok ? "healthy" : "critical");
        }}

        if (window.startCheck) startCheck();
    }} catch (e) {{
        if (textEl) textEl.textContent = "[ERROR] Failed to execute restart action.";
        if (badgeEl) {{
            badgeEl.textContent = "ERROR";
            badgeEl.className = "badge critical";
        }}
        console.error(e);
    }} finally {{
        if (btn) {{
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText;
        }}
    }}
}}
window.quickRestart = quickRestart;

async function checkFilebeat() {{
    const panel   = document.getElementById("statusOutputPanel");
    const titleEl = document.getElementById("statusOutputTitle");
    const badgeEl = document.getElementById("statusOutputBadge");
    const textEl  = document.getElementById("statusOutputText");
    const btn     = document.getElementById("act-test-filebeat");

    if (panel) panel.style.display = "block";
    if (titleEl) titleEl.textContent = "Testing Filebeat output...";
    if (badgeEl) {{
        badgeEl.textContent = "TESTING...";
        badgeEl.className = "badge warning";
    }}
    if (textEl) textEl.textContent = "Testing Filebeat configurations and server output connectivity...";

    if (btn) {{
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "Testing...";
    }}

    try {{
        let res = await fetch(BASE_URL + "/filebeat-test");
        let data = await res.json();

        if (titleEl) titleEl.textContent = "Filebeat Output Test";
        if (textEl) textEl.textContent = data.output || "(no output returned)";

        if (badgeEl) {{
            const ok = (data.output || "").toLowerCase().includes("talk to server...  ok") ||
                       (data.output || "").toLowerCase().includes("talk to server... ok");
            badgeEl.textContent = ok ? "OK" : "CHECK OUTPUT";
            badgeEl.className = "badge " + (ok ? "healthy" : "warning");
        }}
    }} catch (e) {{
        if (textEl) textEl.textContent = "[ERROR] Failed to query Filebeat output test.";
        if (badgeEl) {{
            badgeEl.textContent = "ERROR";
            badgeEl.className = "badge critical";
        }}
        console.error(e);
    }} finally {{
        if (btn) {{
            btn.disabled = false;
            btn.textContent = btn.dataset.originalText;
        }}
    }}
}}
window.checkFilebeat = checkFilebeat;
'''

    backup(path)
    content = content + js_block

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[DONE] Patched {path} (unified all Quick Action output into one panel)")
    return True


def main():
    project_root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROJECT_ROOT
    project_root = os.path.abspath(project_root)

    print(f"Project root: {project_root}\n")

    ok1 = patch_main_py(project_root)
    ok2 = patch_app_js(project_root)
    ok3 = patch_app_js_unify_output(project_root)

    print()
    if ok1 and ok2 and ok3:
        print("SUCCESS. Now restart your backend and hard-refresh the browser:")
        print("  1) restart the FastAPI backend (however start.sh runs it)")
        print("  2) in the browser: Ctrl+Shift+R on the portal page")
        print("  3) go to Dashboard -> Quick System Actions -> you'll see 3 new buttons")
    else:
        print("One or more files could not be patched automatically.")
        print("Check the [FAIL]/[SKIP] messages above.")


if __name__ == "__main__":
    main()
