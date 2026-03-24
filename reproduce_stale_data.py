
import requests
import time

BASE_URL = "http://localhost:8000/api"
WORKSPACE_ID = "b798cd85-f08c-4109-a4c1-c609a7041fcd"

def reproduce():
    # 1. Login
    print("Logging in...")
    login_resp = requests.post(f"{BASE_URL}/auth/login/", json={
        "email": "buildtracker@gmail.com",
        "password": "Password1234$"  # nosec
    })
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return
    
    print(f"Login successful. Keys: {list(login_resp.json().keys())}")
    data = login_resp.json()
    token = data.get("access_token") or data.get("token") or data.get("access")
    if not token:
        print(f"No token found in response: {data}")
        return
    headers = {"Authorization": f"Bearer {token}"}
    print("Token acquired.")

    # 2. Get current integrations
    print("\nFetching current integrations...")
    list_resp = requests.get(f"{BASE_URL}/integrations/{WORKSPACE_ID}/integrations/", headers=headers, timeout=10)
    initial_count = len(list_resp.json().get("data", []))
    print(f"Initial count: {initial_count}")

    # 3. Create a new integration
    unique_name = f"Test Integration {int(time.time())}"
    print(f"\nCreating integration: {unique_name}...")
    create_resp = requests.post(f"{BASE_URL}/integrations/{WORKSPACE_ID}/integrations/", headers=headers, timeout=10, json={
        "name": unique_name,
        "category": "Development",
        "description": "Reproduction test",
        "is_visible": True
    })
    
    if create_resp.status_code == 201:
        print("Integration created successfully.")
    else:
        print(f"Creation failed (Status {create_resp.status_code}): {create_resp.text}")
        return

    # 4. Immediately fetch again
    print("\nFetching integrations again (immediate)...")
    list_resp = requests.get(f"{BASE_URL}/integrations/{WORKSPACE_ID}/integrations/", headers=headers, timeout=10)
    data = list_resp.json().get("data", [])
    new_count = len(data)
    print(f"New count: {new_count}")

    found = any(i['name'] == unique_name for i in data)
    if found:
        print("SUCCESS: New integration found in list.")
    else:
        print("FAILURE: New integration NOT found in list! (STALE DATA)")

    # 5. Wait 2 seconds and try again
    print("\nWaiting 2 seconds...")
    time.sleep(2)
    print("Fetching integrations again (after delay)...")
    list_resp = requests.get(f"{BASE_URL}/integrations/{WORKSPACE_ID}/integrations/", headers=headers, timeout=10)
    data = list_resp.json().get("data", [])
    if any(i['name'] == unique_name for i in data):
        print("SUCCESS: New integration found after delay.")
    else:
        print("FAILURE: New integration STILL NOT found! (Persistence issue or persistent cache issue)")

if __name__ == "__main__":
    reproduce()
