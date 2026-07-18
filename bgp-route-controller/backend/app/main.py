import ipaddress
import json
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="BGP Route Controller", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ROUTERS_FILE = DATA_DIR / "routers.json"
POLICIES_FILE = DATA_DIR / "policies.json"
USERS_FILE = DATA_DIR / "users.json"
CAPABILITIES_FILE = DATA_DIR / "capabilities.json"
ACTIONS_FILE = DATA_DIR / "actions.json"


class Router(BaseModel):
    id: str
    name: str
    host: str
    vendor: str = "FRRouting"
    status: str = "unknown"


class PolicyRequest(BaseModel):
    router_id: str
    prefix: str
    neighbor: str
    weight: int = Field(ge=0, le=65535)


class Policy(BaseModel):
    id: str
    router_id: str
    prefix: str
    neighbor: str
    weight: int
    status: str = "draft"
    created_at: str
    applied_at: str | None = None
    command_preview: List[str] = Field(default_factory=list)


class User(BaseModel):
    id: str
    username: str
    role: str
    active: bool = True


class CapabilityAction(BaseModel):
    id: str
    name: str
    router_id: str | None = None
    actor_role: str
    status: str
    details: str
    created_at: str


class CapabilityState(BaseModel):
    mode: str = "normal"
    active_router_id: str | None = None
    acl_ports: List[int] = [53, 123, 389]
    last_action: str | None = None


routers: List[Router] = []
policies: List[Policy] = []
users: List[User] = []
capability_state: CapabilityState = CapabilityState()
action_history: List[CapabilityAction] = []


def load_json(path: Path, default):
    if not path.exists():
        save_json(path, default)
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def seed_data() -> None:
    global routers, policies, users, capability_state, action_history
    routers = [Router(**item) for item in load_json(ROUTERS_FILE, [
        {"id": "router-001", "name": "Edge-R1", "host": "10.0.0.1", "vendor": "FRRouting", "status": "online"},
        {"id": "router-002", "name": "Core-R1", "host": "10.0.0.2", "vendor": "Cisco", "status": "standby"},
    ])]
    policies = [Policy(**item) for item in load_json(POLICIES_FILE, [])]
    users = [User(**item) for item in load_json(USERS_FILE, [
        {"id": "user-admin", "username": "admin", "role": "Admin", "active": True},
        {"id": "user-operator", "username": "operator", "role": "Operator", "active": True},
        {"id": "user-guest", "username": "guest", "role": "User", "active": True},
    ])]
    capability_state = CapabilityState(**load_json(CAPABILITIES_FILE, capability_state.model_dump()))
    action_history = [CapabilityAction(**item) for item in load_json(ACTIONS_FILE, [])]


def persist_state() -> None:
    save_json(ROUTERS_FILE, [router.model_dump() for router in routers])
    save_json(POLICIES_FILE, [policy.model_dump() for policy in policies])
    save_json(USERS_FILE, [user.model_dump() for user in users])
    save_json(CAPABILITIES_FILE, capability_state.model_dump())
    save_json(ACTIONS_FILE, [action.model_dump() for action in action_history])


def validate_prefix(prefix: str) -> None:
    ipaddress.ip_network(prefix, strict=False)


def build_policy_commands(router: Router, policy: Policy) -> List[str]:
    vendor = (router.vendor or "FRRouting").lower()
    if "cisco" in vendor:
        return [
            f"router bgp 65000",
            f"neighbor {policy.neighbor} route-map {policy.prefix.replace('.', '_')}-in in",
            f"ip prefix-list {policy.prefix.replace('.', '_')}-allow seq 5 permit {policy.prefix}",
            f"route-map {policy.prefix.replace('.', '_')}-in permit 10 set weight {policy.weight}",
        ]
    if "juniper" in vendor:
        return [
            f"set policy-options policy-statement {policy.prefix.replace('.', '_')}-prefer then local-preference {policy.weight}",
            f"set protocols bgp group external export {policy.prefix.replace('.', '_')}-prefer",
        ]
    return [
        f"vtysh -c 'configure terminal' -c 'router bgp' -c 'neighbor {policy.neighbor} weight {policy.weight}'",
        f"frr.conf: set prefix {policy.prefix} preferred-path via {policy.neighbor}",
    ]


def build_capability_config(router: Router, capability: str, prefix: str, circuit: str | None = None) -> str:
    vendor = (router.vendor or "FRRouting").lower()
    if "cisco" in vendor:
        if capability == "divert":
            return "\n".join([
                "router bgp 65000",
                f"neighbor 203.0.113.1 route-map {prefix.replace('.', '_').replace('/', '_')}-leak in",
                f"ip prefix-list {prefix.replace('.', '_').replace('/', '_')}-leak seq 5 permit {prefix}",
                f"route-map {prefix.replace('.', '_').replace('/', '_')}-leak permit 10 set local-preference 650",
                "end",
            ])
        if capability == "acl-filters":
            circuit_block = circuit or "GigabitEthernet0/0"
            return "\n".join([
                f"interface {circuit_block}",
                "ip access-group 101 in",
                "access-list 101 permit udp any any eq 53",
                "access-list 101 permit udp any any eq 123",
                "access-list 101 permit udp any any eq 389",
                "end",
            ])
        return "router bgp 65000\nend"
    if "juniper" in vendor:
        if capability == "divert":
            return "\n".join([
                "set policy-options policy-statement leak-route then",
                f"  prefix-list {prefix.replace('.', '_').replace('/', '_')}-leak",
                "  accept",
                "set policy-options policy-statement leak-route then local-preference 650",
                "set protocols bgp group external export leak-route",
            ])
        if capability == "acl-filters":
            circuit_block = circuit or "ge-0/0/0"
            return "\n".join([
                f"set interfaces {circuit_block} unit 0 family inet filter input acl-udp-dos",
                "set firewall family inet filter acl-udp-dos term allow53 from protocol udp port 53",
                "set firewall family inet filter acl-udp-dos term allow123 from protocol udp port 123",
                "set firewall family inet filter acl-udp-dos term allow389 from protocol udp port 389",
            ])
        return "set policy-options policy-statement leak-route then accept"
    return f"# FRR placeholder for {capability}\n# prefix={prefix}\n"


def require_role(role: str | None, allowed: List[str]) -> str:
    normalized = (role or "User").title()
    if normalized not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return normalized


def append_action(name: str, router_id: str | None, actor_role: str, status: str, details: str) -> None:
    action_history.append(CapabilityAction(
        id=str(uuid4()),
        name=name,
        router_id=router_id,
        actor_role=actor_role,
        status=status,
        details=details,
        created_at=datetime.utcnow().isoformat(),
    ))
    persist_state()


seed_data()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "bgp-route-controller"}


@app.get("/routers", response_model=List[Router])
def list_routers() -> List[Router]:
    return routers


@app.post("/routers", response_model=Router)
def create_router(router: Router) -> Router:
    routers.append(router)
    persist_state()
    return router


@app.get("/policies", response_model=List[Policy])
def list_policies() -> List[Policy]:
    return policies


@app.post("/policies", response_model=Policy)
def create_policy(policy: PolicyRequest) -> Policy:
    if not any(item.id == policy.router_id for item in routers):
        raise HTTPException(status_code=404, detail="Router not found")

    try:
        validate_prefix(policy.prefix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid prefix") from exc

    record = Policy(
        id=str(uuid4()),
        router_id=policy.router_id,
        prefix=policy.prefix,
        neighbor=policy.neighbor,
        weight=policy.weight,
        status="queued",
        created_at=datetime.utcnow().isoformat(),
        command_preview=[],
    )
    policies.append(record)
    persist_state()
    return record


@app.post("/policies/{policy_id}/apply")
def apply_policy(policy_id: str) -> dict:
    policy = next((item for item in policies if item.id == policy_id), None)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    router = next((item for item in routers if item.id == policy.router_id), None)
    if router is None:
        raise HTTPException(status_code=404, detail="Router not found")

    commands = build_policy_commands(router, policy)
    policy.status = "applied"
    policy.applied_at = datetime.utcnow().isoformat()
    policy.command_preview = commands
    persist_state()
    return {"status": "applied", "policy_id": policy_id, "weight": policy.weight, "commands": commands, "applied_at": policy.applied_at}


@app.delete("/policies/{policy_id}")
def delete_policy(policy_id: str, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin"])
    policy = next((item for item in policies if item.id == policy_id), None)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    policies.remove(policy)
    persist_state()
    append_action("delete-policy", policy.router_id, "Admin", "executed", f"Removed route rule for prefix {policy.prefix}")
    return {"status": "deleted", "policy_id": policy_id}


@app.post("/routers/{router_id}/connect")
def connect_router(router_id: str) -> dict:
    router = next((item for item in routers if item.id == router_id), None)
    if router is None:
        raise HTTPException(status_code=404, detail="Router not found")
    router.status = "connected"
    persist_state()
    return {
        "status": "connected",
        "router_id": router_id,
        "vendor": router.vendor,
        "session": f"ssh://{router.host}",
        "note": "This prototype uses a simulated session and command preview for safe planning.",
    }


@app.get("/capabilities")
def get_capabilities() -> dict:
    return {
        "mode": capability_state.mode,
        "active_router_id": capability_state.active_router_id,
        "acl_ports": capability_state.acl_ports,
        "last_action": capability_state.last_action,
        "history": [action.model_dump() for action in action_history],
    }


@app.get("/session-summary")
def get_session_summary() -> dict:
    connected = [router.model_dump() for router in routers if router.status == "connected"]
    return {
        "connected_routers": connected,
        "router_count": len(routers),
        "policy_count": len(policies),
        "active_mode": capability_state.mode,
    }


@app.post("/capabilities/divert")
def divert_route(payload: dict, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin", "Operator"])
    router_id = payload.get("router_id")
    if not any(item.id == router_id for item in routers):
        raise HTTPException(status_code=404, detail="Router not found")
    capability_state.mode = "diverted"
    capability_state.active_router_id = router_id
    capability_state.last_action = "divert"
    persist_state()
    append_action("divert", router_id, (x_user_role or "User").title(), "executed", "Route diversion applied and BGP weight preference increased")
    return {"status": "executed", "mode": capability_state.mode, "router_id": router_id}


@app.post("/capabilities/execute")
def execute_capability(payload: dict, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin", "Operator"])
    capability = (payload.get("capability") or "").strip().lower()
    router_id = payload.get("router_id")
    prefix = payload.get("prefix") or ""

    if capability not in {"divert", "acl-filters", "revert", "reset"}:
        raise HTTPException(status_code=400, detail="Unsupported capability")
    if capability != "reset" and router_id and not any(item.id == router_id for item in routers):
        raise HTTPException(status_code=404, detail="Router not found")

    start_time = datetime.utcnow()
    router = next((item for item in routers if item.id == router_id), None)
    if capability == "divert":
        capability_state.mode = "diverted"
        capability_state.active_router_id = router_id
        capability_state.last_action = "divert"
        detail = f"Route diversion applied for prefix {prefix}"
    elif capability == "acl-filters":
        ports = payload.get("ports", [53, 123, 389])
        capability_state.mode = "acl-filtered"
        capability_state.active_router_id = router_id
        capability_state.acl_ports = ports
        capability_state.last_action = "acl-filters"
        detail = f"ACL filters installed for prefix {prefix} on ports {ports}"
    elif capability == "revert":
        capability_state.mode = "normal"
        capability_state.active_router_id = router_id
        capability_state.last_action = "revert"
        detail = f"Controller reverted to normal policy for prefix {prefix}"
    else:
        capability_state.mode = "normal"
        capability_state.active_router_id = None
        capability_state.acl_ports = [53, 123, 389]
        capability_state.last_action = "reset"
        detail = f"Controller reset to baseline state for prefix {prefix}"

    config = build_capability_config(router or Router(id=router_id or "unknown", name="unknown", host="unknown", vendor="FRRouting"), capability, prefix, payload.get("circuit"))
    persist_state()
    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    append_action(capability, router_id, (x_user_role or "User").title(), "executed", f"{detail}; prefix={prefix}; started_at={start_time.isoformat()} ; duration_ms={duration_ms}; config:\n{config}")
    return {
        "status": "executed",
        "capability": capability,
        "router_id": router_id,
        "prefix": prefix,
        "duration_ms": duration_ms,
        "started_at": start_time.isoformat(),
        "mode": capability_state.mode,
        "config": config,
    }


@app.post("/capabilities/acl-filters")
def apply_acl_filters(payload: dict, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin", "Operator"])
    router_id = payload.get("router_id")
    if not any(item.id == router_id for item in routers):
        raise HTTPException(status_code=404, detail="Router not found")
    ports = payload.get("ports", [53, 123, 389])
    capability_state.mode = "acl-filtered"
    capability_state.active_router_id = router_id
    capability_state.acl_ports = ports
    capability_state.last_action = "acl-filters"
    persist_state()
    append_action("acl-filters", router_id, (x_user_role or "User").title(), "executed", f"ACL filters installed for UDP DDoS ports: {ports}")
    return {"status": "executed", "ports": ports, "router_id": router_id}


@app.post("/capabilities/revert")
def revert_to_normal(payload: dict, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin", "Operator"])
    router_id = payload.get("router_id")
    if router_id and not any(item.id == router_id for item in routers):
        raise HTTPException(status_code=404, detail="Router not found")
    capability_state.mode = "normal"
    capability_state.active_router_id = router_id
    capability_state.last_action = "revert"
    persist_state()
    append_action("revert", router_id, (x_user_role or "User").title(), "executed", "Controller reverted to normal routing policy")
    return {"status": "executed", "mode": capability_state.mode, "router_id": router_id}


@app.post("/capabilities/reset")
def reset_capabilities(x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin"])
    capability_state.mode = "normal"
    capability_state.active_router_id = None
    capability_state.acl_ports = [53, 123, 389]
    capability_state.last_action = "reset"
    policies.clear()
    persist_state()
    append_action("reset", None, "Admin", "executed", "Controller reset to baseline state")
    return {"status": "reset", "mode": capability_state.mode}


@app.get("/users", response_model=List[User])
def list_users() -> List[User]:
    return users


@app.post("/users", response_model=User)
def create_user(user: User, x_user_role: str | None = Header(default=None)) -> User:
    require_role(x_user_role, ["Admin"])
    users.append(user)
    persist_state()
    append_action("create-user", None, "Admin", "executed", f"Created user {user.username}")
    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: str, x_user_role: str | None = Header(default=None)) -> dict:
    require_role(x_user_role, ["Admin"])
    user = next((item for item in users if item.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    users.remove(user)
    persist_state()
    append_action("delete-user", None, "Admin", "executed", f"Deleted user {user.username}")
    return {"status": "deleted", "user_id": user_id}
