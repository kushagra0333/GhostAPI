import requests
import json
import time

def test_api():
    url = "http://127.0.0.1:8000/generate"
    payload = {"prompt": "explain what is RESTAPI like you are explaning to a 5year old child."}
    headers = {"Content-Type": "application/json"}
    
    print(f"Sending request to {url}...")
    try:
        start = time.time()
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        end = time.time()
        
        print(f"Response status: {response.status_code}")
        print(f"Latency: {end - start:.2f}s")
        
        if response.status_code == 200:
            data = response.json()
            print("Response Data:")
            print(json.dumps(data, indent=2))
        else:
            print("Error response:", response.text)
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Wait for server to start
    time.sleep(2)
    test_api()
