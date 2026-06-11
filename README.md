# AI Digest

Daily Chinese AI digest for product managers. The generator combines:

- Central `follow-builders` feeds for AI builder X posts, podcasts, and blogs
- OpenRouter summarization into a static HTML digest under `docs/`
- Optional Telegram delivery from GitHub Actions

## GitHub Actions

The digest runs every day from `.github/workflows/digest.yml`.

- Schedule: `0 0 * * *`, which is 8:00 AM in Singapore.
- Manual runs: use **Actions -> Daily AI Digest -> Run workflow**.
- Output: generated pages are committed back to `docs/`, then published to the `gh-pages` branch used by GitHub Pages.

Required repository secret:

- `OPENROUTER_API_KEY`

Optional Telegram repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository variable or workflow env:

- `OPENROUTER_MODEL`, defaulted in the workflow to `openai/gpt-4o-mini`
- `DIGEST_TIMEZONE`, defaulted in the workflow to `Asia/Singapore`

## Local Run

Create `.env`:

```sh
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
DIGEST_TIMEZONE=Asia/Singapore
# Optional Telegram delivery
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Install and run:

```sh
pip install -r requirements.txt
python digest.py
```

## Publishing

GitHub Pages serves the static archive from the `gh-pages` branch root. The daily workflow updates that branch from `docs/` after each successful digest run.

## Telegram

To send the digest to Telegram from GitHub Actions:

1. In Telegram, open `@BotFather`.
2. Send `/newbot` and follow the prompts.
3. Copy the bot token into the GitHub secret `TELEGRAM_BOT_TOKEN`.
4. Open a chat with your new bot and send it any message.
5. Get your chat ID by opening `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`.
6. Copy `message.chat.id` into the GitHub secret `TELEGRAM_CHAT_ID`.

If either Telegram secret is missing, the workflow still publishes the HTML digest and skips Telegram delivery.
