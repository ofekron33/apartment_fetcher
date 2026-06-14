"""
One-time setup: Log in via browser and save the Firebase refresh token.
The refresh token doesn't expire, so you only run this once.
"""

import json
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

sys.stdout.reconfigure(encoding="utf-8")

TOKEN_FILE = "firebase_token.json"


def main():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    print("Starting Chrome...")
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    driver.get("https://4kirot.com/")

    print("\nPlease log in with your Gmail account in the browser.")
    print("Waiting for login...")

    for i in range(300):
        time.sleep(1)
        if "/auth" not in driver.current_url:
            break
        if i % 15 == 0 and i > 0:
            print(f"  [{i}s] Waiting...")
    else:
        print("Timed out.")
        driver.quit()
        return

    print("Logged in! Extracting tokens...")
    time.sleep(5)

    # Extract the refresh token from Firebase Auth
    token_data = driver.execute_script("""
        return new Promise((resolve) => {
            // Firebase Auth stores the current user with tokens
            // Access via the auth module that's already loaded
            const checkAuth = () => {
                // Try to get auth from the Firebase app
                try {
                    // The firebase-config.js exports 'auth'
                    // We can access the internal state
                    const keys = Object.keys(sessionStorage);
                    const firebaseKeys = keys.filter(k => k.startsWith('firebase:'));
                    const result = {};
                    firebaseKeys.forEach(k => {
                        try {
                            result[k] = JSON.parse(sessionStorage.getItem(k));
                        } catch(e) {
                            result[k] = sessionStorage.getItem(k);
                        }
                    });
                    resolve(result);
                } catch(e) {
                    resolve({error: e.message});
                }
            };
            checkAuth();
        });
    """)

    print(f"Session storage keys: {list(token_data.keys()) if token_data else 'none'}")

    # Also try to get the token directly from the auth object
    refresh_token = driver.execute_script("""
        // Firebase Auth in the page context
        // The auth object is module-scoped, but we can access currentUser
        // through the Firebase Auth's internal persistence layer

        // Check sessionStorage for Firebase auth state
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            const val = sessionStorage.getItem(key);
            if (val && val.includes('refreshToken')) {
                return val;
            }
        }

        // Check localStorage too
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            const val = localStorage.getItem(key);
            if (val && val.includes('refreshToken')) {
                return val;
            }
        }

        return null;
    """)

    if refresh_token:
        data = json.loads(refresh_token)
        print(f"\nFound Firebase auth data!")
        print(f"  Email: {data.get('email', 'N/A')}")
        print(f"  UID: {data.get('uid', data.get('localId', 'N/A'))}")

        # Extract the refresh token
        stsToken = data.get("stsTokenManager", {})
        rt = stsToken.get("refreshToken", "")

        if rt:
            saved = {
                "refresh_token": rt,
                "email": data.get("email"),
                "uid": data.get("uid", data.get("localId")),
                "api_key": "AIzaSyASXIdOzl71__LJtYkSYS7kVzXorA9NDKg",
            }
            with open(TOKEN_FILE, "w") as f:
                json.dump(saved, f, indent=2)
            print(f"\nRefresh token saved to {TOKEN_FILE}")
            print("You can now use fetch_apartments.py without a browser!")
        else:
            print("Could not find refresh token in auth data.")
            print(f"Keys found: {list(data.keys())}")
    else:
        print("\nNo Firebase auth data found in storage.")
        print("Trying alternative extraction...")

        # Try accessing through IndexedDB
        idb_data = driver.execute_script("""
            return new Promise((resolve) => {
                const req = indexedDB.databases();
                req.then(dbs => {
                    resolve(dbs.map(d => d.name));
                }).catch(() => resolve([]));
            });
        """)
        print(f"IndexedDB databases: {idb_data}")

        # Try the firebase auth internal state
        auth_state = driver.execute_script("""
            // Iterate all storage mechanisms
            const result = {sessionStorage: {}, localStorage: {}, cookies: document.cookie};

            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                result.sessionStorage[key] = sessionStorage.getItem(key).substring(0, 200);
            }
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                result.localStorage[key] = localStorage.getItem(key).substring(0, 200);
            }

            return result;
        """)
        print(f"\nAll storage:")
        print(json.dumps(auth_state, indent=2, ensure_ascii=False))

    driver.quit()


if __name__ == "__main__":
    main()
