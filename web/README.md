# YouTube Downloader Web Interface

A simple browser-based web interface for downloading YouTube videos using youtube-dl.

## Features

- Clean, modern web interface
- Enter any YouTube video URL
- View video information (title, thumbnail, duration, uploader)
- Select video quality/format
- Track download progress in real-time
- Download the video file directly to your computer

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements-web.txt
```

2. Run the web application:

```bash
cd web
python app.py
```

3. Open your browser and go to: `http://localhost:5000`

## Configuration

You can configure the server using environment variables:

```bash
# Set debug mode (default: true)
export FLASK_DEBUG=false

# Set host (default: 127.0.0.1)
export FLASK_HOST=0.0.0.0

# Set port (default: 5000)
export FLASK_PORT=8080
```

## Usage

1. Paste a YouTube URL in the input field
2. Click "Get Info" to fetch video details
3. Select your preferred quality/format
4. Click "Download Video"
5. Wait for the download to complete
6. Click "Save to Computer" to download the file to your device

## GitHub Pages

A static landing page is deployed to GitHub Pages that provides documentation and quick start instructions. The actual downloader application requires self-hosting since it's a dynamic Flask application.

To deploy to GitHub Pages:
1. Go to your repository Settings → Pages
2. Set the source to "GitHub Actions"
3. The workflow in `.github/workflows/deploy-pages.yml` will deploy automatically

## Screenshots

The interface provides a simple, intuitive way to download videos:

- Paste URL → View video info → Choose quality → Download

## Note

This web interface is intended for personal use. Please respect YouTube's Terms of Service and only download videos you have permission to download.
