# MyShot

[![Build Android APK](https://github.com/Ranjacobi/MyShot/actions/workflows/build-apk.yml/badge.svg)](https://github.com/Ranjacobi/MyShot/actions/workflows/build-apk.yml)

Personal tracker for weight-loss medications: doses, reminders, nutrition, supplements and doctor reports. A Hebrew (RTL) Android app built with [Capacitor 8](https://capacitorjs.com).

> MyShot is a personal journal, not a medical device. Dosing decisions belong to your doctor.

[מדריך בעברית](README.he.md)

## Features

- **Your medication.** Weekly injections (Mounjaro, Zepbound, Wegovy, Ozempic), a daily injection (Saxenda), pills (Wegovy pill, Ozempic pill, Rybelsus, Foundayo, Contrave/Mysimba, Xenical/orlistat), or a custom medication. Each comes with its own dose steps, missed-dose rule, minimum gap between doses, storage notes and pen or pack type, taken from the official prescribing information.
- **Reminders.** Notifications for the dose, a follow-up if it wasn't logged, the evening before, supplements, water, a weekly weigh-in, and low stock or an expiring pen. Buttons on the notification log the dose or snooze it for an hour.
- **Injections.** Site rotation on a body map, the dose ladder, the dose plan from your doctor, and an estimated medication-level chart for weekly injections.
- **Nutrition.** Log meals from a photo, a nutrition label, free text or by hand. Save recipes, and track daily protein, fiber, calories and water.
- **Supplements.** What to take and when, by day of the week, with stock tracking. Protein shakes count toward daily protein.
- **Tracking.** Side effects by day of the injection cycle, weight and BMI, progress photos with side-by-side comparison, and 7- and 30-day summaries.
- **Receipts.** Photograph a receipt and, with an AI key, the date, amount, vendor and category fill in automatically.
- **For the doctor.** A PDF report, a text summary and a list of questions for the next visit.
- **Private.** All data stays on the phone. Backups and reports leave only through the Android share sheet.

## Get the APK

Every push to `main` builds a debug APK with GitHub Actions:

1. Open [Actions](https://github.com/Ranjacobi/MyShot/actions) and the latest **Build Android APK** run.
2. Under **Artifacts**, download **MyShot-apk** and unzip it.
3. Copy `MyShot.apk` to the phone, open it and allow installs from that source.

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

Reminders are scheduled on the phone, so they arrive when the app is closed and offline. They're rescheduled after every change, so a follow-up never fires once the dose is logged. Turn each type on or off in **Settings → תזכורות**.

- The app asks for notification permission on first launch (Android 13+).
- On Android 14+, exact-time alarms need extra approval. Settings has a button for it; without it, Android may delay a reminder by a few minutes.
- Some manufacturers stop notifications from apps they consider idle. If reminders don't arrive, exclude MyShot from battery optimization.

## AI features (optional)

Receipt auto-fill, meal photo and label analysis, and meal ideas work with your own API key from one of three providers. Pick one in **Settings → בינה מלאכותית**, paste the key and tap **בדיקת החיבור** to check it.

| Provider | Get a key | Default models (photos / meal ideas) |
|---|---|---|
| Claude (Anthropic) | console.anthropic.com | `claude-sonnet-5-5` / `claude-haiku-5-5` |
| ChatGPT (OpenAI) | platform.openai.com/api-keys | `gpt-6-sol` / `gpt-6-luna` |
| Gemini (Google) | aistudio.google.com/apikey | `gemini-3.8-flash` / `gemini-3.5-flash-lite` |

You can set a different model for each provider on the same screen, for example when a newer one comes out. API usage is billed by the provider.

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
