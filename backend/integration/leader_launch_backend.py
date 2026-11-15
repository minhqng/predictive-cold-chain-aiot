"""Start the Member C backend using environment-provisioned settings."""
from integration.leader_portable_stack import resolve_runtime_config

import uvicorn

if __name__ == "__main__":
    uvicorn.run("coldguard_backend.main:app", host="127.0.0.1", port=resolve_runtime_config().backend_port)
