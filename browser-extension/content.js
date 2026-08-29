if (!globalThis.__jobMonitorInstalled) {
  globalThis.__jobMonitorInstalled = true;
  chrome.runtime.onMessage.addListener(message => {
    if (message.type !== "JOB_MONITOR_FILL") return;
    const rules = [
      [message.data.first, /first.?name/i], [message.data.last, /last.?name|surname/i],
      [message.data.email, /e-?mail/i], [message.data.phone, /phone|mobile/i]
    ];
    const fields = [...document.querySelectorAll("input:not([type=hidden]), textarea, select")];
    for (const field of fields) {
      const label = [field.name, field.id, field.placeholder, field.getAttribute("aria-label"), document.querySelector(`label[for="${CSS.escape(field.id)}"]`)?.innerText].filter(Boolean).join(" ");
      const match = rules.find(([value, regex]) => value && regex.test(label));
      if (match && !field.value) {
        field.value = match[0]; field.dispatchEvent(new Event("input", {bubbles:true})); field.dispatchEvent(new Event("change", {bubbles:true})); field.style.outline = "2px solid #1b9aaa";
      } else if (/sponsor|authorization|salary|relocat|veteran|disability|gender|race|clearance|attest|agree/i.test(label)) {
        field.style.outline = "3px solid #f59e0b";
      }
    }
    alert("Safe identity fields filled in teal. Orange fields require your review. Nothing was submitted.");
  });
}
