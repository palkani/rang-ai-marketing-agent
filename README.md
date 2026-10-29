# RANG AI Marketing Agent

Local-first restaurant flyer and caption dashboard using Docker Compose, Next.js, FastAPI, SQLite, Pillow, and APScheduler.

## Start on Mac

1. Install Docker Desktop.
2. Clone this repository.
3. Run `cp .env.example .env`.
4. Run `docker compose up --build -d`.
5. Visit http://localhost:3000.

Generate daily flyers, approve drafts, download JPEGs for WhatsApp sharing, and optionally post to Instagram/Facebook once Meta credentials and a publicly accessible HTTPS media URL are configured.

**Security:** Never commit `.env`, Meta tokens, or private customer data. Repository is currently visible as public; change it to Private in GitHub Settings before adding sensitive assets.

**Limitations:** ChatGPT Plus is not a backend API entitlement; this version uses local templates and requires no AI image API. WhatsApp group posting is manual.
