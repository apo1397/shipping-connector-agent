# GoKwik Connector Agent — Testing Guide

## Prerequisites

1. **NVIDIA API Key** (required for DeepSeek v3.2 LLM)
   - Get it free from: https://build.nvidia.com/
   - Sign up with your email
   - Navigate to "API Keys" and create a new key
   - Copy the key

2. **Sample API Documentation**
   - You need a URL or file containing shipping provider API docs
   - Postman collection links, GitHub markdown, PDF URLs all work
   - Example: https://example.com/api/shipping-docs

## Quick Start

### 1. Configure Environment

```bash
# Edit .env and replace the placeholder with your actual key
nano .env
# Change: LLM_API_KEY=your_nvidia_api_key_here
```

### 2. Start the Server

```bash
bash run.sh
```

The server will start at `http://localhost:8000`

### 3. Open the Web UI

Open your browser and navigate to:
```
http://localhost:8000
```

You should see the GoKwik Connector Agent UI with the 5-step wizard.

## Testing the Full Pipeline

### Step 1: Input Documentation URL

1. Paste a shipping provider API documentation URL
   - Example: `https://api.xpressbees.com/docs`
   - Or test with Postman collection URL
2. Optionally enter the provider name (e.g., "xpressbees", "delhivery")
3. Click "Analyze Documentation"

**Expected Output:**
- Progress indicator shows: "Creating session..." → "Fetching documentation..." → "Discovering APIs..."
- Takes 30-60 seconds depending on documentation size

### Step 2: API Discovery Review

After analysis, you'll see two cards:

**Tracking API Card:**
- Shows: method (GET/POST), URL, headers, query parameters, request body schema, response schema
- Confidence badge showing detection confidence (7-10/10 usually high)

**Authentication Card:**
- Shows: auth type (bearer_token, api_key_header, basic, oauth2, or none)
- Auth endpoint details if applicable

**Action:** Review the discovered APIs to ensure they match your provider's actual endpoints.
Click "Continue to Status Mapping"

### Step 3: Status Mapping

You'll see a table with:
- **Provider Status**: Status codes from the shipping provider (e.g., "OFD", "DL")
- **Description**: What the status means (e.g., "Out for Delivery")
- **Terminal?**: Whether this is a final status (Yes/No)
- **GoKwik Status**: Dropdown to select the mapped status from GoKwik's canonical list

**Action:**
1. Review LLM's suggested mappings (usually correct)
2. Adjust any that seem wrong by selecting a different GoKwik status from the dropdown
3. Click "Confirm Mappings & Generate Code"

### Step 4: Code Generation

After confirming mappings, the system will:
1. Generate Python connector code with:
   - `authenticate()` — handles auth with credentials
   - `track_shipment()` — calls the tracking API
   - `parse_tracking_response()` — extracts status from API response
   - `STATUS_MAP` — maps provider statuses to GoKwik statuses

**Expected Output:**
- Tab 1: `connector.py` — main connector module
- Tab 2: `__init__.py` — module exports
- Tab 3: `config.json` — metadata

**Buttons:**
- "Download ZIP" — saves connector code as `{provider_name}_connector.zip`
- "Test Connector" → Move to Step 5

### Step 5: Live Test

1. **Enter Credentials** (fields change based on auth type)
   - Bearer Token: `Authorization: Bearer <token>`
   - API Key: `X-API-Key: <key>`
   - Basic Auth: Username + Password
   - OAuth2: Client ID + Secret
   - JSON: Custom credentials as JSON

2. **Enter AWB Numbers** (comma-separated)
   - Example: `AWB123456, AWB789012, AWB445566`

3. **Click "Run Test"**

**Expected Output:**
- Results table showing:
  - ✅ PASS: Successfully fetched tracking for AWB with parsed status
  - ❌ FAIL: Error message if fetch failed

Each result shows:
- Parsed response (formatted JSON)
- Raw API response (if available)
- Error details (if failed)

## Generated Files

After generation, check:
```bash
ls -la generated_connectors/{provider_name}/
# Should contain:
# - connector.py (200-300 lines)
# - __init__.py (module exports)
# - config.json (metadata)
```

## Example Test Case

### Using a Public API (Free Tier)

If you don't have a shipping provider API, you can test with a public API like JSONPlaceholder:

1. **URL:** `https://jsonplaceholder.typicode.com/`
   - Provider Name: `placeholder`

2. **Step 2:** LLM will detect endpoints and suggest auth (usually "none")

3. **Step 3:** Status mapping will be minimal (few statuses)

4. **Step 4:** Generated code will have basic HTTP calling patterns

5. **Step 5:** Test with IDs like: `1, 2, 3` (JSONPlaceholder allows IDs 1-100)

## Troubleshooting

### Error: "Failed to create session"
- Check your NVIDIA API key in `.env` is valid
- Verify internet connection
- Check server logs for detailed error

### Error: "Failed to confirm mappings"
- Ensure all required fields are filled
- Try refreshing the browser and retrying

### Test shows "FAIL" with connection error
- Credentials are wrong or API endpoint is invalid
- Check the discovered API URL in Step 2
- Verify provider's API is accessible

### Server won't start
- Ensure Python 3.9+ is installed: `python3 --version`
- Check `.env` is readable: `cat .env`
- Kill any existing server: `pkill -f "python3 -m backend.main"`
- Try again: `bash run.sh`

### Code generation fails repeatedly
- Documentation might be in an unsupported format
- Try a simpler/smaller documentation URL
- Check server logs for LLM error details

## Performance Notes

- **First run:** 30-60 seconds (documentation fetching + LLM analysis)
- **Code generation:** 15-30 seconds per attempt
- **Tests:** 2-5 seconds per AWB (depending on API response time)

## Next Steps

1. Test with your actual shipping provider's API docs
2. Review generated connector code for accuracy
3. Download ZIP and integrate into your system
4. Customize connector.py if needed for specific data extraction

