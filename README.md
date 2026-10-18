# LinkedIn Post Resource Extractor

A local Python project that accepts a LinkedIn post URL and collects accessible post details, links, link labels/context, image URLs, and a screenshot. It exports CSV, JSON, TXT, and ZIP reports.

## Features

- Streamlit web UI running locally on your computer
- Visible Chrome mode with a dedicated persistent browser profile
- Headless mode for publicly accessible pages
- Collects page metadata, post text, external hyperlinks, link labels, nearby context, and accessible image URLs
- Best-effort redirect resolution for recognized short-link services
- Optional image downloads with an 8 MB per-image limit
- Screenshot and machine-readable CSV/JSON exports
- Deduplicates URLs and records the source/context when available

## Important limitations

LinkedIn can require login, limit visibility, lazy-load content, or change its HTML structure. This project only inspects content accessible to the browser and does not bypass access controls. It cannot guarantee that every comment, image, or hidden attachment will be found. You may need to sign in manually in the separate browser window and expand/scroll the post before extraction.

Use the tool only for content you are allowed to access and respect LinkedIn's terms and privacy expectations. Do not share the `browser_profile` directory: it may contain authentication session data.

## Windows setup

Recommended: Windows 10/11, Python 3.11–3.14.

1. Extract the ZIP file to a folder, for example `D:\Python Project\LinkedIn Post Extractor`.
2. Open PowerShell in that folder.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run the app using the venv Python directly:
   `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. Install Playwright Chromium:

   ```powershell
   python -m playwright install chromium
   ```

6. Start the app:

   ```powershell
   python -m streamlit run app.py
   ```

7. Open the local address Streamlit prints, usually `http://localhost:8501`.

You can also double-click `run_windows.bat` after dependencies are installed.

## Using the tool

1. Paste a LinkedIn post URL, such as `https://lnkd.in/p/dzaCm3GR`.
2. Choose **Visible Chrome** if the post needs a sign-in session. It opens a separate browser profile. Sign in manually if required.
3. Set a wait delay long enough for the post to load. You can also expand the post and load comments in the browser before the extraction delay ends.
4. Choose whether to resolve known short links and download images.
5. Click **Extract post details**.
6. Download the ZIP report or individual CSV/JSON/TXT files.

## Output files

- `post_details.json`: metadata, text, link records, image records, and extraction information
- `links.csv`: link name/label, original URL, resolved destination (if found), source container, context
- `images.csv`: image URL, alt text, source, dimensions, local path, download status
- `post_text.txt`: extracted text
- `post_screenshot.png`: screenshot of the loaded page
- `images/`: downloaded accessible images, if enabled
- `summary.json`: counts and page information
- `linkedin_extraction_report.zip`: all output files

## Troubleshooting

- **No links found:** switch to Visible Chrome, sign in manually if required, increase the wait delay, and confirm the post opens in the browser.
- **Browser install error:** run `python -m playwright install chromium`.
- **Chrome profile already in use:** close the other instance of this project's browser and retry.
- **Links are missing:** increase scroll rounds; expand “See more” and load comments. No extractor can guarantee hidden/private content.
- **Short link not resolved:** the shortener may block automated requests, require cookies, or use a redirect mechanism the resolver does not support. The original URL is still saved.
- **Images don't download:** the host may block requests, require authorization, or use a URL that expires. The image URL is still recorded when detected.

## Project structure

```text
linkedin_post_extractor/
├── app.py
├── requirements.txt
├── README.md
├── run_windows.bat
├── .gitignore
└── outputs/
```

Generated reports and the browser profile are created locally and should not be uploaded to a public repository if they contain private content or session data.
