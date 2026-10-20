#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export JAVA_HOME="${JAVA_HOME:-/workspace/.tools/jdk21/jdk-21.0.12.1}"
export ANDROID_HOME="${ANDROID_HOME:-/workspace/.tools/android-sdk}"
export ANDROID_USER_HOME="${ANDROID_USER_HOME:-/workspace/.tools/android-home}"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-/workspace/.tools/gradle-home}"
# The cloud proxy hostname/port are reused without exposing any credential values.
python3 - <<'PY'
import os,subprocess,urllib.parse
from pathlib import Path
if not (Path(os.environ['JAVA_HOME'])/'bin/javac').is_file():
    raise SystemExit('A full JDK is required. See apps/firetv-command-hud/README.md.')
args=['/workspace/.tools/gradle-8.13/bin/gradle','-p','apps/firetv-command-hud','assembleDebug','--no-daemon','--max-workers=2','-Duser.home=/workspace/.tools/java-home']
trust=Path('/etc/ssl/certs/java/cacerts')
if trust.exists():args+=['-Djavax.net.ssl.trustStore='+str(trust)]
p=urllib.parse.urlsplit(os.getenv('HTTPS_PROXY') or '')
if p.hostname:
    for protocol in ('http','https'):
        args += [f'-D{protocol}.proxyHost={p.hostname}',f'-D{protocol}.proxyPort={p.port or 80}']
raise SystemExit(subprocess.call(args))
PY
