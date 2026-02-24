"""Quick test: verify Azure OpenAI works via Azure AD token auth + litellm."""
import os
if "AZURE_API_BASE" not in os.environ:
    raise EnvironmentError("Set AZURE_API_BASE env var (e.g. https://<resource>.cognitiveservices.azure.com/)")
os.environ["AZURE_API_VERSION"] = "2024-12-01-preview"

import litellm
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

print("Testing Azure OpenAI via litellm + Azure AD auth...")
print(f"  Model: azure/gpt-4o")
print(f"  Endpoint: {os.environ['AZURE_API_BASE']}")
print()

# Get Azure AD token
print("🔑 Getting Azure AD token...")
credential = DefaultAzureCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")
print(f"   ✅ Token acquired (expires in {token.expires_on} epoch)")
print()

try:
    response = litellm.completion(
        model="azure/gpt-4o",
        messages=[{"role": "user", "content": "Say 'hello' in one word."}],
        max_tokens=10,
        azure_ad_token=token.token,
        api_base=os.environ["AZURE_API_BASE"],
        api_version=os.environ["AZURE_API_VERSION"],
    )
    print(f"✅ Response: {response.choices[0].message.content}")
    print(f"   Model: {response.model}")
    print(f"   Tokens: {response.usage.total_tokens}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
