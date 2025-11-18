# Security Guidelines

## API Keys

**IMPORTANT:** Never commit API keys to Git!

### Protected files (already in .gitignore):

- `.env` - environment variables file
- `uploads/` - uploaded videos
- `outputs/` - translated videos

### Secure usage:

1. **Copy `.env.example` to `.env`**:
   ```bash
   cp .env.example .env
   ```

2. **Add your API key to `.env`**:
   ```
   DEEPL_API_KEY=your-actual-api-key-here
   ```

3. **Never commit the `.env` file**!

### For GitHub:

Before publishing to GitHub, ensure:

- [x] `.env` is added to `.gitignore`
- [x] No hardcoded API keys in code
- [x] `.env.example` contains only a template
- [x] `uploads/` and `outputs/` are in `.gitignore`

### Getting a DeepL API key:

https://www.deepl.com/pro-api
