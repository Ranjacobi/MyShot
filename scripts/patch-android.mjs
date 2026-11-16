// Run once after `npx cap add android`. Adds the notification permissions and
// the status-bar icon, and checks the target SDK that Google Play requires.
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const manifest = path.join(root, 'android/app/src/main/AndroidManifest.xml');
if (!fs.existsSync(manifest)) {
  console.error('לא נמצא פרויקט אנדרואיד. הריצו קודם: npx cap add android');
  process.exit(1);
}
let xml = fs.readFileSync(manifest, 'utf8');
const perms = [
  'android.permission.POST_NOTIFICATIONS',   // Android 13+: permission to show notifications
  'android.permission.SCHEDULE_EXACT_ALARM', // Android 12+: reminders at the exact minute (the user can allow or deny)
];
for (const p of perms) {
  if (!xml.includes(`"${p}"`)) xml = xml.replace('</manifest>', `    <uses-permission android:name="${p}" />\n</manifest>`);
}
// Android 11+: without this, the camera app can't be found and photo buttons open the gallery instead.
if (!xml.includes('android.media.action.IMAGE_CAPTURE')) {
  xml = xml.replace('</manifest>', '    <queries>\n        <intent>\n            <action android:name="android.media.action.IMAGE_CAPTURE" />\n        </intent>\n    </queries>\n</manifest>');
}
fs.writeFileSync(manifest, xml);
console.log('✓ הרשאות התראות ואפשרות המצלמה נוספו ל-AndroidManifest.xml');

for (const d of ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']) {
  const src = path.join(root, 'resources/android', `drawable-${d}`, 'ic_stat_myshot.png');
  const dir = path.join(root, 'android/app/src/main/res', `drawable-${d}`);
  fs.mkdirSync(dir, { recursive: true });
  fs.copyFileSync(src, path.join(dir, 'ic_stat_myshot.png'));
}
console.log('✓ אייקון ההתראות הועתק');

// Follow the phone's dark mode: WebView sets prefers-color-scheme from the activity theme.
const styles = path.join(root, 'android/app/src/main/res/values/styles.xml');
if (fs.existsSync(styles)) {
  const st = fs.readFileSync(styles, 'utf8');
  const next = st.replace(/(<style\s+name="AppTheme\.NoActionBar"\s+parent=")[^"]*(")/, '$1Theme.AppCompat.DayNight.NoActionBar$2');
  if (next !== st) fs.writeFileSync(styles, next);
  console.log('✓ ערכת הנושא עוקבת אחרי מצב כהה בטלפון');
}

// Version: APP_VERSION in www/index.html is the single source.
const html = fs.readFileSync(path.join(root, 'www/index.html'), 'utf8');
const ver = html.match(/const APP_VERSION = '(\d+)\.(\d+)\.(\d+)'/);
const gradle = path.join(root, 'android/app/build.gradle');
if (ver && fs.existsSync(gradle)) {
  const name = `${ver[1]}.${ver[2]}.${ver[3]}`, code = +ver[1] * 10000 + +ver[2] * 100 + +ver[3];
  const g = fs.readFileSync(gradle, 'utf8')
    .replace(/versionCode(\s*=?\s*)\d+/, `versionCode$1${code}`)
    .replace(/versionName(\s*=?\s*)"[^"]*"/, `versionName$1"${name}"`);
  fs.writeFileSync(gradle, g);
  console.log(`✓ גרסה ${name} (versionCode ${code})`);
}

const vars = path.join(root, 'android/variables.gradle');
if (fs.existsSync(vars)) {
  const m = fs.readFileSync(vars, 'utf8').match(/targetSdkVersion\s*=\s*(\d+)/);
  const v = m ? +m[1] : null;
  if (v && v < 36) console.warn(`⚠ targetSdkVersion = ${v}. Google Play דורש 36 ומעלה. עדכנו ב-android/variables.gradle.`);
  else if (v) console.log(`✓ targetSdkVersion = ${v}`);
}
