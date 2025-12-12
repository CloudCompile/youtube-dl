#!/usr/bin/env python
# coding: utf-8

from __future__ import unicode_literals

import logging
import os
import sys
import threading
import time
import uuid

# Add parent directory to path to import youtube_dl
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, send_file, Response

import youtube_dl

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread-safe lock for downloads dictionary
downloads_lock = threading.Lock()

# Store download progress and status
# Max entries to prevent memory leaks
MAX_DOWNLOADS = 100
downloads = {}
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')

# Create downloads directory if it doesn't exist
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


def cleanup_old_downloads():
    """Remove old download entries to prevent memory leaks."""
    with downloads_lock:
        if len(downloads) > MAX_DOWNLOADS:
            # Sort by status: keep 'downloading' and 'processing', remove old 'complete' and 'error'
            removable = [
                k for k, v in downloads.items()
                if v['status'] in ('complete', 'error')
            ]
            # Remove oldest entries (first half of removable)
            for key in removable[:len(removable) // 2]:
                download = downloads[key]
                if download.get('filename') and os.path.exists(download['filename']):
                    try:
                        os.remove(download['filename'])
                    except OSError as e:
                        logger.warning("Failed to remove file %s: %s", download['filename'], e)
                del downloads[key]


class DownloadLogger:
    """Logger for youtube-dl that captures output."""

    def __init__(self, download_id):
        self.download_id = download_id

    def debug(self, msg):
        if self.download_id in downloads:
            downloads[self.download_id]['logs'].append(msg)

    def warning(self, msg):
        if self.download_id in downloads:
            downloads[self.download_id]['logs'].append('WARNING: ' + msg)

    def error(self, msg):
        if self.download_id in downloads:
            downloads[self.download_id]['logs'].append('ERROR: ' + msg)
            downloads[self.download_id]['error'] = msg


def progress_hook(download_id):
    """Create a progress hook for tracking download status."""

    def hook(d):
        if download_id not in downloads:
            return

        if d['status'] == 'downloading':
            downloads[download_id]['status'] = 'downloading'
            downloads[download_id]['progress'] = d.get('_percent_str', '0%').strip()
            downloads[download_id]['speed'] = d.get('_speed_str', 'N/A')
            downloads[download_id]['eta'] = d.get('_eta_str', 'N/A')
        elif d['status'] == 'finished':
            downloads[download_id]['status'] = 'processing'
            downloads[download_id]['progress'] = '100%'
            downloads[download_id]['filename'] = d.get('filename', '')

    return hook


def do_download(download_id, url, format_id=None):
    """Perform the actual download in a background thread."""
    try:
        output_template = os.path.join(DOWNLOAD_DIR, download_id + '_%(title)s.%(ext)s')

        ydl_opts = {
            'outtmpl': output_template,
            'logger': DownloadLogger(download_id),
            'progress_hooks': [progress_hook(download_id)],
            'noplaylist': True,
        }

        if format_id:
            ydl_opts['format'] = format_id

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.startswith(download_id + '_'):
                downloads[download_id]['filename'] = os.path.join(DOWNLOAD_DIR, filename)
                downloads[download_id]['status'] = 'complete'
                downloads[download_id]['progress'] = '100%'
                return

        # If we get here, download may have failed
        if downloads[download_id]['status'] != 'error':
            downloads[download_id]['status'] = 'error'
            downloads[download_id]['error'] = 'Download completed but file not found'

    except Exception as e:
        downloads[download_id]['status'] = 'error'
        downloads[download_id]['error'] = str(e)


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Get video information without downloading."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Extract relevant information
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    format_info = {
                        'format_id': f.get('format_id', 'unknown'),
                        'ext': f.get('ext', 'unknown'),
                        'quality': f.get('format_note', f.get('quality', 'unknown')),
                        'filesize': f.get('filesize', 0),
                        'resolution': f.get('resolution', 'audio only' if f.get('vcodec') == 'none' else 'unknown'),
                    }
                    formats.append(format_info)

            result = {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'formats': formats,
            }

            return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a video download."""
    data = request.get_json()
    url = data.get('url', '').strip()
    format_id = data.get('format_id')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    # Clean up old downloads to prevent memory leaks
    cleanup_old_downloads()

    # Generate a unique download ID
    download_id = str(uuid.uuid4())[:8]

    # Initialize download tracking (thread-safe)
    with downloads_lock:
        downloads[download_id] = {
            'status': 'starting',
            'progress': '0%',
            'speed': 'N/A',
            'eta': 'N/A',
            'filename': None,
            'error': None,
            'logs': [],
        }

    # Start download in background thread
    thread = threading.Thread(target=do_download, args=(download_id, url, format_id))
    thread.daemon = True
    thread.start()

    return jsonify({'download_id': download_id})


@app.route('/api/status/<download_id>')
def get_status(download_id):
    """Get the status of a download."""
    if download_id not in downloads:
        return jsonify({'error': 'Download not found'}), 404

    status = downloads[download_id].copy()
    # Don't send all logs, just the last few
    status['logs'] = status['logs'][-5:] if status['logs'] else []

    return jsonify(status)


@app.route('/api/file/<download_id>')
def download_file(download_id):
    """Download the completed file."""
    if download_id not in downloads:
        return jsonify({'error': 'Download not found'}), 404

    download = downloads[download_id]

    if download['status'] != 'complete':
        return jsonify({'error': 'Download not complete'}), 400

    if not download['filename'] or not os.path.exists(download['filename']):
        return jsonify({'error': 'File not found'}), 404

    filename = os.path.basename(download['filename'])
    # Remove the download_id prefix from the filename for the user
    if filename.startswith(download_id + '_'):
        filename = filename[len(download_id) + 1:]

    return send_file(
        download['filename'],
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/cleanup/<download_id>', methods=['POST'])
def cleanup_download(download_id):
    """Clean up a completed download."""
    with downloads_lock:
        if download_id in downloads:
            download = downloads[download_id]
            if download['filename'] and os.path.exists(download['filename']):
                try:
                    os.remove(download['filename'])
                except OSError as e:
                    logger.warning("Failed to cleanup file %s: %s", download['filename'], e)
            del downloads[download_id]

    return jsonify({'success': True})


if __name__ == '__main__':
    # Use environment variables for production configuration
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(debug=debug_mode, host=host, port=port)
