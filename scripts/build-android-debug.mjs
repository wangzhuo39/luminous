import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const javaHome = process.env.JAVA_HOME || resolve(homedir(), '.local/share/luminous-android/jdk-21');
const androidSdk = process.env.ANDROID_SDK_ROOT || process.env.ANDROID_HOME
  || resolve(homedir(), '.local/share/luminous-android/sdk');
const environment = { ...process.env, JAVA_HOME: javaHome, ANDROID_SDK_ROOT: androidSdk };
const versionCode = process.env.LUMINOUS_ANDROID_VERSION_CODE || '1';
const versionName = process.env.LUMINOUS_ANDROID_VERSION_NAME || '0.1.0';

if (!existsSync(resolve(javaHome, 'bin/java'))) throw new Error(`JDK not found at ${javaHome}`);
if (!existsSync(resolve(androidSdk, 'platforms/android-36'))) throw new Error(`Android SDK 36 not found at ${androidSdk}`);
if (!/^[1-9]\d*$/.test(versionCode)) throw new Error('LUMINOUS_ANDROID_VERSION_CODE must be a positive integer');
if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(versionName)) {
  throw new Error('LUMINOUS_ANDROID_VERSION_NAME must be a semantic version');
}

function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, env: environment, stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run('npm', ['run', 'android:sync']);
run('./gradlew', [
  'assembleDebug',
  `-PluminousVersionCode=${versionCode}`,
  `-PluminousVersionName=${versionName}`,
], resolve(root, 'android'));

const apkPath = resolve(root, 'android/app/build/outputs/apk/debug/app-debug.apk');
const downloadDir = resolve(root, 'apps/companion-web/companion-ui/downloads');
if (!existsSync(apkPath)) throw new Error(`APK not found at ${apkPath}`);
mkdirSync(downloadDir, { recursive: true });
copyFileSync(apkPath, resolve(downloadDir, 'luminous-android-debug.apk'));
console.log(`Published debug APK to ${resolve(downloadDir, 'luminous-android-debug.apk')}`);
