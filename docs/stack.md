# Tech Stack

This document outlines the technology stack used in this project.

## Backend

*   **Programming Language:** Python 3
*   **Web Framework:** [Flask](https://flask.palletsprojects.com/)
*   **Authentication:**
    *   [Flask-Login](https://flask-login.readthedocs.io/) for session-based authentication.
    *   [Flask-JWT-Extended](https://flask-jwt-extended.readthedocs.io/) for API authentication using JSON Web Tokens.
*   **Forms:** [Flask-WTF](https://flask-wtf.readthedocs.io/) for handling web forms.
*   **Environment Variables:** [python-dotenv](https://github.com/theskumar/python-dotenv) for managing configuration.
*   **CLI:** [Click](https://click.palletsprojects.com/) for creating command-line interfaces.

## Frontend

*   **Markup:** HTML5
*   **Styling:** CSS3 with a custom theme (`fairyfloss.css`).
*   **JavaScript:** Vanilla JavaScript (no major frameworks like React or Vue.js).

## Database

*   **Primary Database:** [SQLite](https://www.sqlite.org/index.html) for storing application data.
*   **In-Memory Data Store:** [Redis](https://redis.io/) for blacklisting JWT tokens.

## Testing

*   **Testing Framework:** [Pytest](https://docs.pytest.org/) for running automated tests.
