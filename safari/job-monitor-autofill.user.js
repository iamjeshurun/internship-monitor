// ==UserScript==
// @name         Job Monitor Review Autofill
// @description  Fills safe resume fields for review, highlights sensitive questions, and never submits.
// @version      1.8.0
// @match        https://*/*
// @run-at       document-idle
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

(async () => {
  "use strict";
  // Run only in the top page. Application frames otherwise create duplicate UI.
  if (window.top !== window.self) return;
  if (globalThis.__jobMonitorUserscript) return;
  globalThis.__jobMonitorUserscript = true;

  // Keep the repository copy empty. A Mac-local installed copy may personalize
  // these safe resume fields without committing personal information.
  const defaultProfile = {
    first:"", last:"", email:"", phone:"", city:"", state:"", country:"",
    school:"", degree:"", major:"", graduation_month:"", graduation_year:"",
    linkedin:"", github:""
  };

  const risky = /sponsor|work.?authorization|salary|compensation|relocat|veteran|disability|gender|race|ethnic|clearance|attest|agree|signature|social.?security|ssn|date.?of.?birth|criminal/i;
  const profileRules = [
    ["first", /first.?name|given.?name/i],
    ["last", /last.?name|family.?name|surname/i],
    ["email", /e-?mail/i],
    ["phone", /phone|mobile|telephone/i],
    ["city", /current.?city|home.?city|city.?of.?residence|\bcity\b/i],
    ["state", /\bstate\b|province/i],
    ["country", /country.?of.?residence|\bcountry\b/i],
    ["school", /school|university|college|institution/i],
    ["degree", /degree|qualification/i],
    ["major", /major|field.?of.?study|discipline/i],
    ["graduation_month", /graduation.*month|expected.*month/i],
    ["graduation_year", /graduation.*year|expected.*year/i],
    ["linkedin", /linkedin/i],
    ["github", /github/i]
  ];

  const css = `
    #jm-button{position:fixed;left:18px;bottom:18px;z-index:2147483647;border:0;border-radius:999px;padding:11px 16px;background:#124e78;color:white;font:600 14px system-ui;box-shadow:0 4px 18px #0005;cursor:pointer}
    #jm-panel{position:fixed;inset:0;z-index:2147483647;background:#0008;display:grid;place-items:center;font:14px system-ui}
    #jm-card{width:min(360px,calc(100vw - 32px));background:white;color:#17202a;border-radius:14px;padding:20px;box-shadow:0 18px 60px #0008}
    #jm-card h2{margin:0 0 12px;font-size:20px} #jm-card label{display:block;margin-top:9px;font-weight:600}
    #jm-card input{width:100%;box-sizing:border-box;padding:9px;margin-top:3px;border:1px solid #aab4be;border-radius:7px}
    #jm-card input[type=checkbox]{width:auto;margin-right:7px} #jm-resume-status{font-size:12px;color:#52606d;margin-top:5px}
    #jm-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px} #jm-actions button{padding:9px 12px;border:0;border-radius:7px;cursor:pointer}
    #jm-cancel{background:#e7edf2} #jm-fill{background:#124e78;color:white} #jm-note{font-size:12px;color:#52606d;margin-top:10px}
  `;
  const style = document.createElement("style"); style.id = "jm-style"; style.textContent = css;

  const button = document.createElement("button");
  button.id = "jm-button"; button.type = "button"; button.textContent = "Review Autofill";
  button.style.cssText = "position:fixed;left:18px;bottom:18px;z-index:2147483647;border:0;border-radius:999px;padding:11px 16px;background:#124e78;color:white;font:600 14px system-ui;box-shadow:0 4px 18px #0005;cursor:pointer";
  function mountUi() {
    if (!style.isConnected) (document.head || document.documentElement).append(style);
    if (!button.isConnected) (document.body || document.documentElement).append(button);
  }
  mountUi();
  // Greenhouse and other single-page application systems can replace the body
  // after userscripts run. Keep the review control mounted across those redraws.
  new MutationObserver(mountUi).observe(document.documentElement, {childList:true, subtree:true});

  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  function fieldLabel(field) {
    const explicit = field.id ? document.querySelector(`label[for="${CSS.escape(field.id)}"]`)?.innerText : "";
    const wrapped = field.closest("label")?.innerText;
    return [field.name, field.id, field.placeholder, field.autocomplete, field.getAttribute("aria-label"), explicit, wrapped].filter(Boolean).join(" ");
  }
  function setField(field, value) {
    if (!value || field.value) return false;
    if (field instanceof HTMLSelectElement) {
      const wanted = String(value).trim().toLowerCase();
      const option = [...field.options].find(item =>
        item.value.toLowerCase() === wanted || item.text.trim().toLowerCase() === wanted
      );
      if (!option) return false;
      field.value = option.value;
    } else if (field instanceof HTMLInputElement && descriptor?.set) descriptor.set.call(field, value);
    else field.value = value;
    field.dispatchEvent(new Event("input", {bubbles:true}));
    field.dispatchEvent(new Event("change", {bubbles:true}));
    field.style.outline = "3px solid #159a9c";
    field.dataset.jobMonitorFilled = "true";
    return true;
  }
  async function loadProfile() {
    try {
      const saved = typeof GM_getValue === "function"
        ? await GM_getValue("profile", defaultProfile)
        : globalThis.GM?.getValue ? await globalThis.GM.getValue("profile", defaultProfile) : {};
      return Object.fromEntries(Object.keys(defaultProfile).map(key => [key, saved?.[key] || defaultProfile[key]]));
    } catch (_) {}
    return defaultProfile;
  }
  async function saveProfile(data) {
    try {
      if (typeof GM_setValue === "function") return await GM_setValue("profile", data);
      if (globalThis.GM?.setValue) return await globalThis.GM.setValue("profile", data);
    } catch (_) {}
  }
  async function loadResume() {
    try {
      if (typeof GM_getValue === "function") return await GM_getValue("resume", null);
      if (globalThis.GM?.getValue) return await globalThis.GM.getValue("resume", null);
    } catch (_) {}
    return null;
  }
  async function saveResume(data) {
    try {
      if (typeof GM_setValue === "function") return await GM_setValue("resume", data);
      if (globalThis.GM?.setValue) return await globalThis.GM.setValue("resume", data);
    } catch (_) {}
  }
  function readResume(file) {
    return new Promise((resolve, reject) => {
      if (!file || file.type !== "application/pdf") return reject(new Error("Choose a PDF résumé."));
      if (file.size > 5_000_000) return reject(new Error("Résumé must be smaller than 5 MB."));
      const reader = new FileReader();
      reader.onload = () => resolve({name:file.name, type:file.type, data:String(reader.result)});
      reader.onerror = () => reject(new Error("Could not read the résumé."));
      reader.readAsDataURL(file);
    });
  }
  function attachResume(resume) {
    if (!resume?.data) return 0;
    const candidates = [...document.querySelectorAll('input[type="file"]')].filter(field =>
      !field.closest("#jm-panel") && /resume|résumé|\bcv\b|curriculum.?vitae/i.test(fieldLabel(field))
    );
    const field = candidates[0];
    if (!field) return 0;
    const encoded = resume.data.split(",")[1] || "";
    const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
    const file = new File([bytes], resume.name || "resume.pdf", {type:"application/pdf"});
    const transfer = new DataTransfer(); transfer.items.add(file); field.files = transfer.files;
    field.dispatchEvent(new Event("input", {bubbles:true}));
    field.dispatchEvent(new Event("change", {bubbles:true}));
    field.style.outline = "3px solid #159a9c";
    return 1;
  }
  async function openPanel() {
    if (document.getElementById("jm-panel")) return;
    const panel = document.createElement("div"); panel.id = "jm-panel";
    panel.innerHTML = `<div id="jm-card" role="dialog" aria-modal="true"><h2>Review Autofill</h2>
      <label>First name<input id="jm-first" autocomplete="given-name"></label><label>Last name<input id="jm-last" autocomplete="family-name"></label>
      <label>Email<input id="jm-email" type="email" autocomplete="email"></label><label>Phone<input id="jm-phone" type="tel" autocomplete="tel"></label>
      <label>Saved résumé PDF<input id="jm-resume-file" type="file" accept="application/pdf,.pdf"></label>
      <div id="jm-resume-status">No résumé saved yet.</div>
      <label><input id="jm-resume-attach" type="checkbox">Attach saved résumé on this page</label>
      <div id="jm-note">Also fills saved location, education, graduation, LinkedIn, and GitHub fields. Teal fields are filled; orange fields require review. Nothing is submitted.</div>
      <div id="jm-actions"><button id="jm-cancel" type="button">Cancel</button><button id="jm-fill" type="button">Save & Fill</button></div></div>`;
    (document.body || document.documentElement).append(panel);
    const saved = await loadProfile();
    let savedResume = await loadResume();
    for (const key of ["first","last","email","phone"]) panel.querySelector(`#jm-${key}`).value = saved[key] || "";
    const resumeInput = panel.querySelector("#jm-resume-file");
    const resumeStatus = panel.querySelector("#jm-resume-status");
    if (savedResume?.name) resumeStatus.textContent = `Saved locally: ${savedResume.name}`;
    resumeInput.onchange = async () => {
      try {
        savedResume = await readResume(resumeInput.files?.[0]);
        await saveResume(savedResume);
        resumeStatus.textContent = `Saved locally: ${savedResume.name}`;
        panel.querySelector("#jm-resume-attach").checked = true;
      } catch (error) { resumeStatus.textContent = error.message; }
    };
    panel.querySelector("#jm-cancel").onclick = () => panel.remove();
    panel.onclick = event => { if (event.target === panel) panel.remove(); };
    panel.querySelector("#jm-fill").onclick = async () => {
      const data = {...saved, ...Object.fromEntries(["first","last","email","phone"].map(key => [key, panel.querySelector(`#jm-${key}`).value.trim()]))};
      await saveProfile(data);
      let filled = 0, flagged = 0;
      for (const field of [...document.querySelectorAll("input:not([type=hidden]):not([type=submit]), textarea, select")]) {
        if (field.type === "file") continue;
        const label = fieldLabel(field);
        if (risky.test(label)) { field.style.outline = "3px solid #f59e0b"; flagged++; continue; }
        const match = profileRules.find(([, regex]) => regex.test(label));
        if (match && setField(field, data[match[0]])) filled++;
      }
      const attached = panel.querySelector("#jm-resume-attach").checked ? attachResume(savedResume) : 0;
      panel.remove();
      alert(`Filled ${filled} safe résumé field${filled === 1 ? "" : "s"}. Attached ${attached} résumé. Highlighted ${flagged} field${flagged === 1 ? "" : "s"} for review. Nothing was submitted.`);
    };
  }
  button.addEventListener("click", openPanel);
})();
