#!/bin/bash
# Simple API Testing Script using curl
# Tests the running FastAPI server

echo "🧪 Testing FastAPI Server APIs"
echo "=================================="

BASE_URL="http://localhost:8000"
API_BASE="$BASE_URL/api/v1"

# Function to test an endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}
    
    echo ""
    echo "📋 Testing: $description"
    echo "   $method $API_BASE$endpoint"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$API_BASE$endpoint")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE$endpoint")
    fi
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -n1)
    # Extract response body (all but last line)
    body=$(echo "$response" | head -n -1)
    
    if [ "$status_code" = "$expected_status" ]; then
        echo "   ✅ Success: $status_code"
        echo "   📄 Response: ${body:0:100}..."
    else
        echo "   ❌ Failed: Expected $expected_status, got $status_code"
        echo "   📄 Response: ${body:0:200}..."
    fi
}

# Test basic endpoints
test_endpoint "GET" "" "Root endpoint"
test_endpoint "GET" "/slack/test" "Slack test endpoint"
test_endpoint "GET" "/auth/google/status" "Google auth status"
test_endpoint "GET" "/drive/files" "Drive files endpoint"
test_endpoint "GET" "/chat/status" "Chat service status"

echo ""
echo "=================================="
echo "🌐 Interactive Testing Options:"
echo "   • API Docs: $BASE_URL/docs"
echo "   • ReDoc: $BASE_URL/redoc"
echo "   • OpenAPI: $BASE_URL/openapi.json"
echo ""
echo "💡 Use the interactive docs to test POST endpoints and complex requests!"
