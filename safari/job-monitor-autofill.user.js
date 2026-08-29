// ==UserScript==
// @name         Job Monitor Review Autofill
// @description  Fills basic identity fields for review, highlights sensitive questions, and never submits.
// @version      1.0.0
// @match        https://*/*
// @run-at       document-idle
// @inject-into  content
// @grant        GM.getValue
// @grant        GM.setValue
// @noframes
// ==/UserScript==

(async () => {
  "use strict";
  if (globalThis.__jobMonitorUserscript) return;
  globalThis.__jobMonitorUserscript = true;

  const fields = [...document.querySelectorAll("input:not([type=hidden]):not([type=submit]), textarea, select")];
  const pageText = `${document.title} ${location.hostname} ${document.body?.innerText?.slice(0, 4000) || ""}`;
  const looksLikeApplication = fields.length >= 3 && /apply|application|candidate|career|job|resume|résumé/i.test(pageText);
  if (!looksLikeApplication) return;

  const risky = /sponsor|work.?authorization|salary|compensation|relocat|veteran|disability|gender|race|ethnic|clearance|attest|agree|signature|social.?security|ssn|date.?of.?birth|criminal/i;
  const identityRules = [
    ["first", /first.?name|given.?name/i],
    ["last", /last.?name|family.?name|surname/i],
    ["email", /e-?mail/i],
    ["phone", /phone|mobile|telephone/i]
  ];

  const css = `
    #jm-button{position:fixed;right:18px;bottom:18px;z-index:2147483647;border:0;border-radius:999px;padding:11px 16px;background:#124e78;color:white;font:600 14px system-ui;box-shadow:0 4px 18px #0005;cursor:pointer}
    #jm-panel{position:fixed;inset:0;z-index:2147483647;background:#0008;display:grid;place-items:center;font:14px system-ui}
    #jm-card{width:min(360px,calc(100vw - 32px));background:white;color:#17202a;border-radius:14px;padding:20px;box-shadow:0 18px 60px #0008}
    #jm-card h2{margin:0 0 12px;font-size:20px} #jm-card label{display:block;margin-top:9px;font-weight:600}
    #jm-card input{width:100%;box-sizing:border-box;padding:9px;margin-top:3px;border:1px solid #aab4be;border-radius:7px}
    #jm-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px} #jm-actions button{padding:9px 12px;border:0;border-radius:7px;cursor:pointer}
    #jm-cancel{background:#e7edf2} #jm-fill{background:#124e78;color:white} #jm-note{font-size:12px;color:#52606d;margin-top:10px}
  `;
  const style = document.createElement("style"); style.textContent = css; document.documentElement.append(style);

  const button = document.createElement("button");
  button.id = "jm-button"; button.type = "button"; button.textContent = "Review Autofill";
  document.documentElement.append(button);

  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  function fieldLabel(field) {
    const explicit = field.id ? document.querySelector(`label[for="${CSS.escape(field.id)}"]`)?.innerText : "";
    const wrapped = field.closest("label")?.innerText;
    return [field.name, field.id, field.placeholder, field.autocomplete, field.getAttribute("aria-label"), explicit, wrapped].filter(Boolean).join(" ");
  }
  function setField(field, value) {
    if (!value || field.value) return false;
    if (field instanceof HTMLInputElement && descriptor?.set) descriptor.set.call(field, value); else field.value = value;
    field.dispatchEvent(new Event("input", {bubbles:true}));
    field.dispatchEvent(new Event("change", {bubbles:true}));
    field.style.outline = "3px solid #159a9c";
    field.dataset.jobMonitorFilled = "true";
    return true;
  }
  async function openPanel() {
    const saved = await GM.getValue("identity", {first:"", last:"", email:"", phone:""});
    const panel = document.createElement("div"); panel.id = "jm-panel";
    panel.innerHTML = `<div id="jm-card" role="dialog" aria-modal="true"><h2>Review Autofill</h2>
      <label>First name<input id="jm-first" autocomplete="given-name"></label><label>Last name<input id="jm-last" autocomplete="family-name"></label>
      <label>Email<input id="jm-email" type="email" autocomplete="email"></label><label>Phone<input id="jm-phone" type="tel" autocomplete="tel"></label>
      <div id="jm-note">Stored only in the Userscripts extension. Teal fields are filled; orange fields require review. Nothing is submitted.</div>
      <div id="jm-actions"><button id="jm-cancel" type="button">Cancel</button><button id="jm-fill" type="button">Save & Fill</button></div></div>`;
    document.documentElement.append(panel);
    for (const key of ["first","last","email","phone"]) panel.querySelector(`#jm-${key}`).value = saved[key] || "";
    panel.querySelector("#jm-cancel").onclick = () => panel.remove();
    panel.onclick = event => { if (event.target === panel) panel.remove(); };
    panel.querySelector("#jm-fill").onclick = async () => {
      const data = Object.fromEntries(["first","last","email","phone"].map(key => [key, panel.querySelector(`#jm-${key}`).value.trim()]));
      await GM.setValue("identity", data);
      let filled = 0, flagged = 0;
      for (const field of [...document.querySelectorAll("input:not([type=hidden]):not([type=submit]), textarea, select")]) {
        const label = fieldLabel(field);
        if (risky.test(label)) { field.style.outline = "3px solid #f59e0b"; flagged++; continue; }
        const match = identityRules.find(([, regex]) => regex.test(label));
        if (match && setField(field, data[match[0]])) filled++;
      }
      panel.remove();
      alert(`Filled ${filled} safe identity field${filled === 1 ? "" : "s"}. Highlighted ${flagged} field${flagged === 1 ? "" : "s"} for review. Nothing was submitted.`);
    };
  }
  button.addEventListener("click", openPanel);
})();
