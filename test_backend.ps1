$ErrorActionPreference = 'Stop'
$base = 'http://localhost:3000'
$testEmail = 'test_user@example.com'
$testPass = 'Password123'

function Assert-Status($response, $expected, $desc) {
  if ($response.StatusCode -ne $expected) {
    Write-Host "FAILED: $desc - Expected $expected, got $($response.StatusCode)"
    exit 1
  } else {
    Write-Host "PASSED: $desc"
  }
}

Write-Host '=== PUBLIC ENDPOINTS ==='
# health
$response = Invoke-RestMethod -Method Get -Uri "$base/health" -SkipHttpErrorCheck -Headers @{}
Assert-Status $response 200 'GET /health'
# unknown route
try {
  $resp = Invoke-WebRequest -Method Get -Uri "$base/unknown" -Headers @{} -ErrorAction Stop
} catch {
  $resp = $_.Exception.Response
}
Assert-Status $resp 404 'GET unknown route'

Write-Host '=== AUTHENTICATION ==='
# Cleanup previous test user if exists
try { Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/register" -Body (@{email=$testEmail;password=$testPass}|ConvertTo-Json) -ContentType 'application/json' } catch {}
# Register
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/register" -Body (@{email=$testEmail;password=$testPass}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 201 'POST /auth/register'
# Duplicate registration
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/register" -Body (@{email=$testEmail;password=$testPass}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 409 'POST /auth/register duplicate'
# Login
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/login" -Body (@{email=$testEmail;password=$testPass}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 200 'POST /auth/login'
$jwt = $response.token
# Wrong password
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/login" -Body (@{email=$testEmail;password='Wrong'}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 401 'POST /auth/login wrong password'
# Me with valid JWT
$response = Invoke-RestMethod -Method Get -Uri "$base/api/v1/auth/me" -Headers @{Authorization = "Bearer $jwt"} -SkipHttpErrorCheck
Assert-Status $response 200 'GET /auth/me valid JWT'
# Me without JWT
try { Invoke-RestMethod -Method Get -Uri "$base/api/v1/auth/me" -SkipHttpErrorCheck } catch { $resp = $_.Exception.Response }
Assert-Status $resp 401 'GET /auth/me no JWT'
# Me with invalid JWT
try { Invoke-RestMethod -Method Get -Uri "$base/api/v1/auth/me" -Headers @{Authorization = "Bearer invalidtoken"} -SkipHttpErrorCheck } catch { $resp = $_.Exception.Response }
Assert-Status $resp 401 'GET /auth/me invalid JWT'

Write-Host '=== CONVERSATIONS ==='
# Create conversation
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/conversations" -Headers @{Authorization = "Bearer $jwt"} -Body (@{title='Test Conv'}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 201 'POST /conversations'
$convId = $response.id
# List conversations
$response = Invoke-RestMethod -Method Get -Uri "$base/api/v1/conversations" -Headers @{Authorization = "Bearer $jwt"} -SkipHttpErrorCheck
Assert-Status $response 200 'GET /conversations'
# Get conversation
$response = Invoke-RestMethod -Method Get -Uri "$base/api/v1/conversations/$convId" -Headers @{Authorization = "Bearer $jwt"} -SkipHttpErrorCheck
Assert-Status $response 200 'GET /conversations/:id'
# Get messages (should be empty)
$response = Invoke-RestMethod -Method Get -Uri "$base/api/v1/conversations/$convId/messages" -Headers @{Authorization = "Bearer $jwt"} -SkipHttpErrorCheck
Assert-Status $response 200 'GET /conversations/:id/messages (empty)'
# Chat within conversation
$chatPayload = @{question='Does creatine improve athletic performance?';top_k=3;conversation_id=$convId}
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/chat" -Headers @{Authorization = "Bearer $jwt"} -Body ($chatPayload|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
Assert-Status $response 200 'POST /chat'
if (-not $response.answer) { Write-Host 'FAILED: chat answer empty'; exit 1 }
if (-not $response.sources -or $response.sources.Count -eq 0) { Write-Host 'FAILED: chat sources missing'; exit 1 }
Write-Host "PASSED: chat response contains answer and sources"
# Verify messages stored
$response = Invoke-RestMethod -Method Get -Uri "$base/api/v1/conversations/$convId/messages" -Headers @{Authorization = "Bearer $jwt"} -SkipHttpErrorCheck
Assert-Status $response 200 'GET /conversations/:id/messages after chat'
if ($response.Count -ne 2) { Write-Host "FAILED: expected 2 messages, got $($response.Count)"; exit 1 }
Write-Host "PASSED: messages stored correctly"

# Attempt to access another user's conversation (create second user)
$secondEmail = 'second_user@example.com'
$secondPass = 'Password123'
# Register second user
try { Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/register" -Body (@{email=$secondEmail;password=$secondPass}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck } catch {}
# Login second user
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/login" -Body (@{email=$secondEmail;password=$secondPass}|ConvertTo-Json) -ContentType 'application/json' -SkipHttpErrorCheck
$jwt2 = $response.token
# Attempt to get first user's conversation with second user's JWT
try { Invoke-RestMethod -Method Get -Uri "$base/api/v1/conversations/$convId" -Headers @{Authorization = "Bearer $jwt2"} -SkipHttpErrorCheck } catch { $resp = $_.Exception.Response }
Assert-Status $resp 404 'GET /conversations/:id unauthorized access'
# Attempt to delete first user's conversation with second JWT
try { Invoke-RestMethod -Method Delete -Uri "$base/api/v1/conversations/$convId" -Headers @{Authorization = "Bearer $jwt2"} -SkipHttpErrorCheck } catch { $resp = $_.Exception.Response }
Assert-Status $resp 404 'DELETE /conversations/:id unauthorized delete'

Write-Host '=== RATE LIMITING ==='
# Send 31 quick authenticated requests to a cheap endpoint (e.g., /auth/me)
for ($i=1;$i -le 31;$i++) {
  $resp = Invoke-WebRequest -Method Get -Uri "$base/api/v1/auth/me" -Headers @{Authorization = "Bearer $jwt"} -ErrorAction SilentlyContinue
  if ($i -eq 31) {
    if ($resp.StatusCode -ne 429) { Write-Host "FAILED: expected 429 on request $i"; exit 1 } else { Write-Host "PASSED: rate limit triggered on request $i" }
  }
}

Write-Host "ALL TESTS PASSED"
exit 0
