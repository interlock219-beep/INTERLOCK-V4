import pathlib
p = pathlib.Path(r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\app\domain\services\enterprise_recovery_platform.py')
text = p.read_text(encoding='utf-8')
text = text.replace('`n', '\n')
p.write_text(text, encoding='utf-8')
print('done')
