"""
Test script to verify the integration is working correctly
Run this after starting both the backend API and Ed integration
"""

import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = 'http://localhost:8320/api'

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_health_check():
    """Test if the API server is running"""
    print_section("1. Health Check")
    try:
        response = requests.get('http://localhost:8320/')
        if response.status_code == 200:
            data = response.json()
            print("✓ API Server is running!")
            print(f"  Status: {data['status']}")
            print(f"  Posts: {data['stats']['posts']}")
            print(f"  Students: {data['stats']['students']}")
            print(f"  Homeworks: {data['stats']['homeworks']}")
            print(f"  LLMs: {data['stats']['llms']}")
            return True
        else:
            print(f"✗ API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to API server")
        print("  Make sure backend_api.py is running!")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_students():
    """Test getting list of students"""
    print_section("2. Get Students")
    try:
        response = requests.get(f'{API_BASE_URL}/students')
        if response.status_code == 200:
            students = response.json()
            print(f"✓ Found {len(students)} students:")
            for student in students[:5]:  # Show first 5
                print(f"  - {student['name']}")
            if len(students) > 5:
                print(f"  ... and {len(students) - 5} more")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_homeworks():
    """Test getting list of homeworks"""
    print_section("3. Get Homeworks")
    try:
        response = requests.get(f'{API_BASE_URL}/homeworks')
        if response.status_code == 200:
            homeworks = response.json()
            print(f"✓ Found {len(homeworks)} homeworks:")
            for hw in homeworks[:3]:
                print(f"  - Homework {hw['number']}")
                print(f"    Students: {len(hw['students'])}")
                print(f"    LLMs: {len(hw['llms'])}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_llms():
    """Test getting list of LLMs"""
    print_section("4. Get LLM Agents")
    try:
        response = requests.get(f'{API_BASE_URL}/llms')
        if response.status_code == 200:
            llms = response.json()
            print(f"✓ Found {len(llms)} LLM agents:")
            for llm in llms:
                print(f"  - {llm['name']}")
                print(f"    Students: {len(llm['students'])}")
                print(f"    Homeworks: {len(llm['homeworks'])}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_posts():
    """Test getting filtered posts"""
    print_section("5. Get Posts (All)")
    try:
        response = requests.get(f'{API_BASE_URL}/posts')
        if response.status_code == 200:
            posts = response.json()
            print(f"✓ Found {len(posts)} posts")
            if posts:
                print(f"\n  Example post:")
                post = posts[0]
                print(f"  Title: {post['title']}")
                print(f"  Author: {post['author']}")
                print(f"  Participation: {post.get('participation', 'N/A')}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_filtered_posts():
    """Test getting filtered posts"""
    print_section("6. Get Posts (Filtered)")
    try:
        # Try filtering by participation type A
        response = requests.get(f'{API_BASE_URL}/posts?participation=A')
        if response.status_code == 200:
            posts = response.json()
            print(f"✓ Found {len(posts)} Participation A posts")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_sentiment():
    """Test sentiment analysis endpoint"""
    print_section("7. Get Sentiment Analysis")
    try:
        response = requests.get(f'{API_BASE_URL}/sentiment')
        if response.status_code == 200:
            sentiment = response.json()
            print(f"✓ Got sentiment data for {len(sentiment)} LLMs:")
            for llm, data in list(sentiment.items())[:3]:
                print(f"  - {llm}: {data['sentiment']} ({data['score']:.2f})")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_create_post():
    """Test creating a new post (simulating Ed integration)"""
    print_section("8. Create Test Post")
    try:
        test_post = {
            "post_id": 999,
            "title": "Test Post - Participation A HW1 Claude",
            "author": "Test Student",
            "content": "This is a test post created by the test script",
            "participation_type": "A",
            "homework_number": 1,
            "llm_agent": "Claude",
            "timestamp": datetime.now().isoformat(),
            "url": "https://edstem.org/test",
            "category": "Test"
        }
        
        response = requests.post(f'{API_BASE_URL}/posts', json=test_post)
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Created test post with ID {result['post_id']}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_submission():
    """Test getting a submission"""
    print_section("9. Get Submission")
    try:
        response = requests.get(
            f'{API_BASE_URL}/submissions',
            params={'student': 'Alice Johnson', 'homework': '1', 'llm': 'Claude'}
        )
        if response.status_code == 200:
            submission = response.json()
            print("✓ Got submission data")
            print(f"  Student: {submission.get('student', 'N/A')}")
            print(f"  Homework: {submission.get('homework', 'N/A')}")
            print(f"  LLM: {submission.get('llm', 'N/A')}")
            if 'summary' in submission:
                print(f"  Summary: {submission['summary'][:100]}...")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("""
╔════════════════════════════════════════════════════════════╗
║   CS182A/282A Integration Test Suite                       ║
╚════════════════════════════════════════════════════════════╝
    
This script will test all API endpoints to verify the integration
is working correctly.

Prerequisites:
  1. Backend API server must be running (python backend_api.py)
  2. Ed integration should be running (python ed_integration.py)
  3. Frontend can be tested separately
    """)
    
    input("Press Enter to start tests...")
    
    # Run all tests
    results = {
        'Health Check': test_health_check(),
        'Get Students': test_get_students(),
        'Get Homeworks': test_get_homeworks(),
        'Get LLMs': test_get_llms(),
        'Get All Posts': test_get_posts(),
        'Get Filtered Posts': test_filtered_posts(),
        'Get Sentiment': test_sentiment(),
        'Create Post': test_create_post(),
        'Get Submission': test_submission(),
    }
    
    # Print summary
    print_section("Test Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"Passed: {passed}/{total}\n")
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:10s} {test_name}")
    
    print("\n")
    
    if passed == total:
        print("🎉 All tests passed! Your integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        print("\nTroubleshooting:")
        print("  1. Make sure backend_api.py is running")
        print("  2. Check that port 8320 is not blocked")
        print("  3. Review any error messages above")
    
    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    run_all_tests()