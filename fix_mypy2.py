import pathlib
p = pathlib.Path(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\enterprise_recovery_platform.py')
text = p.read_text(encoding='utf-8')
text = text.replace('    async def _trigger_self_healing(\n        self, tenant_id: str, incident: Incident\n    ) -> dict[str, Any]:\n\n        """Trigger self-healing checks for the affected agent."""\n        if self._healing is None:\n            return {"error": "self_healing_not_configured"}', '    async def _trigger_self_healing(\n        self, tenant_id: str, incident: Incident\n    ) -> dict[str, Any]:\n        """Trigger self-healing checks for the affected agent."""\n        if self._healing is None:\n            return {"error": "self_healing_not_configured"}')
p.write_text(text, encoding='utf-8')
print('done')
