<# 
.SYNOPSIS
    Send a Teams message to a person by name using Microsoft Graph API + deep link.
.DESCRIPTION
    1. Gets a Graph API token via Azure CLI
    2. Looks up the person's email via Microsoft Graph (Invoke-RestMethod)
    3. Opens a Teams chat with the message pre-filled via deep link
    4. Presses Enter to send the message
.PARAMETER Name
    The person's display name to search for
.PARAMETER Message
    The message text to send
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$Name,
    
    [Parameter(Mandatory=$true)]
    [string]$Message
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

# Step 3: Open chat with pre-filled message via Teams deep link
$encodedMessage = [System.Uri]::EscapeDataString($Message)
$link = "msteams:/l/chat/0/0?users=$email&message=$encodedMessage"

Write-Host "Opening chat with $displayName..."
Start-Process $link

# Step 4: Wait for the chat to open, then press Enter to send
Start-Sleep -Seconds 4
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 1
Write-Host "Message sent successfully"
