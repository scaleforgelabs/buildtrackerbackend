from locust import HttpUser, task, between, events
import requests

GLOBAL_TOKEN = None

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global GLOBAL_TOKEN
    print(f"Fetching global token from {environment.host}...")
    try:
        response = requests.post(f"{environment.host}/api/auth/login/", json={
            "email": "ojugbelelateef2006@gmail.com",
            "password": "Ojugbele2006@"
        }, timeout=10)
        
        if response.status_code == 200:
            GLOBAL_TOKEN = response.json().get('token')
            print("Successfully acquired global test token! Load test will now begin...")
        else:
            print(f"CRITICAL: Test Start Failed to login: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"CRITICAL: Exception during test start login: {e}")

class BuildTrackerUser(HttpUser):
    # Simulate a user waiting between 1 to 3 seconds before making another click
    wait_time = between(1, 3)
    
    def on_start(self):
        """
        Executed exactly once per simulated user when they start.
        We apply the single global token to all 500+ users!
        """
        if GLOBAL_TOKEN:
            self.client.headers.update({'Authorization': f'Bearer {GLOBAL_TOKEN}'})
        else:
            # If the global token failed to fetch, the users shouldn't even bother
            pass

    @task(3)
    def view_user_profile(self):
        """Simulate a user viewing their profile/dashboard (weight: 3)"""
        self.client.get("/api/auth/me/")
        
    @task(2)
    def view_workspaces(self):
        """Simulate a user checking their workspaces list (weight: 2)"""
        self.client.get("/api/workspaces/")
