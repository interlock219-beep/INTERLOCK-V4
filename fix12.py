with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 1025 - ternary too long
old_1025 = 'current_snapshot = self._capture_file_snapshot(full_path, self._max_file_size_bytes) if full_path.exists() or full_path.is_symlink() else self._capture_file_snapshot(full_path, self._max_file_size_bytes)'
new_1025 = '''current_snapshot = (\n                self._capture_file_snapshot(full_path, self._max_file_size_bytes)\n                if full_path.exists() or full_path.is_symlink()\n                else self._capture_file_snapshot(full_path, self._max_file_size_bytes)\n            )'''
content = content.replace(old_1025, new_1025)

# Fix line 1030 - F841 unused variable action_type
# Remove the unused variable assignment
content = content.replace(
    'action_type = action.action_type.lower()\n        operation = compensation_payload.get(\"operation\", \"\")',
    'operation = compensation_payload.get(\"operation\", \"\")'
)

# Fix line 1053 - string too long
content = content.replace(
    '\"reason\": \"Current filesystem state differs from the captured post-action state\",',
    '\"reason\": (\n                        \"Current filesystem state differs from the \"\n                        \"captured post-action state\"\n                    ),'
)

# Fix line 1067 - dict literal too long
content = content.replace(
    'details={\"reason\": \"Target path was recreated after deletion\", \"file\": file_path_str},',
    'details={\n                    \"reason\": \"Target path was recreated after deletion\",\n                    \"file\": file_path_str,\n                },'
)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 1025, 1030 (F841), 1053, 1067')
