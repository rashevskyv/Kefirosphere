# GitHub Token Setup Guide

## Як отримати GitHub Personal Access Token

1. **Перейдіть на GitHub:**
   - Відкрийте https://github.com/settings/tokens

2. **Створіть новий токен:**
   - Натисніть **"Generate new token"** → **"Generate new token (classic)"**

3. **Налаштуйте токен:**
   - **Note:** `Kefir Build Token` (або будь-яка назва)
   - **Expiration:** `No expiration` (або встановіть термін дії)
   - **Scopes:** Виберіть необхідні права:
     - ✅ `repo` (повний доступ до приватних репозиторіїв)
     - ✅ `workflow` (якщо потрібно запускати GitHub Actions)
     - ✅ `write:packages` (якщо публікуєте пакети)

4. **Згенеруйте токен:**
   - Натисніть **"Generate token"**
   - **ВАЖЛИВО:** Скопіюйте токен зараз! Ви не зможете побачити його знову!

5. **Додайте токен в .env:**
   ```bash
   GITHUB_TOKEN=ghp_ваш_токен_тут
   ```

## Налаштування Git для використання токена

### Автоматично (рекомендовано):
```bash
python utilities/setup_git_credentials.py
```

### Вручну:

#### Варіант 1: Git Credential Store (зберігає в файлі)
```bash
git config --global credential.helper store
echo "https://rashevskyv:ghp_ваш_токен@github.com" >> ~/.git-credentials
chmod 600 ~/.git-credentials
```

#### Варіант 2: Git Credential Cache (зберігає в пам'яті)
```bash
git config --global credential.helper cache
git config --global credential.helper 'cache --timeout=3600'
```

Потім при першому push/pull введіть:
- **Username:** `rashevskyv`
- **Password:** `ghp_ваш_токен` (не пароль, а токен!)

#### Варіант 3: SSH (найбезпечніший)
```bash
# Згенеруйте SSH ключ
ssh-keygen -t ed25519 -C "your_email@example.com"

# Додайте ключ в ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Скопіюйте публічний ключ
cat ~/.ssh/id_ed25519.pub

# Додайте його на GitHub:
# https://github.com/settings/keys → New SSH key
```

Потім змініть remote URL:
```bash
git remote set-url origin git@github.com:rashevskyv/kefir.git
```

## Перевірка налаштування

```bash
# Перевірте, що токен працює
git ls-remote https://github.com/rashevskyv/kefir.git

# Або спробуйте push
git push
```

## Безпека

⚠️ **НІКОЛИ не комітьте .env файл з токеном в git!**

Переконайтеся, що `.env` в `.gitignore`:
```bash
echo ".env" >> .gitignore
```

## Troubleshooting

### "Authentication failed"
- Перевірте, що токен правильно скопійований в .env
- Перевірте, що токен має права `repo`
- Перевірте, що токен не прострочений

### "Permission denied"
- Переконайтеся, що ви маєте права на запис в репозиторій
- Перевірте, що використовуєте правильний username

### WSL: "Permission denied (publickey)"
```bash
# Переконайтеся, що git використовує HTTPS, а не SSH
git remote -v
git remote set-url origin https://github.com/rashevskyv/kefir.git
```
