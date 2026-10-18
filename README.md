# LinkedIn Post Resource Extractor

**Turn LinkedIn posts into organized, usable resources with Python.**

LinkedIn posts often contain valuable learning resources, cybersecurity labs, GitHub repositories, courses, and useful websites. Manually collecting these resources can be time-consuming.

**LinkedIn Post Resource Extractor** is a Python-based web application designed to simplify this process by extracting accessible information from a LinkedIn post URL and organizing it into convenient formats.

## Features

- **Link Extraction:** Collects accessible external URLs from a post.
- **Link Names and Context:** Captures available link text and surrounding information to help identify each resource.
- **Image Detection and Download:** Detects and downloads accessible post images.
- **Shortened URL Resolution:** Attempts to resolve supported shortened links to their destination URLs.
- **Multiple Export Formats:** Exports collected information to CSV, JSON, and TXT files.
- **Screenshot Capture:** Saves a screenshot of the loaded page.
- **Browser Automation:** Uses Playwright to load and inspect dynamic web content.
- **Simple Web Interface:** Provides an easy-to-use interface powered by Streamlit.
- **Report Packaging:** Organizes collected results into a downloadable report.

## Who Can Benefit?

- **Students:** Collect free courses, tutorials, and study materials.
- **Cybersecurity Learners:** Organize security labs, tools, and research resources.
- **Developers:** Gather GitHub repositories, documentation, and programming tutorials.
- **Researchers:** Organize useful links and related images.
- **Non-LinkedIn Users:** Access external resources extracted from publicly accessible posts without manually navigating LinkedIn.

## Tech Stack

- **Python** — Core programming language
- **Streamlit** — Web interface
- **Playwright** — Browser automation
- **Requests** — HTTP requests and resource downloads
- **CSV, JSON, TXT** — Data export formats

## Getting Started

### Prerequisites

- Python 3.10 or later
- pip package manager
- Internet connection
- A supported browser environment for Playwright

### Installation

1. Clone this repository:

   ```bash
   git clone YOUR_REPOSITORY_URL
   ```

2. Navigate to the project directory:

   ```bash
   cd LinkedIn_Post_Resource_Extractor
   ```

3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install the Playwright browser:

   ```bash
   playwright install chromium
   ```

5. Start the application:

   ```bash
   streamlit run app.py
   ```

6. Open the local URL displayed in your terminal, enter a LinkedIn post URL, and follow the application's instructions.

## Output

Depending on the information accessible on the page, the application can generate:

- Extracted links with their available names and context
- JSON and CSV data files
- A text summary
- Downloaded images
- A screenshot of the loaded page
- A packaged report containing collected results

## Limitations

The extractor can only collect information that is accessible to its browser session. LinkedIn login requirements, access restrictions, dynamic page behavior, and anti-automation protections may limit results.

It does not guarantee extraction of every comment, link, or image, and it does not bypass authentication or access controls. Shortened URL resolution depends on destination availability and network restrictions.

Use this tool responsibly and respect LinkedIn's terms, website policies, privacy, and applicable laws.

## Future Improvements

- More reliable identification of links and their associated titles
- Improved image filtering and duplicate detection
- Support for batch processing multiple post URLs
- Advanced search and filtering for extracted resources
- Additional export formats
- Better extraction summaries and reporting

## Author

**SKLearn Academy**

Built with Python to make collecting and organizing online learning resources easier.

**Learn | Build | Grow**

#Python #Automation #Playwright #Streamlit #Cybersecurity #WebAutomation
