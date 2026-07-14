param(
    [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

function Assert-Header {
    param(
        [Microsoft.PowerShell.Commands.BasicHtmlWebResponseObject]$Response,
        [string]$Name
    )

    if (-not $Response.Headers[$Name]) {
        throw "En-tête de sécurité absent : $Name"
    }
}

$homeResponse = Invoke-WebRequest -Uri "$base/" -Method Get -UseBasicParsing
$health = Invoke-WebRequest -Uri "$base/api/health/live" -Method Get -UseBasicParsing

if ($homeResponse.StatusCode -ne 200 -or $health.StatusCode -ne 200) {
    throw "Le frontend ou la liveness API ne répond pas avec HTTP 200."
}

@(
    "Content-Security-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "X-Request-ID"
) | ForEach-Object { Assert-Header -Response $homeResponse -Name $_ }

Assert-Header -Response $health -Name "X-Request-ID"
Write-Host "Contrôle de sécurité réussi pour $base"
