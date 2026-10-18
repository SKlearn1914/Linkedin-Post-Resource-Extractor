from __future__ import annotations

import csv
import ipaddress
import json
import re
import shutil
import socket
import time
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


APP_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = APP_DIR / "outputs"
PROFILE_DIR = APP_DIR / "browser_profile"
OUTPUTS_DIR.mkdir(exist_ok=True)

SHORTENER_DOMAINS = {
    "lnkd.in", "bit.ly", "t.co", "tinyurl.com", "ow.ly",
    "buff.ly", "shorturl.at", "rb.gy", "is.gd", "cutt.ly",
    "rebrand.ly", "goo.gl"
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please enter a valid http:// or https:// URL.")
    return url


def host_is_public(host: str) -> bool:
    """Reject localhost/private/reserved IP destinations before optional requests."""
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        addresses = {info[4][0] for info in infos}
        return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
    except (OSError, ValueError):
        return False


def safe_request_one_hop(url: str, timeout: int = 8):
    """Make one request without following redirects; validate each hop separately."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not host_is_public(parsed.hostname or ""):
        raise ValueError("Blocked non-public or invalid destination.")
    response = requests.get(
        url,
        allow_redirects=False,
        stream=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    return response


def resolve_short_url(url: str, max_hops: int = 8) -> str:
    """Resolve known shorteners with bounded, manually validated redirects."""
    current = url
    for _ in range(max_hops):
        parsed = urlparse(current)
        host = (parsed.hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in SHORTENER_DOMAINS):
            return current
        response = None
        try:
            response = safe_request_one_hop(current)
            location = response.headers.get("Location")
            status = response.status_code
        except Exception:
            return current
        finally:
            if response is not None:
                response.close()

        if status not in {301, 302, 303, 307, 308} or not location:
            return current
        next_url = urljoin(current, location)
        next_parsed = urlparse(next_url)
        if next_parsed.scheme not in {"http", "https"}:
            return current
        if not host_is_public(next_parsed.hostname or ""):
            return current
        current = next_url
    return current


def download_image(url: str, destination: Path, max_bytes: int = 8 * 1024 * 1024) -> tuple[bool, str]:
    """Download an image only from public HTTP(S) hosts, with a size limit."""
    response = None
    try:
        response = safe_request_one_hop(url, timeout=12)
        # Follow only a small number of validated redirects.
        hops = 0
        while response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            response = None
            if not location or hops >= 5:
                return False, "Redirect limit reached"
            url = urljoin(url, location)
            response = safe_request_one_hop(url, timeout=12)
            hops += 1

        if response.status_code >= 400:
            return False, f"HTTP {response.status_code}"
        content_type = response.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            return False, f"Not an image ({content_type or 'unknown content type'})"

        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            return False, "Image exceeds 8 MB limit"

        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    file.close()
                    destination.unlink(missing_ok=True)
                    return False, "Image exceeds 8 MB limit"
                file.write(chunk)
        return True, "Downloaded"
    except Exception as exc:
        return False, str(exc)[:180]
    finally:
        if response is not None:
            response.close()


EXTRACT_JS = r"""
() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const meta = (name, property = false) => {
    const selector = property
      ? `meta[property="${name}"]`
      : `meta[name="${name}"]`;
    return document.querySelector(selector)?.content || "";
  };

  // Prefer recognizable LinkedIn post/comment containers; fall back to main.
  const selectors = [
    ".feed-shared-update-v2",
    ".occludable-update",
    "[data-urn*='activity']",
    ".comments-comment-item",
    "article"
  ];
  let roots = [];
  for (const selector of selectors) {
    const found = [...document.querySelectorAll(selector)];
    if (found.length) {
      roots = roots.concat(found);
    }
  }
  roots = [...new Set(roots)];
  if (!roots.length) {
    roots = [document.querySelector("main") || document.body];
  }

  // Remove nested duplicates when an outer post container already contains them.
  roots = roots.filter((node, i) =>
    !roots.some((other, j) => i !== j && other !== node && other.contains(node))
  );

  const allAnchors = [];
  for (const root of roots) {
    for (const a of root.querySelectorAll("a[href]")) {
      allAnchors.push({a, root});
    }
  }

  const links = [];
  const seenLinks = new Set();
  for (const {a, root} of allAnchors) {
    const href = a.href || "";
    if (!/^https?:\/\//i.test(href)) continue;
    const key = href;
    if (seenLinks.has(key)) continue;
    seenLinks.add(key);

    let contextNode = a;
    let context = "";
    for (let i = 0; i < 5 && contextNode; i++, contextNode = contextNode.parentElement) {
      const t = clean(contextNode.innerText);
      if (t.length >= 12 && t.length <= 1200) {
        context = t;
        if (contextNode.matches(".feed-shared-update-v2__description, .comments-comment-item, article")) break;
      }
    }

    const name = clean(a.innerText) ||
                 clean(a.getAttribute("aria-label")) ||
                 clean(a.getAttribute("title")) ||
                 clean(a.querySelector("img")?.alt) ||
                 "";
    links.push({
      name,
      original_url: href,
      context: context.slice(0, 1200),
      source_container: root.matches(".comments-comment-item") ? "comment" : "post_or_page"
    });
  }

  const images = [];
  const seenImages = new Set();
  const addImage = (url, alt, source, width, height) => {
    if (!url || !/^https?:\/\//i.test(url) || seenImages.has(url)) return;
    seenImages.add(url);
    images.push({
      image_url: url,
      alt_text: clean(alt),
      source,
      width: width || 0,
      height: height || 0
    });
  };

  const ogImage = meta("og:image", true) || meta("twitter:image");
  if (ogImage) addImage(ogImage, meta("og:title", true), "open_graph_preview", 0, 0);

  for (const root of roots) {
    for (const img of root.querySelectorAll("img")) {
      const url = img.currentSrc || img.src ||
                  img.getAttribute("data-delayed-url") ||
                  img.getAttribute("data-ghost-url") || "";
      if (img.naturalWidth >= 120 || img.naturalHeight >= 120 ||
          img.getAttribute("data-delayed-url")) {
        addImage(
          url,
          img.alt || img.getAttribute("aria-label") || "",
          "post_content",
          img.naturalWidth || img.width,
          img.naturalHeight || img.height
        );
      }
    }
  }

  const textCandidates = roots
    .map(root => clean(root.innerText))
    .filter(t => t.length > 30)
    .sort((a, b) => b.length - a.length);

  const postText = textCandidates[0] || clean((document.querySelector("main") || document.body).innerText);

  return {
    page_title: document.title || "",
    canonical_url: document.querySelector('link[rel="canonical"]')?.href || location.href,
    page_url: location.href,
    author: meta("author") || "",
    og_title: meta("og:title", true),
    description: meta("og:description", true) || meta("description"),
    published_time: meta("article:published_time", true),
    post_text: postText,
    links,
    images
  };
}
"""


def click_expand_controls(page):
    """Click common expand controls, without attempting to evade access controls."""
    try:
        page.evaluate(r"""
        () => {
          const re = /\b(see more|show more|more comments|view more comments|load more comments)\b/i;
          const candidates = [...document.querySelectorAll(
            'button, [role="button"], .feed-shared-inline-show-more-text'
          )];
          for (const el of candidates.slice(0, 60)) {
            const label = (el.innerText || el.getAttribute("aria-label") || "").trim();
            if (label && re.test(label) && el.getClientRects().length) {
              try { el.click(); } catch (_) {}
            }
          }
        }
        """)
    except Exception:
        pass


def scroll_page(page, rounds: int):
    for _ in range(rounds):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(900)
        except Exception:
            break


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_zip(folder: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in folder.rglob("*"):
            if item.is_file() and item != zip_path:
                archive.write(item, item.relative_to(folder))


def extract_post(
    post_url: str,
    browser_mode: str,
    wait_seconds: int,
    scroll_rounds: int,
    resolve_short_links: bool,
    download_images: bool,
) -> Path:
    post_url = normalize_url(post_url)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = OUTPUTS_DIR / f"linkedin_extract_{stamp}"
    folder.mkdir(parents=True, exist_ok=True)

    browser = None
    context = None
    playwright = None

    try:
        playwright = sync_playwright().start()
        if browser_mode == "Visible Chrome (persistent login profile)":
            PROFILE_DIR.mkdir(exist_ok=True)
            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1440, "height": 1000},
                    args=["--disable-notifications"],
                )
            except Exception:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    viewport={"width": 1440, "height": 1000},
                    args=["--disable-notifications"],
                )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()

        page.set_default_timeout(10000)
        page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_seconds * 1000)

        click_expand_controls(page)
        scroll_page(page, scroll_rounds)
        click_expand_controls(page)
        page.wait_for_timeout(1500)

        try:
            page.screenshot(path=str(folder / "post_screenshot.png"), full_page=True)
        except Exception:
            pass

        data = page.evaluate(EXTRACT_JS)
        data["input_url"] = post_url
        data["extracted_at"] = datetime.now().astimezone().isoformat()
        data["browser_mode"] = browser_mode
        data["note"] = (
            "Only content loaded and accessible in the browser was inspected. "
            "This report does not bypass login, privacy, or platform access restrictions."
        )

        # Resolve only recognized shorteners and only when the user opts in.
        for link in data.get("links", []):
            original = link.get("original_url", "")
            link["destination_url"] = (
                resolve_short_url(original)
                if resolve_short_links
                else ""
            )

        image_dir = folder / "images"
        for index, img in enumerate(data.get("images", []), start=1):
            img["local_file"] = ""
            img["download_status"] = "Not requested"
            if download_images:
                parsed = urlparse(img.get("image_url", ""))
                ext = Path(parsed.path).suffix.lower()
                if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
                    ext = ".png"
                dest = image_dir / f"image_{index:02d}{ext}"
                ok, message = download_image(img.get("image_url", ""), dest)
                img["download_status"] = message
                if ok:
                    img["local_file"] = str(dest.relative_to(folder))

        # Write all machine-readable and human-readable outputs.
        (folder / "post_details.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        (folder / "post_text.txt").write_text(
            data.get("post_text", ""),
            encoding="utf-8"
        )
        write_csv(
            folder / "links.csv",
            data.get("links", []),
            ["name", "original_url", "destination_url", "context", "source_container"]
        )
        write_csv(
            folder / "images.csv",
            data.get("images", []),
            ["image_url", "alt_text", "source", "width", "height", "local_file", "download_status"]
        )

        # Include an explicit extraction summary.
        summary = {
            "input_url": post_url,
            "page_url": data.get("page_url", ""),
            "page_title": data.get("page_title", ""),
            "links_found": len(data.get("links", [])),
            "images_found": len(data.get("images", [])),
            "output_folder": str(folder),
        }
        (folder / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        make_zip(folder, folder / "linkedin_extraction_report.zip")
        return folder

    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass


# ------------------------------- Streamlit UI -------------------------------

st.set_page_config(
    page_title="LinkedIn Post Resource Extractor",
    page_icon="🔎",
    layout="wide"
)

st.title("LinkedIn Post Resource Extractor")
st.caption(
    "Extract post details, external links, link labels, visible post images, "
    "and export everything into CSV, JSON, TXT, and ZIP."
)

with st.expander("What this tool can and cannot do", expanded=False):
    st.markdown(
        """
        **Can:** inspect content visible to the browser, collect link text and nearby context,
        capture page metadata, identify accessible post images, save a screenshot, and export reports.

        **Cannot guarantee:** every comment, hidden attachment, or link on every LinkedIn page.
        LinkedIn may require login or may change its page structure. This tool does not bypass
        access controls, scrape private content, or defeat anti-bot protections.

        **Privacy:** visible-browser mode uses a dedicated local browser profile in this project
        folder. Sign in only if you choose to, and do not share that profile folder because it
        may contain session data.
        """
    )

with st.form("extract_form"):
    post_url = st.text_input(
        "LinkedIn post URL",
        placeholder="https://lnkd.in/p/dzaCm3GR",
        help="Paste the post URL or another HTTP/HTTPS URL for a post you are allowed to view."
    )
    browser_mode = st.radio(
        "Browser mode",
        [
            "Public page (headless; no manual login)",
            "Visible Chrome (persistent login profile)"
        ],
        index=1,
        help=(
            "Visible Chrome opens a separate browser profile. If LinkedIn asks you to sign in, "
            "sign in manually in that window. The extractor waits for the delay selected below."
        )
    )
    col1, col2 = st.columns(2)
    with col1:
        wait_seconds = st.slider(
            "Wait before extraction (seconds)",
            min_value=5, max_value=90, value=25, step=5,
            help="In visible mode, use this time to sign in and let the post load."
        )
        scroll_rounds = st.slider(
            "Scroll rounds to load more content",
            min_value=0, max_value=10, value=3
        )
    with col2:
        resolve_short_links = st.checkbox(
            "Resolve known short links (best effort)",
            value=True,
            help="Makes network requests only to recognized shortener domains and validates redirect hosts."
        )
        download_images = st.checkbox(
            "Download accessible post images",
            value=True,
            help="Saves images from public HTTP/HTTPS hosts, with an 8 MB per-image limit."
        )
    submitted = st.form_submit_button("Extract post details", type="primary", use_container_width=True)

if submitted:
    if not post_url.strip():
        st.error("Paste a LinkedIn post URL first.")
    else:
        try:
            with st.spinner(
                "Opening the post and collecting accessible details. "
                "Visible Chrome may open in a separate window..."
            ):
                output_folder = extract_post(
                    post_url=post_url,
                    browser_mode=browser_mode,
                    wait_seconds=wait_seconds,
                    scroll_rounds=scroll_rounds,
                    resolve_short_links=resolve_short_links,
                    download_images=download_images,
                )
            st.session_state["last_output_folder"] = str(output_folder)
            st.success("Extraction finished. Review the files and results below.")
        except PlaywrightTimeoutError:
            st.error("The page timed out. Check the URL, internet connection, and whether the post requires login.")
        except Exception as exc:
            st.error(f"Extraction failed: {exc}")
            st.info(
                "Try Visible Chrome mode, confirm the URL opens normally, and ensure Chromium is installed "
                "using: python -m playwright install chromium"
            )

if st.session_state.get("last_output_folder"):
    folder = Path(st.session_state["last_output_folder"])
    if folder.exists():
        st.subheader("Latest extraction")
        try:
            data = json.loads((folder / "post_details.json").read_text(encoding="utf-8"))
            c1, c2, c3 = st.columns(3)
            c1.metric("Links found", len(data.get("links", [])))
            c2.metric("Images found", len(data.get("images", [])))
            c3.metric("Post text characters", len(data.get("post_text", "")))
            st.write("**Page title:**", data.get("og_title") or data.get("page_title") or "(not detected)")
            st.write("**Resolved page URL:**", data.get("page_url", ""))

            links = data.get("links", [])
            if links:
                st.markdown("### Extracted links")
                st.dataframe(
                    [
                        {
                            "Name / label": item.get("name") or "(no link text; see context)",
                            "Original URL": item.get("original_url", ""),
                            "Destination URL": item.get("destination_url", ""),
                            "Source": item.get("source_container", ""),
                            "Context": item.get("context", "")[:240],
                        }
                        for item in links
                    ],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning(
                    "No external links were detected in the selected content. "
                    "The page may require login, or LinkedIn may have changed its layout."
                )

            images = data.get("images", [])
            if images:
                st.markdown("### Detected post images")
                st.dataframe(
                    [
                        {
                            "Alt text": img.get("alt_text", ""),
                            "Image URL": img.get("image_url", ""),
                            "Source": img.get("source", ""),
                            "Dimensions": f"{img.get('width', 0)} × {img.get('height', 0)}",
                            "Download status": img.get("download_status", ""),
                            "Local file": img.get("local_file", ""),
                        }
                        for img in images
                    ],
                    use_container_width=True,
                    hide_index=True
                )
                downloaded = [
                    folder / item["local_file"]
                    for item in images
                    if item.get("local_file") and (folder / item["local_file"]).exists()
                ]
                if downloaded:
                    cols = st.columns(min(3, len(downloaded)))
                    for i, image_path in enumerate(downloaded[:12]):
                        with cols[i % len(cols)]:
                            st.image(str(image_path), caption=image_path.name, use_container_width=True)

            st.markdown("### Download your report")
            zip_path = folder / "linkedin_extraction_report.zip"
            if zip_path.exists():
                st.download_button(
                    "Download complete report (ZIP)",
                    data=zip_path.read_bytes(),
                    file_name=zip_path.name,
                    mime="application/zip",
                    use_container_width=True
                )
            for filename, label, mime in [
                ("links.csv", "Download links CSV", "text/csv"),
                ("images.csv", "Download images CSV", "text/csv"),
                ("post_details.json", "Download full JSON", "application/json"),
                ("post_text.txt", "Download post text", "text/plain"),
                ("post_screenshot.png", "Download page screenshot", "image/png"),
            ]:
                path = folder / filename
                if path.exists():
                    with st.expander(label):
                        st.download_button(
                            label,
                            data=path.read_bytes(),
                            file_name=filename,
                            mime=mime,
                            key=f"download_{filename}_{folder.name}",
                        )
        except Exception as exc:
            st.error(f"Could not load the report: {exc}")

st.divider()
st.caption(
    "Tip: for best results, use Visible Chrome mode, allow the post to load, expand 'See more', "
    "and scroll enough to load comments before extraction."
)
