$env:AZURE_API_BASE = "https://bugtotest-resource.cognitiveservices.azure.com/"
$env:AZURE_API_VERSION = "2024-12-01-preview"
$env:AGENTICOS_LLM_BASE_URL = $env:AZURE_API_BASE
$env:AGENTICOS_LLM_API_VERSION = $env:AZURE_API_VERSION

& "C:\Users\jiaqizou\AppData\Local\Microsoft\WindowsApps\python3.13.exe" scripts\run_all_demos.py
