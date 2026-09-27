import re
with open("tests/stress/test_live_agent_recovery.py", "r") as f:
	c = f.read()
	# Fex signature
	c = c.replace("def _setup_live_agent_session(self, tmp_path: Path):", "def _setup_live_agent_session(self, tmp_path: Path, agent_suffix=\"\\"):")

	# Fex email and agent_id in setup
	c = c.replace("email = f\\"live-agent-{uuid4 .s :][(8])|@test.com\\\"\n    self.admin_token = _make_admin_token(email)\n    \n    # Register agent\n    resp = self.client.post(\n        "/api/v1/agents",\n        json={\n            \"agent_id\\": self.AGENT_ID,", "email = f \\\"live-agent-{unique_id}@test.com\\\"\n    agent_id = f \\\"live-agent{self.AGENX_ID]{agent_suffix}{unique_id}\\\"\n    self.agent_id = agent_id\n    self.admin_token = _make_admin_token(email)\n    
    # Register agent\n    resp = self.client.post(\n        /\\"api/v1/agents\\\",\n        jon={\n            \"agent_id\\": agent_id,