#!/usr/bin/env bash
# Redeploy an exact public commit onto the running judge stack through SSM (no SSH, no instance replacement).
# Usage: scripts/judge-redeploy.sh <40-char-commit> [stack-name] [region]
set -euo pipefail
commit="${1:?commit sha required}"
stack="${2:-done-irl-judge}"
region="${3:-us-east-1}"
[[ "$commit" =~ ^[a-f0-9]{40}$ ]] || { echo "commit must be a full 40-char sha" >&2; exit 2; }
instance=$(aws cloudformation describe-stack-resource --region "$region" --stack-name "$stack" \
  --logical-resource-id ServiceInstance --query StackResourceDetail.PhysicalResourceId --output text)
ip=$(aws cloudformation describe-stacks --region "$region" --stack-name "$stack" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue|[0]" --output text)
host="$(echo "$ip" | tr . -).sslip.io"
read -r -d '' remote <<EOF || true
set -euo pipefail
cd /srv/done-irl/src
git fetch -q origin
git checkout -q $commit
docker build -q --build-arg ENABLE_LIVE_RUNTIME=true -f infra/local/Dockerfile -t done-irl:$commit .
grep -q '^PUBLIC_HOSTS=' /srv/done-irl/runtime.env || echo 'PUBLIC_HOSTS=$host' >> /srv/done-irl/runtime.env
if [ ! -f /srv/done-irl/config/detector.tflite ]; then
  curl --fail -sS --proto '=https' --tlsv1.2 'https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite' -o /srv/done-irl/config/detector.tflite
  echo '40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58  /srv/done-irl/config/detector.tflite' | sha256sum -c -
  chown 10001:10001 /srv/done-irl/config/detector.tflite; chmod 0600 /srv/done-irl/config/detector.tflite
fi
grep -q '^DONE_IRL_DETECTOR_MODEL=' /srv/done-irl/runtime.env || { echo DONE_IRL_DETECTOR_MODEL=/config/detector.tflite; echo DONE_IRL_DETECTOR_DOWNLOAD=0; } >> /srv/done-irl/runtime.env
sed -i -E 's#done-irl:[a-f0-9]{40}#done-irl:$commit#' /etc/systemd/system/done-irl.service
systemctl daemon-reload
systemctl restart done-irl
for i in \$(seq 1 60); do
  if docker exec done-irl python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health/ready')" >/dev/null 2>&1; then echo READY $commit; exit 0; fi
  sleep 5
done
echo NOT_READY; exit 1
EOF
params=$(python -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()]}))' <<<"$remote")
cmd=$(aws ssm send-command --region "$region" --instance-ids "$instance" --document-name AWS-RunShellScript \
  --timeout-seconds 1800 --parameters "$params" --query Command.CommandId --output text)
echo "SSM command $cmd on $instance"
aws ssm wait command-executed --region "$region" --command-id "$cmd" --instance-id "$instance" || true
aws ssm get-command-invocation --region "$region" --command-id "$cmd" --instance-id "$instance" \
  --query "[Status,StandardOutputContent,StandardErrorContent]" --output text | tail -5
curl -fsS "https://$host/health/ready" && echo
