<# 
.SYNOPSIS
    Send an email via Outlook COM automation.
.DESCRIPTION
    1. Gets a Graph API token via Azure CLI (for name-to-email lookup)
    2. Looks up the recipient's email via Microsoft Graph (if a name is provided)
    3. Sends the email via Outlook COM (uses Outlook's own auth — no extra permissions)
.PARAMETER To
    The recipient — either an email address or a person's display name to look up
.PARAMETER Subject
    The email subject line
.PARAMETER Body
    The email body text
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$To,
    
    [Parameter(Mandatory=$true)]
    [string]$Subject,
    
    [Parameter(Mandatory=$true)]
    [string]$Body
)

# Step 1: Resolve recipient email (Graph API lookup if name given)
$email = $To
if ($To -notmatch '@') {
    Write-Host "Looking up '$To' in directory..."
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

    try {
        $searchName = [System.Uri]::EscapeDataString($To)
        $url = "https://graph.microsoft.com/v1.0/users?`$search=`"displayName:$searchName`"&`$select=displayName,mail,userPrincipalName&`$top=1"
        $headers = @{
            Authorization    = "Bearer $graphToken"
            ConsistencyLevel = "eventual"
        }
        $result = Invoke-RestMethod -Uri $url -Headers $headers -Method GET

        if ($result.value.Count -eq 0) {
            Write-Host "ERROR: No user found matching '$To'"
            exit 1
        }
        
        $user = $result.value[0]
        $email = if ($user.mail) { $user.mail } else { $user.userPrincipalName }
        $displayName = $user.displayName
        Write-Host "Found: $displayName ($email)"
    } catch {
        Write-Host "ERROR: Graph API lookup failed: $_"
        exit 1
    }
}

# Step 2: Send email via Outlook COM automation
Write-Host "Sending email to $email via Outlook..."
try {
    $outlook = New-Object -ComObject Outlook.Application
    $mail = $outlook.CreateItem(0)   # 0 = olMailItem
    $mail.To = $email
    $mail.Subject = $Subject
    $mail.Body = $Body
    $mail.Send()
    
    # Release COM objects
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mail) | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($outlook) | Out-Null

    Write-Host "Email sent successfully to $email"
    Write-Host "Subject: $Subject"
} catch {
    Write-Host "ERROR: Failed to send email via Outlook: $_"
    Write-Host "Make sure Outlook desktop is installed and configured."
    exit 1
}
