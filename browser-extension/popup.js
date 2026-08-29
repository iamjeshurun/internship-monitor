const ids = ["first", "last", "email", "phone"];
chrome.storage.local.get(ids, data => ids.forEach(id => document.getElementById(id).value = data[id] || ""));
document.getElementById("save").onclick = () => chrome.storage.local.set(Object.fromEntries(ids.map(id => [id, document.getElementById(id).value])));
document.getElementById("fill").onclick = async () => {
  const data = await chrome.storage.local.get(ids);
  const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
  await chrome.scripting.executeScript({target:{tabId:tab.id},files:["content.js"]});
  await chrome.tabs.sendMessage(tab.id,{type:"JOB_MONITOR_FILL",data});
};
