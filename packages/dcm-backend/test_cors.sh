#!/bin/bash
# Test CORS headers locally

echo "Testing CORS headers on http://localhost:8000"
echo "=============================================="
echo ""

echo "Test 1: Simple GET with Origin header"
echo "=====================================0"
curl -i -X GET "http://localhost:8000/api/v1/costs/summary" \
  -H "Origin: https://dcm.alzp.tgscloud.net" \
  2>/dev/null | head -20

echo ""
echo ""
echo "Test 2: OPTIONS preflight request"
echo "=================================="
curl -i -X OPTIONS "http://localhost:8000/api/v1/pipelines" \
  -H "Origin: https://dcm.alzp.tgscloud.net" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  2>/dev/null | head -20

echo ""
echo ""
echo "✅ CORS is working if you see 'access-control-allow-origin: https://dcm.alzp.tgscloud.net' above"
