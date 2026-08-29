# Lightweight Safari review helper

No Xcode is required. `job-monitor-autofill.user.js` runs through the open-source
Userscripts Safari manager. It appears only on pages that resemble job application
forms, fills four basic identity fields after a click, highlights sensitive fields,
and has no submit capability.

1. Install [Userscripts from the Mac App Store](https://apps.apple.com/us/app/userscripts/id1463298887?platform=mac).
2. Open Userscripts once, then enable it in **Safari > Settings > Extensions**.
3. Grant website access. For tighter privacy, allow only the application sites you
   use; **All Websites** is more convenient for varied company career domains.
4. In Userscripts, choose **New JavaScript**, paste the contents of
   `job-monitor-autofill.user.js`, and save it.
5. Open an application page and click **Review Autofill** at the bottom-right.

The identity profile is stored by Userscripts, not by each employer site. Never add
passwords, government identifiers, demographic answers, or sponsorship answers.
