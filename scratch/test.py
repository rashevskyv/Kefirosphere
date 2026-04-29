import os
import re
import urllib.request
import urllib.error
import json

def get_env_var(key):
    path = '.env'
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith(key + '='):
                    return line.strip().split('=', 1)[1]
    return ''

def translate_block_with_openai(ukr_block_text):
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key or not ukr_block_text.strip():
        return "TRANSLATED_ENG: " + ukr_block_text.replace('\n', ' | ')
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    prompt = (
        "Translate the following changelog block into English.\n"
        "Rules:\n"
        "- Output ONLY the translated text.\n"
        "- Preserve all markdown formatting, including asterisks, list markers, and brackets.\n"
        "- Do NOT translate tool names (e.g., 'Atmosphere', 'Mission Control').\n"
        "- Translate 'Оновлено' to 'Updated', 'Додано' to 'Added'.\n\n"
        f"Block:\n{ukr_block_text}"
    )
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    try:
        req = urllib.request.Request(url, data=json.dumps(data, ensure_ascii=False).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = json.loads(resp.read().decode('utf-8'))
            return resp_body['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"[ERROR] AI block translation failed: {e}")
        return ""

def update_changelog_file(changelog_path, tool_id, tool_name, tool_version, release_url, summary_ukr, kefir_ver, hos_version=None):
    if not os.path.exists(changelog_path):
        return
        
    with open(changelog_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_entry_ukr = f"* [**Оновлено**] [{tool_name} {tool_version}]({release_url}) — {summary_ukr}"

    parts = content.split('#### **ENG**')
    if len(parts) != 2:
        return
        
    ukr_part, eng_part = parts[0], parts[1]
    
    # 1. Update UKR part
    def extract_and_update_block(part_text, ver, entry, t_name):
        ver_marker = f"**{ver}**"
        pattern = re.compile(re.escape(ver_marker) + r'(.*?)(?=\*\*[\d]+\*\*|\Z)', re.DOTALL)
        match = pattern.search(part_text)
        
        if match:
            block = match.group(1)
            lines = block.split('\n')
            new_lines = []
            for line in lines:
                if line.strip().startswith('*') and f"[{t_name} " in line:
                    continue
                new_lines.append(line)
            
            # insert logic
            # append it above the first existing list item or at the end
            first_idx = -1
            for i, l in enumerate(new_lines):
                if l.strip().startswith('*'):
                    first_idx = i
                    break
            
            if first_idx != -1:
                new_lines.insert(first_idx, entry)
            else:
                new_lines.append(entry)
                
            new_block = "\n".join(new_lines)
            
            updated_part = part_text[:match.start()] + ver_marker + new_block + part_text[match.end():]
            return updated_part, new_block.strip()
        else:
            match = re.search(r'\*\*\d+\*\*', part_text)
            new_block = f"\n{entry}\n\n"
            if match:
                idx = match.start()
                updated_part = part_text[:idx] + f"{ver_marker}{new_block}" + part_text[idx:]
            else:
                updated_part = part_text + f"\n{ver_marker}{new_block}"
            return updated_part, entry
            
    new_ukr_part, ukr_block_clean = extract_and_update_block(ukr_part, kefir_ver, new_entry_ukr, tool_name)
    
    # Check lines in UKR block vs ENG block
    ver_marker = f"**{kefir_ver}**"
    pattern = re.compile(re.escape(ver_marker) + r'(.*?)(?=\*\*[\d]+\*\*|\Z)', re.DOTALL)
    match_eng = pattern.search(eng_part)
    
    eng_block_clean = ""
    if match_eng:
        eng_block_clean = match_eng.group(1).strip()
        
    ukr_tool_count = len([l for l in ukr_block_clean.split('\n') if l.strip().startswith('*')])
    eng_tool_count = len([l for l in eng_block_clean.split('\n') if l.strip().startswith('*')])
    
    new_eng_part = eng_part
    
    if ukr_tool_count == eng_tool_count and eng_tool_count > 0:
        print(f"[{tool_id}] Tool counts match ({ukr_tool_count}) in UKR and ENG for v{kefir_ver}. Skipping translation.")
    else:
        print(f"[{tool_id}] Tool counts differ (UKR: {ukr_tool_count}, ENG: {eng_tool_count}) or missing. Translating UKR block to ENG...")
        translated_block = translate_block_with_openai(ukr_block_clean)
        
        if match_eng:
            new_eng_part = eng_part[:match_eng.start()] + ver_marker + "\n" + translated_block + "\n\n" + eng_part[match_eng.end():]
        else:
            match = re.search(r'\*\*\d+\*\*', eng_part)
            if match:
                idx = match.start()
                new_eng_part = eng_part[:idx] + f"{ver_marker}\n{translated_block}\n\n" + eng_part[idx:]
            else:
                new_eng_part = eng_part + f"\n{ver_marker}\n{translated_block}\n"
    
    full_content = new_ukr_part + '#### **ENG**' + new_eng_part
    
    with open('test_changelog_out.md', 'w', encoding='utf-8') as f:
        f.write(full_content)
        
    print(f"[{tool_id}] Updated changelog in test_changelog_out.md")

update_changelog_file('D:/git/dev/_kefir/changelog', 'TEST', 'Ovl Sysmodules', 'v1.5.0', 'http://test', 'Новий ліміт!', '814')
