# Agriculture Pest Management

This project helps track pest reports, treatments, and outcomes for different crops and regions.
It is built with Flask and PostgreSQL, with simple reports and recommendations for farmers.

## Main Features

- CRUD for regions, crops, pests, treatments, pest reports, and treatment applications
- Farmer signup/login and admin login
- Reports for pest counts, pests by crop, and treatment effectiveness
- Dashboard charts
- Treatment recommendation based on pest + crop

## Tech Stack

- Python 3
- Flask
- PostgreSQL
- HTML, Bootstrap, Jinja2
- Chart.js

## How to Run

1. Make sure PostgreSQL server is running.
2. Open terminal in `agriculture_pest_app`.
3. Run:

```bash
pip install -r requirements.txt
python3 run_postgres.py
```

4. Open `http://127.0.0.1:5001`
