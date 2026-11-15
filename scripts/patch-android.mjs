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
fs.writeFileSync(manifest, xml);
console.log('✓ הרשאות התראות נוספו ל-AndroidManifest.xml');

for (const d of ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']) {
  const src = path.join(root, 'resources/android', `drawable-${d}`, 'ic_stat_myshot.png');
  const dir = path.join(root, 'android/app/src/main/res', `drawable-${d}`);
  fs.mkdirSync(dir, { recursive: true });
  fs.copyFileSync(src, path.join(dir, 'ic_stat_myshot.png'));
}
console.log('✓ אייקון ההתראות הועתק');

const vars = path.join(root, 'android/variables.gradle');
if (fs.existsSync(vars)) {
  const m = fs.readFileSync(vars, 'utf8').match(/targetSdkVersion\s*=\s*(\d+)/);
  const v = m ? +m[1] : null;
  if (v && v < 36) console.warn(`⚠ targetSdkVersion = ${v}. Google Play דורש 36 ומעלה. עדכנו ב-android/variables.gradle.`);
  else if (v) console.log(`✓ targetSdkVersion = ${v}`);
}
