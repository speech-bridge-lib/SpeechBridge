# Security Guidelines

## API Keys

**ВАЖНО:** Никогда не коммитьте API ключи в Git!

### Защищенные файлы (уже в .gitignore):

- `.env` - файл с переменными окружения
- `uploads/` - загруженные видео
- `outputs/` - переведенные видео

### Безопасное использование:

1. **Скопируйте `.env.example` в `.env`**:
   ```bash
   cp .env.example .env
   ```

2. **Добавьте ваш API ключ в `.env`**:
   ```
   DEEPL_API_KEY=your-actual-api-key-here
   ```

3. **Никогда не коммитьте `.env` файл**!

### Для GitHub:

Перед публикацией на GitHub убедитесь:

- [x] `.env` добавлен в `.gitignore`
- [x] Нет захардкоженных API ключей в коде
- [x] `.env.example` содержит только шаблон
- [x] `uploads/` и `outputs/` в `.gitignore`

### Получение DeepL API ключа:

https://www.deepl.com/pro-api
