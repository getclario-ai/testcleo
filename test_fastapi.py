#!/usr/bin/env python3
"""
FastAPI TestClient Testing Script
Uses FastAPI's built-in TestClient to test our APIs without external dependencies
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'legacy-data-manager/backend'))

from fastapi.testclient import TestClient
from app.main import app
import json

def test_fastapi_endpoints():
    """Test FastAPI endpoints using TestClient"""
    
    print("🧪 Testing FastAPI Endpoints with TestClient")
    print("=" * 50)
    
    # Create TestClient
    client = TestClient(app)
    
    # Test cases
    test_cases = [
        {
            "method": "GET",
            "endpoint": "/",
            "description": "Root endpoint",
            "expected_status": 200
        },
        {
            "method": "GET", 
            "endpoint": "/api/v1/slack/test",
            "description": "Slack test endpoint",
            "expected_status": 200
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/auth/google/status", 
            "description": "Google auth status",
            "expected_status": 200
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/drive/files",
            "description": "Drive files endpoint", 
            "expected_status": 200
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/chat/status",
            "description": "Chat service status",
            "expected_status": 200
        },
        {
            "method": "GET",
            "endpoint": "/docs",
            "description": "API documentation",
            "expected_status": 200
        },
        {
            "method": "GET",
            "endpoint": "/openapi.json",
            "description": "OpenAPI schema",
            "expected_status": 200
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        method = test_case["method"]
        endpoint = test_case["endpoint"]
        description = test_case["description"]
        expected_status = test_case["expected_status"]
        
        print(f"\n📋 Testing: {description}")
        print(f"   {method} {endpoint}")
        
        try:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint)
            else:
                print(f"   ❌ Unsupported method: {method}")
                results.append((description, False))
                continue
            
            success = response.status_code == expected_status
            
            if success:
                print(f"   ✅ Success: {response.status_code}")
                # Show a snippet of the response
                if hasattr(response, 'json'):
                    try:
                        data = response.json()
                        if isinstance(data, dict) and len(str(data)) < 200:
                            print(f"   📄 Response: {data}")
                        else:
                            print(f"   📄 Response: {str(data)[:100]}...")
                    except:
                        print(f"   📄 Response: {response.text[:100]}...")
                else:
                    print(f"   📄 Response: {response.text[:100]}...")
            else:
                print(f"   ❌ Failed: Expected {expected_status}, got {response.status_code}")
                print(f"   📄 Response: {response.text[:200]}")
            
            results.append((description, success))
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            results.append((description, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status} - {description}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! FastAPI server is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the server configuration.")
    
    return passed == total

def test_slack_commands():
    """Test Slack command endpoints specifically"""
    
    print("\n🤖 Testing Slack Command Endpoints")
    print("=" * 50)
    
    client = TestClient(app)
    
    # Test Slack command data
    slack_command_data = {
        "text": "help",
        "channel_id": "test_channel",
        "user_id": "test_user",
        "team_id": "test_team"
    }
    
    try:
        # Test POST to commands endpoint
        response = client.post("/api/v1/slack/commands", data=slack_command_data)
        
        print(f"📋 Testing Slack Commands Endpoint")
        print(f"   POST /api/v1/slack/commands")
        
        if response.status_code in [200, 401]:  # 401 is expected without proper Slack signature
            print(f"   ✅ Endpoint accessible: {response.status_code}")
            print(f"   📄 Response: {response.text[:200]}...")
            return True
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
            print(f"   📄 Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        print("🚀 Starting FastAPI TestClient Tests")
        
        # Test basic endpoints
        basic_success = test_fastapi_endpoints()
        
        # Test Slack commands
        slack_success = test_slack_commands()
        
        overall_success = basic_success and slack_success
        
        if overall_success:
            print("\n🎉 All FastAPI tests completed successfully!")
            print("💡 You can also visit http://localhost:8000/docs for interactive testing")
        else:
            print("\n⚠️  Some tests failed. Check the server logs.")
        
        sys.exit(0 if overall_success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test setup error: {str(e)}")
        sys.exit(1)
