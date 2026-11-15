#!/usr/bin/env bash
# Builds MyShot.apk on macOS or Linux. Needs Node.js 22+ and Android Studio (opened once).
set -euo pipefail
cd "$(dirname "$0")"

command -v node >/dev/null || { echo "Node.js 22+ is required: https://nodejs.org"; exit 1; }
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
[ "$NODE_MAJOR" -ge 22 ] || { echo "Node.js $NODE_MAJOR is too old. Capacitor 8 needs 22+."; exit 1; }

if [ -z "${ANDROID_HOME:-}" ]; then
  for d in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk"; do
    if [ -d "$d" ]; then export ANDROID_HOME="$d"; break; fi
  done
fi
[ -n "${ANDROID_HOME:-}" ] || { echo "Android SDK not found. Install Android Studio and open it once."; exit 1; }

# Capacitor 8 builds with JDK 21. Use the one bundled with Android Studio if needed.
if ! java -version 2>&1 | grep -qE 'version "(2[1-9]|[3-9][0-9])'; then
  for j in "/Applications/Android Studio.app/Contents/jbr/Contents/Home" "$HOME/android-studio/jbr" "/opt/android-studio/jbr" "/snap/android-studio/current/jbr"; do
    if [ -x "$j/bin/java" ]; then export JAVA_HOME="$j"; export PATH="$j/bin:$PATH"; break; fi
  done
fi

npm install
if [ ! -d android ]; then
  npx cap add android
  node scripts/patch-android.mjs
fi
npx capacitor-assets generate --android
npx cap sync android
(cd android && chmod +x gradlew && ./gradlew assembleDebug)
cp android/app/build/outputs/apk/debug/app-debug.apk ./MyShot.apk
echo ""
echo "Done: $(pwd)/MyShot.apk"
