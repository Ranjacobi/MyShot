@echo off
rem Builds MyShot.apk on Windows. Needs Node.js 22+ and Android Studio (opened once).
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 22+ is required: https://nodejs.org
  exit /b 1
)
if "%ANDROID_HOME%"=="" if exist "%LOCALAPPDATA%\Android\Sdk" set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
if "%ANDROID_HOME%"=="" (
  echo Android SDK not found. Install Android Studio and open it once.
  exit /b 1
)
rem Capacitor 8 builds with JDK 21, which Android Studio bundles.
if exist "%ProgramFiles%\Android\Android Studio\jbr\bin\java.exe" set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"

call npm install
if errorlevel 1 exit /b 1
if not exist android (
  call npx cap add android
  if errorlevel 1 exit /b 1
  call node scripts\patch-android.mjs
  if errorlevel 1 exit /b 1
)
call npx capacitor-assets generate --android
if errorlevel 1 exit /b 1
call npx cap sync android
if errorlevel 1 exit /b 1
pushd android
call gradlew.bat assembleDebug
if errorlevel 1 (
  popd
  exit /b 1
)
popd
copy /y android\app\build\outputs\apk\debug\app-debug.apk MyShot.apk >nul
echo.
echo Done: %CD%\MyShot.apk
