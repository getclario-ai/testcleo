#!/usr/bin/env python3
"""
API Testing Script for Legacy Data Manager
Tests the basic API endpoints to ensure they're working correctly
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

def test_endpoint(method, endpoint, description, data=None, headers=None):
    """Test a single endpoint and return results"""
    url = f"{API_BASE}{endpoint}" if endpoint.startswith('/') else f"{API_BASE}/{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=5)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=5)
        else:
            return False, f"Unsupported method: {method}"
        
        success = response.status_code < 400
        return success, f"{response.status_code} - {response.text[:200]}"
        
    except requests.exceptions.ConnectionError:
        return False, "Connection failed - server not running?"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    print("🧪 Testing Legacy Data Manager APIs")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        ("GET", "", "Root endpoint", None),
        ("GET", "/slack/test", "Slack test endpoint", None),
        ("GET", "/auth/google/status", "Google auth status", None),
        ("GET", "/drive/files", "Drive files endpoint", None),
        ("GET", "/chat/status", "Chat service status", None),
    ]
    
    results = []
    
    for method, endpoint, description, data in test_cases:
        print(f"\n📋 Testing: {description}")
        print(f"   {method} {API_BASE}{endpoint}")
        
        success, message = test_endpoint(method, endpoint, description, data)
        
        if success:
            print(f"   ✅ Success: {message}")
        else:
            print(f"   ❌ Failed: {message}")
        
        results.append((description, success))
    
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
        print("🎉 All tests passed! APIs are working correctly.")
    else:
        print("⚠️  Some tests failed. Check the server logs for details.")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Testing interrupted by user")
        sys.exit(1)
