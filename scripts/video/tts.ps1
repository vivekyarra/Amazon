# Render narration segments to WAV with the Windows OneCore voice (offline, no network).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/video/tts.ps1 [-Voice "Microsoft Mark"] [-Out artifacts/video/voice]
param([string]$Voice = "Microsoft Mark", [string]$Out = "artifacts/video/voice")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$match = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -eq $Voice } | Select-Object -First 1
if ($match) { $synth.Voice = $match }
$synth.Options.SpeakingRate = 1.0
New-Item -ItemType Directory -Force $Out | Out-Null
$segments = Get-Content -Raw "scripts/video/narration.json" | ConvertFrom-Json
foreach ($seg in $segments) {
    $stream = Await ($synth.SynthesizeTextToStreamAsync($seg.text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    $size = [uint32]$stream.Size
    Await ($reader.LoadAsync($size)) ([uint32]) | Out-Null
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    [IO.File]::WriteAllBytes((Join-Path (Resolve-Path $Out) ($seg.id + ".wav")), $bytes)
    Write-Output ("{0} {1} bytes" -f $seg.id, $size)
}
