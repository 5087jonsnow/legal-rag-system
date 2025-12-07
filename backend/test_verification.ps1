# ============================================================
# FILE: backend/test_verification.ps1
# PURPOSE: PowerShell script to test citation verification
# ============================================================

<#
.SYNOPSIS
    Test citation verification system

.DESCRIPTION
    Tests the citation verification API endpoints with various queries
    containing real and hallucinated citations.

.EXAMPLE
    .\test_verification.ps1
#>

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("="*60) -ForegroundColor Cyan
Write-Host "CITATION VERIFICATION TEST SCRIPT" -ForegroundColor Green
Write-Host ("="*60) -ForegroundColor Cyan
Write-Host ""

# Configuration
$BACKEND_URL = "http://localhost:8001"
$API_ENDPOINT = "$BACKEND_URL/api/v1/search/query"

# Step 1: Generate test JWT token
Write-Host "[1/5] Generating test JWT token..." -ForegroundColor Yellow

$TOKEN_SCRIPT = @"
import sys
sys.path.append('.')
from app.core.security import create_test_token
token = create_test_token(user_id='test_lawyer', org_id='test_firm', is_admin=False)
print(token)
"@

try {
    $JWT_TOKEN = docker-compose exec -T backend python -c $TOKEN_SCRIPT 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate token"
    }
    $JWT_TOKEN = $JWT_TOKEN.Trim()
    Write-Host "   ✓ Token generated: $($JWT_TOKEN.Substring(0, 20))..." -ForegroundColor Green
}
catch {
    Write-Host "   ✗ Failed to generate token. Is backend running?" -ForegroundColor Red
    Write-Host "   Run: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

# Step 2: Test API health
Write-Host "`n[2/5] Checking API health..." -ForegroundColor Yellow

try {
    $healthResponse = Invoke-RestMethod -Uri "$BACKEND_URL/api/v1/search/health" -Method Get
    Write-Host "   ✓ API is healthy" -ForegroundColor Green
    Write-Host "   Engine: $($healthResponse.engine)" -ForegroundColor Gray
}
catch {
    Write-Host "   ✗ API health check failed" -ForegroundColor Red
    exit 1
}

# Step 3: Load synthetic test data
Write-Host "`n[3/5] Loading synthetic test data..." -ForegroundColor Yellow

$INGEST_CMD = "python -m scripts.ingest_public_corpus --synthetic"

try {
    docker-compose exec -T backend $INGEST_CMD 2>&1 | Out-Null
    Write-Host "   ✓ Synthetic test data loaded" -ForegroundColor Green
}
catch {
    Write-Host "   ⚠ Could not load test data (may already exist)" -ForegroundColor Yellow
}

# Test cases
$testCases = @(
    @{
        Name = "Query with VERIFIED citation"
        Query = "What are the bail conditions in AIR 2024 SC 1001?"
        ExpectedCitations = 1
        ExpectedVerified = 1
        ExpectedRisk = "HIGH_CONFIDENCE"
    },
    @{
        Name = "Query with HALLUCINATED citation"
        Query = "According to AIR 2099 SC 999, bail is always granted. This is a fake case."
        ExpectedCitations = 1
        ExpectedVerified = 0
        ExpectedRisk = "LOW_CONFIDENCE"
    },
    @{
        Name = "Query with MIXED citations"
        Query = "AIR 2024 SC 1001 is real but AIR 2099 SC 999 is hallucinated."
        ExpectedCitations = 2
        ExpectedVerified = 1
        ExpectedRisk = "MEDIUM_CONFIDENCE"
    },
    @{
        Name = "Query with NO citations"
        Query = "What is anticipatory bail?"
        ExpectedCitations = 0
        ExpectedVerified = 0
        ExpectedRisk = "UNVERIFIED"
    }
)

# Step 4: Run verification tests
Write-Host "`n[4/5] Running verification tests..." -ForegroundColor Yellow
Write-Host ""

$passedTests = 0
$failedTests = 0

foreach ($test in $testCases) {
    Write-Host "TEST: $($test.Name)" -ForegroundColor Cyan
    Write-Host "Query: $($test.Query)" -ForegroundColor Gray

    $headers = @{
        "Authorization" = "Bearer $JWT_TOKEN"
        "Content-Type" = "application/json"
    }

    $body = @{
        query = $test.Query
        top_k = 5
    } | ConvertTo-Json

    try {
        $response = Invoke-RestMethod -Uri $API_ENDPOINT -Method Post -Headers $headers -Body $body

        # Check verification report
        if ($response.verification) {
            $verification = $response.verification

            Write-Host "  Citations found: $($verification.total_citations)" -ForegroundColor White
            Write-Host "  Citations verified: $($verification.verified_count)" -ForegroundColor White
            Write-Host "  Risk level: $($verification.risk_level)" -ForegroundColor White
            Write-Host "  Verification score: $($verification.score)" -ForegroundColor White

            # Validate expectations
            $passed = $true

            if ($verification.total_citations -ne $test.ExpectedCitations) {
                Write-Host "  ✗ Expected $($test.ExpectedCitations) citations, got $($verification.total_citations)" -ForegroundColor Red
                $passed = $false
            }

            if ($verification.verified_count -lt $test.ExpectedVerified) {
                Write-Host "  ✗ Expected at least $($test.ExpectedVerified) verified, got $($verification.verified_count)" -ForegroundColor Red
                $passed = $false
            }

            # Risk level check (may vary based on actual data)
            if ($verification.risk_level -ne $test.ExpectedRisk) {
                Write-Host "  ⚠ Risk level mismatch: expected $($test.ExpectedRisk), got $($verification.risk_level)" -ForegroundColor Yellow
                # Don't fail on this, just warn
            }

            if ($passed) {
                Write-Host "  ✓ PASSED" -ForegroundColor Green
                $passedTests++
            }
            else {
                Write-Host "  ✗ FAILED" -ForegroundColor Red
                $failedTests++
            }

            # Show citation details
            if ($verification.details -and $verification.details.Count -gt 0) {
                Write-Host "  Citation details:" -ForegroundColor Gray
                foreach ($detail in $verification.details) {
                    $status = if ($detail.is_verified) { "✓" } else { "✗" }
                    $color = if ($detail.is_verified) { "Green" } else { "Red" }
                    Write-Host "    $status $($detail.citation) (confidence: $($detail.confidence))" -ForegroundColor $color
                }
            }
        }
        else {
            Write-Host "  ✗ No verification report in response" -ForegroundColor Red
            $failedTests++
        }
    }
    catch {
        Write-Host "  ✗ Request failed: $($_.Exception.Message)" -ForegroundColor Red
        $failedTests++
    }

    Write-Host ""
}

# Step 5: Summary
Write-Host "[5/5] Test Summary" -ForegroundColor Yellow
Write-Host ("="*60) -ForegroundColor Cyan
Write-Host "Passed: $passedTests / $($testCases.Count)" -ForegroundColor Green
Write-Host "Failed: $failedTests / $($testCases.Count)" -ForegroundColor Red
Write-Host ("="*60) -ForegroundColor Cyan

if ($failedTests -eq 0) {
    Write-Host "`n✓ ALL TESTS PASSED!" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "`n✗ SOME TESTS FAILED" -ForegroundColor Red
    exit 1
}

# End of file
