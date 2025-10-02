#!/bin/bash
# FastAPI Server Testing Script
# Tests all the key endpoints to ensure our /grbg implementation is working

echo "🧪 Testing FastAPI Server - /grbg Commands"
echo "=========================================="

BASE_URL="http://localhost:8000"
API_BASE="$BASE_URL/api/v1"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
        echo -e "   ${GREEN}✅ Success: $status_code${NC}"
        echo "   📄 Response: ${body:0:100}..."
    else
        echo -e "   ${RED}❌ Failed: Expected $expected_status, got $status_code${NC}"
        echo "   📄 Response: ${body:0:200}..."
    fi
}

# Test basic server health
echo "🏥 Testing Server Health"
test_endpoint "GET" "" "Root endpoint"
test_endpoint "GET" "/docs" "API Documentation" 200

# Test Slack endpoints
echo ""
echo "🤖 Testing Slack Endpoints"
test_endpoint "GET" "/slack/test" "Slack test endpoint"

# Test Auth endpoints
echo ""
echo "🔐 Testing Auth Endpoints"
test_endpoint "GET" "/auth/google/status" "Google auth status"

# Test Drive endpoints
echo ""
echo "📁 Testing Drive Endpoints"
test_endpoint "GET" "/drive/files" "Drive files endpoint"

# Test Chat endpoints
echo ""
echo "💬 Testing Chat Endpoints"
test_endpoint "GET" "/chat/status" "Chat service status"

echo ""
echo "=========================================="
echo -e "${YELLOW}🌐 Interactive Testing Options:${NC}"
echo "   • API Docs: $BASE_URL/docs"
echo "   • ReDoc: $BASE_URL/redoc"
echo "   • Frontend: http://localhost:3000"
echo ""
echo -e "${YELLOW}💡 Next Steps:${NC}"
echo "   1. Visit http://localhost:8000/docs to test API endpoints interactively"
echo "   2. Visit http://localhost:3000 to test the frontend"
echo "   3. Test Slack commands by setting up your Slack app with the webhook URL"
echo ""
echo -e "${GREEN}🎉 Testing completed!${NC}"

