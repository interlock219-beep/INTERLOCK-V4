import pathlib

service_path = pathlib.Path(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\token_revocation_service.py')
service_content = service_path.read_text()
service_content = service_content.replace(
    'tokens, _ = await self._token_repo.list_all(tenant_id, limit=1000, offset=0)',
    'tokens, _ = await self._token_repo.list_by_tenant(tenant_id, limit=1000, offset=0)'
)
service_content = service_content.replace(
    'tokens, total = await self._token_repo.list_all(\n                tenant_id, limit=limit, offset=offset,\n            )',
    'tokens, total = await self._token_repo.list_by_tenant(\n                tenant_id, limit=limit, offset=offset,\n            )'
)
service_path.write_text(service_content)

test_path = pathlib.Path(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\tests\unit\test_token_revocation.py')
test_content = test_path.read_text()
test_content = test_content.replace('token_repo.list_all.return_value', 'token_repo.list_by_tenant.return_value')
test_content = test_content.replace('token_repo.list_all.side_effect', 'token_repo.list_by_tenant.side_effect')
test_path.write_text(test_content)

print('done')
