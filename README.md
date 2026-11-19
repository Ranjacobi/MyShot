# MyShot

[![Build Android APK](https://github.com/Ranjacobi/MyShot/actions/workflows/build-apk.yml/badge.svg)](https://github.com/Ranjacobi/MyShot/actions/workflows/build-apk.yml)

Personal tracker for weight-loss medications: doses, reminders, nutrition, supplements and doctor reports. A Hebrew (RTL) Android app built with [Capacitor 8](https://capacitorjs.com).

> MyShot is a personal journal, not a medical device. Dosing decisions belong to your doctor.

[מדריך בעברית](README.he.md)

## Features

- **Your medication.** Weekly injections (Mounjaro, Zepbound, Wegovy, Ozempic), a daily injection (Saxenda), pills (Wegovy pill, Ozempic pill, Rybelsus, Foundayo, Contrave/Mysimba, Xenical/orlistat), or a custom medication. Each comes with its own dose steps, missed-dose rule, minimum gap between doses, storage notes and pen or pack type, taken from the official prescribing information.
- **Reminders.** Notifications for the dose, a follow-up if it wasn't logged, the evening before, supplements, water, a weekly weigh-in, low stock or an expiring pen, and a weekly backup. Add your own reminders too, such as a blood test or a doctor's appointment. Buttons on the notification log the dose or snooze it for an hour.
- **Injections.** Site rotation on a body map, the dose ladder, the dose plan from your doctor, and an estimated medication-level chart for weekly injections.
- **Nutrition.** Log meals from a photo (camera or gallery), a nutrition label, free text or by hand. The AI's estimates stay editable item by item, and a retake replaces the last detection. Save recipes, and track daily protein, fiber, calories and water.
- **Supplements.** Photograph a supplement and the AI reads the label: what it contributes, how it fits weight loss and your medication, the label dose, and when to take it, including around a workout. The app adds its own safety checks on top: fat burners and stimulants, laxatives and diuretics, St. John's wort, spacing for fiber and for calcium with iron, and the 30-minute wait after empty-stomach pills. It then joins your schedule with reminders, and logging a meal reminds you of the supplements that go with it. Stock tracking, and protein shakes count toward daily protein.
- **Tracking.** Side effects by day of the injection cycle, weight and BMI, progress photos with side-by-side comparison, and 7- and 30-day summaries.
- **Training and steps.** Log strength, cardio and walks, see strength sessions against a weekly goal (strength training helps keep muscle while losing weight), and track daily steps with a 7-day chart. Optional workout reminders on the days you choose.
- **Receipts.** Photograph a receipt and, with an AI key, the date, amount, vendor and category fill in automatically.
- **For the doctor.** A PDF report, a text summary and a list of questions for the next visit.
- **Light and dark.** Follows the phone's setting, or switch in one tap with the sun/moon button in the header.
- **Private.** All data stays on the phone. Notifications are discreet by default: the lock screen shows only "MyShot", never the medication or dose. An optional app lock with a PIN and fingerprint (or the phone's screen lock). Backups go to Google Drive automatically once a day, or through the share sheet.

## Get the APK

Every push to `main` builds a debug APK with GitHub Actions:

1. Open [Actions](https://github.com/Ranjacobi/MyShot/actions) and the latest **Build Android APK** run.
2. Under **Artifacts**, download **MyShot-apk** and unzip it.
3. Copy `MyShot.apk` to the phone, open it and allow installs from that source.

Each build is also published under [Releases](https://github.com/Ranjacobi/MyShot/releases). On the phone, this link always downloads the newest APK (sign in to GitHub first, since the repository is private): https://github.com/Ranjacobi/MyShot/releases/latest/download/MyShot.apk

To build without pushing: **Actions → Build Android APK → Run workflow**.

All cloud builds are signed with the same debug key (`ci/debug-signing.p12`), so a new APK installs over the previous one and keeps the data. Keep this repository **private**: anyone with that key can sign an APK that installs as an update of MyShot.

## Build locally

Requires Node.js 22+ and Android Studio, which bundles JDK 21.

```bash
./build-apk.sh    # macOS or Linux
build-apk.cmd     # Windows
```

The script installs dependencies, creates the Android project on the first run and writes `MyShot.apk` to the project folder. Local builds are signed with your own debug key, so don't mix local and cloud builds on the same phone.

To work in Android Studio instead:

```bash
npm install
npm run android:init    # first time only
npx cap open android
```

After editing `www/index.html`, run `npx cap sync android`.

## Reminders

Reminders are scheduled on the phone, so they arrive when the app is closed and offline. They're rescheduled after every change, so a follow-up never fires once the dose is logged.

Manage them on the **עוד → תזכורות** screen: switch each type on or off, set its times, add your own reminders (one-time, daily, on chosen weekdays or monthly), see what's coming up, and send a test notification.

- The app asks for notification permission on first launch (Android 13+).
- On Android 14+, exact-time alarms need extra approval. Settings has a button for it; without it, Android may delay a reminder by a few minutes.
- Some manufacturers stop notifications from apps they consider idle. If reminders don't arrive, exclude MyShot from battery optimization.

## MyShot Plus

MyShot is free, with an optional **MyShot Plus** subscription (monthly or yearly, with a free trial). Safety, tracking and the user's own data are never behind the subscription.

- **Free:** doses, injections and every reminder, missed-dose rules, the guide and warning signs, the duplicate-dose check, the home ring and level chart, injection sites, side effects, weight, manual nutrition, supplements, workouts and steps, lock and discreet notifications, manual backup and export, all five languages, the text summary for the doctor, 5 AI recognitions a month and 3 reminders of your own. Your own AI key keeps working as an advanced option.
- **Plus:** AI included with no key (meal and label photos, supplement scans, receipts, meal ideas), automatic daily backup to Google Drive, the PDF report with charts, side-effect insights, progress photo comparison, receipts and insurance refunds, and unlimited reminders of your own.
- When a subscription ends, the data stays and can always be exported; only the Plus features stop.
- **Where Plus appears:** a card at the top of Settings, a full-screen Plus screen when a Plus feature is tapped (with the reason), *Plus* badges on those features, a dismissible card on the home screen from the third launch, and once after the first setup. The Plus screen follows the common layout of top subscription apps: two plan cards with the yearly plan pre-selected (with its saving and monthly price), how the free trial works (today, a reminder two days before it ends, the first charge), a fixed button with the exact charge under it, and *Restore purchase*. The app really sends that reminder before the trial ends.
- **Builds without the RevenueCat key** (the development builds from GitHub) show everything as a preview: the Plus screen has a *Development build* box to switch between *All open* (the default, so nothing is locked), *As a free user* and *As a subscriber*, and *Start free trial* simulates a subscription instead of buying.

### Setting it up

1. **Signing key for Play.** Create an upload key once and keep the file and passwords safe:
   `keytool -genkeypair -v -keystore myshot-upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000`
   In GitHub → Settings → Secrets and variables → Actions, add the secrets `ANDROID_KEYSTORE_BASE64` (`base64 -i myshot-upload.jks | pbcopy`), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`upload`) and `ANDROID_KEY_PASSWORD`. Each build then also produces `MyShot-release.aab` (the *MyShot-release* artifact).
2. **RevenueCat** (free up to a monthly revenue threshold): create a project, add a Google Play app with the package `com.itranstudios.myshot`, and connect the Play service credentials as RevenueCat's guide describes. Create the entitlement `plus`. Copy the **public SDK key** (starts with `goog_`) into the GitHub repository variable `REVENUECAT_ANDROID_KEY`. The next build includes the subscription and the billing permission.
3. **Google Play Console.** Upload that AAB to *Internal testing*. Then, under Monetize → Subscriptions, create `myshot_plus` with two base plans, `monthly` and `yearly`, and add a free-trial offer to the yearly plan. Set up the payments profile if Play asks for it. In RevenueCat, import the two products, attach them to the `plus` entitlement, and create the offering `default` with the Monthly and Annual packages.
4. **The AI server** (Cloudflare Workers, in `proxy/`):
   ```
   cd proxy
   npx wrangler login
   npx wrangler kv namespace create QUOTA        # put the id it prints into wrangler.toml
   npx wrangler secret put GEMINI_API_KEY        # a Gemini key with billing enabled
   npx wrangler secret put RC_SECRET             # RevenueCat secret API key (starts with sk_)
   npx wrangler deploy
   ```
   Put the address it prints (for example `https://myshot-ai.<name>.workers.dev`) into the repository variable `MYSHOT_AI_URL`. Limits are set in `wrangler.toml` (`FREE_LIMIT = 5`, `PLUS_LIMIT = 300` a month). The free Cloudflare plan limits KV writes per day, which is enough to start with.
5. **Test the purchase.** In Play Console → Settings → License testing, add your Gmail address, install the app from the internal testing link, and buy: test purchases are free and renew quickly. Check that Plus opens the features, that *Restore purchase* works, and that cancelling in Google Play keeps access until the end of the period.

Before publishing, the store listing needs a privacy policy and subscription terms; the paywall already states that the subscription renews automatically and can be cancelled anytime in Google Play.

## Language

**Settings → שפה · Language** switches between **עברית**, **English**, **Русский**, **Español** and **Français**; the app reloads in the chosen language. The same choice appears on the welcome screen. A new install follows the phone's language (Hebrew, Russian, Spanish or French, and English for anything else); an existing install stays in Hebrew until you switch.

- **English** is complete: the interface, the medical guide, the medication and missed-dose rules, the supplement tips and the PDF report (laid out left to right). Where the Hebrew names an Israeli service, the English says it generally and gives the Israeli number in parentheses, for example “your local emergency number (in Israel: MDA 101)”.
- **Russian, Spanish and French** cover the interface: screens, buttons, settings, notifications and messages, and AI answers (meal and food names, supplement explanations, meal ideas) come back in the chosen language. **The medical content stays in English** on purpose: the guide, dose and missed-dose rules, warning signs, supplement safety rules, the duplicate-dose warnings and the PDF report. Anything without a translation falls back to English, then to Hebrew.
- Text you typed yourself, such as supplement names and notes, stays as you wrote it.

The translations live in `www/i18n-en.js`, `i18n-ru.js`, `i18n-es.js` and `i18n-fr.js`, keyed by the Hebrew source text. They were made without a native-speaker review, so have one done before publishing in those markets.

## First launch

A new install opens with three choices: **שחזור מ-Google Drive** (sign in, and the app finds its latest backup in your Drive and restores it), **בחירת קובץ גיבוי** (pick a backup file from the phone, Drive or anywhere else), or **להתחיל מחדש** (the short medication setup). Nothing is replaced without asking, and a new install has nothing to replace, so the restore runs straight away. Right after the restore or the setup, the app offers once to lock itself with fingerprint or a code; **לא עכשיו** skips it, and it can be set later in Settings → פרטיות ונעילה.

The automatic Drive search sees only backups the app saved itself (the daily Drive backup), because of the `drive.file` permission, and it works once the Google setup below is done. Until then, the Drive button opens the file picker, where Drive is one of the sources. A backup saved through the share sheet is chosen with **בחירת קובץ גיבוי**.

## Backup to Google Drive

There are two ways, and both restore through **Settings → שחזור מגיבוי** or **שחזור מ-Drive**.

**Share sheet (works out of the box).** **Settings → גיבוי ונתונים → גיבוי ל-Google Drive** opens the Android share sheet with a backup file; choose Drive and a folder. The weekly backup reminder on the reminders screen has a **גיבוי עכשיו** button that does the same.

**Automatic daily backup (one-time setup).** The app signs in to your Google account once and then saves a backup every day to a **MyShot** folder in your Drive, silently, when you open the app. It keeps the last 14 backups and can only see files it created itself (the `drive.file` permission). This part is added to the build only after you set it up; until then builds are unchanged.

1. In [Google Cloud Console](https://console.cloud.google.com), create a project (for example *MyShot*).
2. **APIs & Services → Library**: enable **Google Drive API**.
3. **Google Auth Platform**: set the app name and support email, choose **External**, add your Gmail address under **Audience → Test users**, and add the scope `.../auth/drive.file` under **Data access**.
4. **Clients → Create client → Web application**. Copy its client ID (it ends with `.apps.googleusercontent.com`).
5. **Clients → Create client → Android**: package name `com.itranstudios.myshot`, SHA-1 `7C:C8:3B:70:05:C6:7E:AA:49:55:CC:77:B9:F9:46:EE:B9:41:01:61` (the key that signs the APKs from GitHub Actions). If you later build a signed release or publish to Google Play, add another Android client with that key's SHA-1 too (for Play, the App signing key from Play Console → App integrity).
6. In this repository: **Settings → Secrets and variables → Actions → Variables → New repository variable**, name `GOOGLE_WEB_CLIENT_ID`, value: the **Web** client ID from step 4 (not the Android one).
7. Run the workflow again (any push, or **Actions → Run workflow**), install the new APK, and in the app tap **Settings → גיבוי ונתונים → גיבוי אוטומטי ל-Google Drive**.

While the consent screen is in *Testing*, Google may ask you to sign in again from time to time; if the automatic backup stops, tap **גיבוי עכשיו** to reconnect. Google Cloud changes can take a few hours to apply.

## App lock and discreet notifications

- **Discreet notifications** are on by default (Settings → פרטיות ונעילה). Notifications use private channels, so on a secured lock screen Android hides their content, and the text never names the medication or dose.
- **App lock** (Settings → פרטיות ונעילה) is optional, with one method: a 4–6 digit **PIN** (stored only as a salted hash), or **fingerprint**, with the phone's own screen lock as the fallback. Changing or removing the lock asks for the current method first. Lock immediately, after a minute or after 5 minutes. Coming back from the app's own camera, share sheet, file picker, Google sign-in or the fingerprint prompt does not lock it again. A notification tapped while locked waits until you unlock. If you forget the PIN, the only way back in is clearing the app's data, so keep a backup.

## AI features (optional)

Receipt auto-fill, meal photo and label analysis, and meal ideas work with your own API key from one of three providers. Pick one in **Settings → בינה מלאכותית**, paste the key and tap **בדיקת החיבור** to check it.

| Provider | Get a key | Models offered (the cheapest that read images) |
|---|---|---|
| Claude (Anthropic) | console.anthropic.com | Haiku family, now Claude Haiku 5.5 |
| ChatGPT (OpenAI) | platform.openai.com/api-keys | Luna and Nano families, now GPT-6 Luna |
| Gemini (Google) | aistudio.google.com/apikey | Flash-Lite family, now Gemini 3.5 Flash-Lite |

The model is picked from a list, never typed. With your key, the app reads the provider's current model list, keeps only these cheapest image-capable families, newest first, and refreshes it every few days. **אוטומטי** always uses the newest one, so a new model shows up without an app update. If a chosen model is retired, or a Gemini model hits its free-tier limit, the app retries once with the next model in the list. API usage is billed by the provider.

Keys are stored only on the phone, one per provider, and aren't included in backups. A photo is sent to the selected provider only when you ask to analyze it. On Android, requests go through Capacitor's native HTTP, so they don't depend on browser CORS rules. Without a key, everything else works as usual.

Personal keys suit personal use. For a public release, keep the keys on a small server and point `aiClient` in `www/index.html` at it.

## Google Play release

Google Play needs an AAB signed with your own upload key, and new apps must target Android 16 (API 36). Capacitor 8 targets 36, and `scripts/patch-android.mjs` checks it.

1. Create an upload key once, and back it up. Without it you can't update the app on Play.
   ```bash
   keytool -genkeypair -keystore myshot-release.jks -alias myshot -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Add four secrets under **Settings → Secrets and variables → Actions**:
   - `ANDROID_KEYSTORE_BASE64`: the keystore in base64 (`base64 -i myshot-release.jks | pbcopy` on macOS)
   - `ANDROID_KEYSTORE_PASSWORD`
   - `ANDROID_KEY_ALIAS`: `myshot`
   - `ANDROID_KEY_PASSWORD`
3. From the next run, **Artifacts** also has **MyShot-release** with a signed APK and AAB.

Never commit the release keystore; `.gitignore` already excludes `*.jks`. The package ID is `com.itranstudios.myshot`. To change it, edit `capacitor.config.json` before the first Play upload, because it can't change afterwards.

## Automated checks

Every push first runs `tests/run_tests.py` in GitHub Actions (the **test** job): the app loads in headless Chromium with the Android plugins, AI providers and Google Drive mocked, and 39 checks cover reminders and discreet notifications, logging a dose from a notification (and the duplicate-dose guard), the back button, backup and restore, receipt and meal recognition, the model list and fallback, supplement scanning and its safety rules, the meal-to-supplement prompt, the app lock with a PIN and with fingerprint, the settings pages, the first-launch restore (Drive, a file, or starting fresh) and the lock offer, MyShot Plus (the paywall, buying and restoring, the locked features, MyShot AI and its free quota, and development builds staying open), the English, Russian, Spanish and French interfaces (no Hebrew left on any screen, the phone's language on a new install, switching back and forth, the guide and the PDF report), training and steps, Drive backup and retention, and layout at 360 px. **The APK is built only if every check passes**, so an update that breaks something never reaches the phone.

To run them on your computer: `python3 -m pip install playwright && python3 -m playwright install chromium && python3 tests/run_tests.py`

## Version

The version lives in one place: `APP_VERSION` in `www/index.html`. On every build, `scripts/patch-android.mjs` copies it to Android as `versionName`, with `versionCode` = major × 10000 + minor × 100 + patch (1.4.0 → 10400), so each release is higher than the last. Each Release is also titled with it.

To release a new version, bump `APP_VERSION`, add a line at the top of `CHANGELOG` in the same file (it shows in the app's About screen), and push.

## Project structure

| Path | What it is |
|---|---|
| `www/index.html` | The whole app: HTML, CSS and JavaScript in one file |
| `capacitor.config.json` | App name, package ID and plugin settings |
| `.github/workflows/build-apk.yml` | Cloud build |
| `build-apk.sh`, `build-apk.cmd` | One-command local build |
| `scripts/patch-android.mjs` | Adds notification permissions and the status-bar icon, and checks the target SDK |
| `assets/` | Sources for the launcher icon and splash screens |
| `resources/android/` | Notification icon |
| `store/` | Play Store icon (512 px) and feature graphic (1024×500) |
| `ci/debug-signing.p12` | Fixed debug key for cloud builds |

## Medical information

Medication rules such as dose steps, missed doses and storage come from the official prescribing information and are shown for reference. The level chart is an estimate based on published pharmacokinetics, not a blood test. Always follow your doctor and the leaflet that came with your medication.
