import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const javaHome = process.env.JAVA_HOME || resolve(homedir(), '.local/share/luminous-android/jdk-21');
const androidSdk = process.env.ANDROID_SDK_ROOT || process.env.ANDROID_HOME
  || resolve(homedir(), '.local/share/luminous-android/sdk');
const versionCode = process.env.LUMINOUS_ANDROID_VERSION_CODE || '';
const versionName = process.env.LUMINOUS_ANDROID_VERSION_NAME || '';
const requiredSecrets = [
  'LUMINOUS_ANDROID_KEYSTORE',
  'LUMINOUS_ANDROID_KEY_ALIAS',
  'LUMINOUS_ANDROID_STORE_PASSWORD',
  'LUMINOUS_ANDROID_KEY_PASSWORD',
];
const environment = { ...process.env, JAVA_HOME: javaHome, ANDROID_SDK_ROOT: androidSdk };

if (!existsSync(resolve(javaHome, 'bin/java'))) throw new Error(`JDK not found at ${javaHome}`);
if (!existsSync(resolve(androidSdk, 'platforms/android-36'))) throw new Error(`Android SDK 36 not found at ${androidSdk}`);
if (!/^[1-9]\d*$/.test(versionCode)) throw new Error('LUMINOUS_ANDROID_VERSION_CODE is required and must be positive');
if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(versionName)) {
  throw new Error('LUMINOUS_ANDROID_VERSION_NAME is required and must be semantic');
}
for (const name of requiredSecrets) {
  if (!process.env[name]) throw new Error(`${name} is required for a signed release`);
}
if (!existsSync(process.env.LUMINOUS_ANDROID_KEYSTORE)) throw new Error('Android release keystore does not exist');

function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, env: environment, stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run('npm', ['run', 'android:sync']);
run('./gradlew', [
  'assembleRelease',
  `-PluminousVersionCode=${versionCode}`,
  `-PluminousVersionName=${versionName}`,
], resolve(root, 'android'));

const apkPath = resolve(root, 'android/app/build/outputs/apk/release/app-release.apk');
const apksigner = resolve(androidSdk, 'build-tools/36.0.0/apksigner');
if (!existsSync(apkPath)) throw new Error(`APK not found at ${apkPath}`);
if (!existsSync(apksigner)) throw new Error(`apksigner not found at ${apksigner}`);
run(apksigner, ['verify', '--verbose', apkPath]);

const downloadDir = resolve(root, 'apps/companion-web/companion-ui/downloads');
const publishedPath = resolve(downloadDir, 'luminous-android-release.apk');
mkdirSync(downloadDir, { recursive: true });
copyFileSync(apkPath, publishedPath);
const digest = createHash('sha256').update(readFileSync(publishedPath)).digest('hex');
console.log(`Published signed release APK to ${publishedPath}`);
console.log(`SHA-256 ${digest}`);
