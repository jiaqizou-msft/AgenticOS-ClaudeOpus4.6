<# 
.SYNOPSIS
    Start a Teams call to a person by name using Microsoft Graph API + deep link.
.DESCRIPTION
    1. Gets a Graph API token via Azure CLI
    2. Looks up the person's email via Microsoft Graph (Invoke-RestMethod)
    3. Starts a Teams audio/video call via deep link protocol
.PARAMETER Name
    The person's display name to search for
.PARAMETER CallType
    "audio" (default) or "video"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$Name,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("audio", "video")]
    [string]$CallType = "audio"
)

# Step 1: Get a Graph API token via Azure CLI
Write-Host "Looking up '$Name' in directory..."
try {
    $graphToken = az account get-access-token --resource https://graph.microsoft.com --query accessToken -o tsv 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to get Graph API token. Run 'az login' first."
        exit 1
    }
} catch {
    Write-Host "ERROR: Azure CLI not available: $_"
    exit 1
}

# Step 2: Search for the person via Microsoft Graph
try {
    $searchName = [System.Uri]::EscapeDataString($Name)
    $url = "https://graph.microsoft.com/v1.0/users?`$search=`"displayName:$searchName`"&`$select=displayName,mail,userPrincipalName&`$top=1"
    $headers = @{
        Authorization    = "Bearer $graphToken"
        ConsistencyLevel = "eventual"
    }
    $result = Invoke-RestMethod -Uri $url -Headers $headers -Method GET

    if ($result.value.Count -eq 0) {
        Write-Host "ERROR: No user found matching '$Name'"
        exit 1
    }
    
    $user = $result.value[0]
    $email = $user.userPrincipalName
    $displayName = $user.displayName
    Write-Host "Found: $displayName ($email)"
} catch {
    Write-Host "ERROR: Graph API lookup failed: $_"
    exit 1
}

# Step 3: Start the call via Teams deep link
if ($CallType -eq "video") {
    $link = "msteams:/l/call/0/0?users=$email&withVideo=true"
} else {
    $link = "msteams:/l/call/0/0?users=$email"
}

Write-Host "Starting $CallType call to $displayName..."
Start-Process $link
Write-Host "Call initiated successfully"
