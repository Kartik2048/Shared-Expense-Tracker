import os
from datetime import datetime, timezone

# Force SQLite database file for testing
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

try:
    from fastapi.testclient import TestClient
except (ImportError, RuntimeError):
    print("TestClient requires 'httpx'. Installing it dynamically...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_api():
    print("1. Testing User Creation...")
    user_data = {
        "name": "kartik_api",
        "email": "kartik_api@example.com"
    }
    response = client.post("/users/", json=user_data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    user_json = response.json()
    assert user_json["name"] == "kartik_api"
    assert user_json["email"] == "kartik_api@example.com"
    assert "id" in user_json
    user_id = user_json["id"]

    # Test duplicate email validation
    print("\n1b. Testing duplicate user validation...")
    response_dup = client.post("/users/", json=user_data)
    print(f"Duplicate user Status Code: {response_dup.status_code}")
    print(f"Duplicate user Response: {response_dup.json()}")
    assert response_dup.status_code == 400

    print("\n2. Testing Group Creation...")
    group_data = {
        "name": "Skiing Trip 2026"
    }
    response = client.post("/groups/", json=group_data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    group_json = response.json()
    assert group_json["name"] == "Skiing Trip 2026"
    assert "id" in group_json
    group_id = group_json["id"]

    print("\n3. Testing Adding User to Group with specific joined_at timestamp...")
    joined_date = "2026-05-15T09:30:00"
    member_data = {
        "user_id": user_id,
        "joined_at": joined_date
    }
    response = client.post(f"/groups/{group_id}/members", json=member_data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    member_json = response.json()
    assert member_json["group_id"] == group_id
    assert member_json["user_id"] == user_id
    assert member_json["joined_at"].startswith("2026-05-15T09:30:00")

    print("\n3b. Testing duplicate member validation...")
    response_dup_member = client.post(f"/groups/{group_id}/members", json=member_data)
    print(f"Duplicate member Status Code: {response_dup_member.status_code}")
    print(f"Duplicate member Response: {response_dup_member.json()}")
    assert response_dup_member.status_code == 400

    print("\nAPI Routes and Pydantic Schemas verified successfully!")

if __name__ == "__main__":
    try:
        test_api()
    finally:
        # Dispose the engine to release open file locks on Windows
        try:
            from app.database import engine
            engine.dispose()
        except Exception as e:
            print(f"Failed to dispose engine: {e}")
            
        # Clean up local SQLite test file
        if os.path.exists("test.db"):
            try:
                os.remove("test.db")
                print("Cleaned up test.db successfully.")
            except Exception as e:
                print(f"Failed to clean up test.db: {e}")
