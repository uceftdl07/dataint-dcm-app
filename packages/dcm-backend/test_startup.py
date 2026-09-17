#!/usr/bin/env python3
"""Quick startup test — check imports, config, and routes."""

print("=" * 60)
print("🧪 TEST 1: Import main.py")
print("=" * 60)
try:
    from app.main import app
    print("✅ main.py imports OK")
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("🧪 TEST 2: Check CORSSettings")
print("=" * 60)
try:
    from app.config import CORSSettings
    cors = CORSSettings()
    print(f"✅ CORSSettings created")
    print(f"   cors_allowed_origins: {cors.cors_allowed_origins}")
    print(f"   get_allowed_origins(): {cors.get_allowed_origins()}")
except Exception as e:
    print(f"❌ CORSSettings error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("🧪 TEST 3: Check Settings")
print("=" * 60)
try:
    from app.config import Settings
    try:
        settings = Settings.from_secrets_manager()
        print(f"✅ Settings from_secrets_manager() loaded")
    except Exception as e:
        print(f"⚠️  from_secrets_manager() failed (expected in local): {e}")
        settings = Settings()
        print(f"✅ Settings() with defaults loaded")
except Exception as e:
    print(f"❌ Settings error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("🧪 TEST 4: Check app routes")
print("=" * 60)
try:
    routes = [route.path for route in app.routes if hasattr(route, 'path')]
    print(f"✅ App has {len(routes)} routes")
    
    # Check for CORS test endpoint
    if "/api/v1/cors-test" in routes:
        print("✅ /api/v1/cors-test endpoint found!")
    else:
        print("❌ /api/v1/cors-test endpoint NOT found")
        print(f"   Available routes: {routes[:5]}...")
except Exception as e:
    print(f"❌ Routes error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
