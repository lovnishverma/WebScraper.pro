---
title: WebScraper.pro
emoji: 🚀
colorFrom: pink
colorTo: indigo
sdk: docker
pinned: false
---

# 🕷️ WebScraper.pro — Premium Web Scraping Platform

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask Version](https://img.shields.io/badge/flask-3.0.3-green.svg)](https://flask.palletsprojects.com/)
[![Playwright](https://img.shields.io/badge/playwright-1.44.0-orange.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**WebScraper.pro** is a professional, secure, and production-ready web scraping platform built on Python and Flask. It provides a visual dashboard to configure, manage, and schedule scraping jobs targeting both static pages and modern dynamic (JavaScript-rendered) websites, exporting cleanly to JSON, CSV, or Excel.

Designed with a **premium dark-mode visual interface** featuring glassmorphism elements, dynamic micro-animations, and live job status polling.

---

## 🌟 Key Features

* **⚡ Dual Scraping Engines:**
  * **Static Engine:** Fast, lightweight HTTP requests combined with BeautifulSoup4 parsing.
  * **Dynamic Engine:** Headless Playwright integration for complex, client-side, JavaScript-heavy SPAs.
* **📊 Premium Real-Time Dashboard:**
  * Live-updating analytics cards (success rates, items scraped, running jobs).
  * Auto-refreshing status progress bars and real-time console log stream.
* **🔎 Granular Visual Extractors:**
  * Select data via **CSS Selectors**, **XPath Expressions**, **HTML Tags**, or **HTML Attributes**.
  * Custom configurations for **Table Data**, **JSON-LD Schema**, and **Full HTML** extractions.
* **⚙️ Enterprise Crawl Controls:**
  * Auto-rotating random User Agents per request.
  * Adaptive request throttling (custom delays) and automatic retry policies.
  * Infinite scroll triggers (custom scroll depth) and standard pagination crawling.
  * Full support for custom HTTP request headers (JSON format).
* **🔒 Production-Grade Security:**
  * High-performance request rate limiting powered by `Flask-Limiter`.
  * Industry-standard Cross-Site Request Forgery (`CSRFProtect`) protection.
  * Strict security headers (CSP, X-Frame-Options, X-Content-Type) and sanitize filters (`bleach`).
* **📥 Multi-Format Exporters:** Export scraped datasets on-demand to structured **JSON**, **CSV**, or Microsoft **Excel** (`.xlsx`).

---

## 🏗️ Modular Architecture

The platform has been re-architected from a flat layout into a highly maintainable, standardized **Application Factory Blueprint** structure:

```
webscraping/
├── app/
│   ├── __init__.py           # Application Factory initialization
│   ├── config/               # Settings & Environment configurations
│   ├── models/               # SQLAlchemy ORM schemas (BaseModel, User, ScrapeJob, etc.)
│   ├── scrapers/             # Core Scraping Engine (Static & Playwright)
│   ├── services/             # Job Execution, Excel/CSV Exports, Statistics calculations
│   ├── middleware/           # Rate limiting and Security headers middleware
│   ├── routes/               # Modular controller Blueprints (Main, Jobs)
│   ├── utils/                # Input validation & Logging configurators
│   ├── templates/            # HTML templates (dashboard, job details, forms)
│   └── static/               # Premium custom CSS, JS assets
├── run.py                    # Production-ready entry point
├── .env                      # Environment secrets
└── requirements.txt          # Package dependencies
```

---

## 🚀 Quick Start

### 📋 Prerequisites
- Python **3.10** or higher
- Node.js (required for Playwright browsers dependency)

### 1. Clone & Set Up Directory
```bash
git clone https://github.com/your-username/webscraper-pro.git
cd webscraper-pro
```

### 2. Configure Virtual Environment
```bash
python -m venv venv
# On Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Setup Environment Variables
Create a `.env` file in the root directory. You can copy the example file:
```bash
cp env.example .env
```

Open `.env` and set up your application environment details:
```ini
# Core
FLASK_APP=app
FLASK_ENV=development
SECRET_KEY=generate-a-strong-random-key-here
DEBUG=True

# Database (Leave commented out to use default SQLite)
# DATABASE_URL=sqlite:///database/scraper.db
```

### 5. Launch the Server
```bash
python run.py
```
The application will start, seed database configurations automatically, and be accessible at **`http://127.0.0.1:5000`**.

---

## 🛠️ Configuration Settings (`.env`)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLASK_ENV` | String | `production` | Environment type (`development` or `production`) |
| `SECRET_KEY` | String | *Required* | Secret key for session encryption & CSRF tokens |
| `DEBUG` | Boolean | `False` | Enables or disables interactive debug tools |
| `DATABASE_URL` | String | `sqlite:///database/scraper.db` | Target database connection URI |
| `RATELIMIT_DEFAULT` | String | `100 per minute` | Default global API rate limit constraint |

---

## 🔒 Security Compliance

This platform enforces secure engineering best practices:
- **Input Sanitization:** Uses `bleach` and custom content validators to strip dangerous Javascript/HTML injection payloads before database commit.
- **Robust Rate-Limiting:** Defends against scraping-abuse/DoS using local in-memory window limitation schemas.
- **Strict Headers:** Employs security middleware to restrict frame injection, content sniffing, and force standard CORS controls.

---

## 📄 License
Distributed under the MIT License. See [LICENSE](LICENSE) for more details.

