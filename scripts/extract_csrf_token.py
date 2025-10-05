#!/usr/bin/env python3
"""Extract the CSRF token from the saved login page."""

import re
from pathlib import Path

LOGIN_HTML = Path('/tmp/posa-login.html')
TOKEN_PATH = Path('/tmp/posa-token.txt')


def main():
    if not LOGIN_HTML.exists():
        raise SystemExit('Login HTML not found. Run the curl command first to save it.')

    html = LOGIN_HTML.read_text()
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise SystemExit('CSRF token not found. Make sure you are logged out and reran curl.')
    token = match.group(1)

    TOKEN_PATH.write_text(token)
    print(f'Token: {token}')


if __name__ == '__main__':
    main()
