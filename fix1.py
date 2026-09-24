with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 224
content = content.replace(
    'digest = hashlib.sha256(raw_bytes).hexdigest() if stat.S_ISREG(file_stat.st_mode) else None',
    'digest = (\n                hashlib.sha256(raw_bytes).hexdigest()\n                if stat.S_ISREG(file_stat.st_mode)\n                else None\n            )'
)

# Fix line 274
old_274 = '"type": "symlink" if is_link else "directory" if metadata["is_directory"] else "file" if metadata["is_file"] else "other",'
new_274 = '''"type": (
                "symlink"
                if is_link
                else "directory"
                if metadata["is_directory"]
                else "file"
                if metadata["is_file"]
                else "other"
            ),'''
content = content.replace(old_274, new_274)

# Fix line 278
old_278 = '"content_b64": base64.b64encode(raw_bytes).decode("ascii") if stat.S_ISREG(file_stat.st_mode) else None,'
new_278 = '''"content_b64": (
                base64.b64encode(raw_bytes).decode("ascii")
                if stat.S_ISREG(file_stat.st_mode)
                else None
            ),'''
content = content.replace(old_278, new_278)

with open(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\infrastructure\recovery\filesystem_recovery_adapter.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed lines 224, 274, 278')
