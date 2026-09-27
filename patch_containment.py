import pathlib

p = pathlib.Path(r"F:\Desktop_Data_2026\Desktop\INTERLOCK V4\tests\stress\test_live_agent_recovery.py")
text = p.read_text(encoding="utf-8")

# Fix freeze test: change grantor-kill to grantor-freeze
old_freeze_fix = r'''        # Create grantor agent for authority delegation
        grantor_id = f"grantor-kill-{uuid4().hex[:8]}"
        client.post(
            "/api/v1/agents",
            json={
                "agent_id": grantor_id,
                "name": f"Grantor {grantor_id}",
                "agent_type": "tool_agent",
                "environment": "test",
                "tenant_id": "tenant-live-agent",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        # Create authority grant so agent can perform filesystem operations
        _create_authority_grant(client, admin_token, grantor_id, agent_id)
        
        path_security = WorkspacePathSecurity(workspace)
        tools = ProtectedFilesystemTools(
            path_security=path_security,
            gateway_url="http://test",
            auth_token=admin_token,
            http_client=_make_http_client(client, admin_token),
        )
        
        # Pre-freeze mutation should work'''

new_freeze_fix = r'''        # Create grantor agent for authority delegation
        grantor_id = f"grantor-freeze-{uuid4().hex[:8]}"
        client.post(
            "/api/v1/agents",
            json={
                "agent_id": grantor_id,
                "name": f"Grantor {grantor_id}",
                "agent_type": "tool_agent",
                "environment": "test",
                "tenant_id": "tenant-live-agent",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        # Create authority grant so agent can perform filesystem operations
        _create_authority_grant(client, admin_token, grantor_id, agent_id)
        
        path_security = WorkspacePathSecurity(workspace)
        tools = ProtectedFilesystemTools(
            path_security=path_security,
            gateway_url="http://test",
            auth_token=admin_token,
            http_client=_make_http_client(client, admin_token),
        )
        
        # Pre-freeze mutation should work'''

if old_freeze_fix not in text:
    raise SystemExit("OLD_FREEZE_FIX NOT FOUND")
text = text.replace(old_freeze_fix, new_freeze_fix, 1)

# Kill test: add grantor block
old_kill = r'''        session_id = resp.json()["session_id"]
        
        path_security = WorkspacePathSecurity(workspace)
        tools = ProtectedFilesystemTools(
            path_security=path_security,
            gateway_url="http://test",
            auth_token=admin_token,
            http_client=_make_http_client(client, admin_token),
        )
        
        # Pre-kill mutation'''

new_kill = r'''        session_id = resp.json()["session_id"]
        
        # Create grantor agent for authority delegation
        grantor_id = f"grantor-kill-{uuid4().hex[:8]}"
        client.post(
            "/api/v1/agents",
            json={
                "agent_id": grantor_id,
                "name": f"Grantor {grantor_id}",
                "agent_type": "tool_agent",
                "environment": "test",
                "tenant_id": "tenant-live-agent",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        # Create authority grant so agent can perform filesystem operations
        _create_authority_grant(client, admin_token, grantor_id, agent_id)
        
        path_security = WorkspacePathSecurity(workspace)
        tools = ProtectedFilesystemTools(
            path_security=path_security,
            gateway_url="http://test",
            auth_token=admin_token,
            http_client=_make_http_client(client, admin_token),
        )
        
        # Pre-kill mutation'''

if old_kill not in text:
    raise SystemExit("OLD_KILL NOT FOUND")
text = text.replace(old_kill, new_kill, 1)

p.write_text(text, encoding="utf-8")
print("PATCHED")
