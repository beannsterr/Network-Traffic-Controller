# BGP Route Controller

This project is a lightweight prototype for managing BGP route steering, mitigation actions, and role-based workflow logging.

## How to access the site

### 1. Start the backend
From the backend folder, run:

```powershell
cd workflow-agent/bgp-route-controller/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Start the frontend
From the frontend folder, run:

```powershell
cd workflow-agent/bgp-route-controller/frontend
python -m http.server 8080
```

### 3. Open the UI
Open the following URL in your browser:

- http://127.0.0.1:8080/index.html

### 4. API endpoints
The backend API is available at:

- Health: http://127.0.0.1:8000/health
- Routers: http://127.0.0.1:8000/routers
- Policies: http://127.0.0.1:8000/policies
- Capabilities: http://127.0.0.1:8000/capabilities
- Session summary: http://127.0.0.1:8000/session-summary

## Using the UI

- Enter a prefix in the Capabilities section.
- Choose a capability from the dropdown.
- Press Enter or click Execute.
- The action is logged with a timestamp and duration.

## Roles

- Admin: can reset the controller and manage users and route rules
- Operator: can run mitigation actions
- User: can view state and create draft policies
