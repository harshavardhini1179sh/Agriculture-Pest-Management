import os
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import db
import config as config_module

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

def _farmer_by_email(email):
    """Return farmer signup row dict if email exists, else None."""
    if not (email or "").strip():
        return None
    rows = db.execute_query(
        """
        SELECT name, email, password_hash, created_at
        FROM farmer_signup
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
        LIMIT 1
        """,
        (email.strip().lower(),),
    )
    return rows[0] if rows else None


def _add_farmer(name, email, password_hash_value):
    """Insert a new farmer signup row."""
    db.execute_update_delete(
        """
        INSERT INTO farmer_signup (name, email, password_hash)
        VALUES (%s, %s, %s)
        """,
        ((name or "").strip(), (email or "").strip().lower(), password_hash_value),
    )


# ---------- Home / Dashboard ----------
@app.route("/")
def index():
    try:
        recent = db.execute_query("""
            SELECT pr.report_id, pr.status, p.common_name AS pest_name, c.name AS crop_name, r.name AS region_name
            FROM pest_report pr
            JOIN pest p ON pr.pest_id = p.pest_id
            JOIN crop c ON pr.crop_id = c.crop_id
            JOIN region r ON pr.region_id = r.region_id
            ORDER BY pr.report_id DESC LIMIT 8
        """)
    except Exception:
        recent = []
    return render_template("index.html", recent=recent)


# ---------- Farmer signup / login (stored in PostgreSQL table farmer_signup) ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not name:
            flash("Please enter your name.")
            return render_template("signup.html")
        if not email:
            flash("Please enter your email.")
            return render_template("signup.html")
        if not password or len(password) < 4:
            flash("Password must be at least 4 characters.")
            return render_template("signup.html")
        if password != confirm:
            flash("Passwords do not match.")
            return render_template("signup.html")
        if _farmer_by_email(email):
            flash("An account with this email already exists. Please log in.")
            return redirect(url_for("login"))
        try:
            _add_farmer(name, email, generate_password_hash(password))
        except psycopg2.errors.UniqueViolation:
            flash("An account with this email already exists. Please log in.")
            return redirect(url_for("login"))
        flash("Signup successful. Please log in.")
        return redirect(url_for("login"))
    return render_template("signup.html")


def _is_admin(email, password):
    if not email or not password:
        return False
    return (email.strip().lower() == config_module.ADMIN_EMAIL and
            password == config_module.ADMIN_PASSWORD)


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("index")
    reason = request.args.get("reason") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        next_url = request.form.get("next") or request.args.get("next") or url_for("index")
        if _is_admin(email, password):
            session["admin"] = True
            session["farmer_email"] = email
            session["farmer_name"] = "Admin"
            return redirect(next_url)
        farmer = _farmer_by_email(email)
        if not farmer or not check_password_hash(farmer.get("password_hash") or "", password):
            flash("Incorrect email or password.", "danger")
            return render_template("login.html", next_url=next_url, reason=reason)
        session["admin"] = False
        session["farmer_email"] = farmer.get("email")
        session["farmer_name"] = farmer.get("name")
        return redirect(next_url)
    return render_template("login.html", next_url=next_url, reason=reason)


@app.route("/logout")
def logout():
    session.pop("farmer_email", None)
    session.pop("farmer_name", None)
    session.pop("admin", None)
    return redirect(url_for("index"))


# ---------- Region CRUD (add/edit/delete: admin only) ----------
def _require_admin():
    if not session.get("admin"):
        flash("Only admin can do that.", "danger")
        return True
    return False


@app.route("/regions")
def regions_list():
    rows = db.execute_query("SELECT * FROM region ORDER BY name")
    return render_template("regions/list.html", regions=rows, is_admin=session.get("admin"))


@app.route("/regions/add", methods=["GET", "POST"])
def region_add():
    if _require_admin():
        return redirect(url_for("regions_list"))
    if request.method == "POST":
        db.execute_insert(
            "INSERT INTO region (state_code, name) VALUES (%s, %s) RETURNING region_id",
            (request.form.get("state_code"), request.form.get("name"))
        )
        return redirect(url_for("regions_list"))
    return render_template("regions/form.html", region=None)


@app.route("/regions/<int:id>/edit", methods=["GET", "POST"])
def region_edit(id):
    if _require_admin():
        return redirect(url_for("regions_list"))
    if request.method == "POST":
        db.execute_update_delete(
            "UPDATE region SET state_code=%s, name=%s WHERE region_id=%s",
            (request.form.get("state_code"), request.form.get("name"), id)
        )
        return redirect(url_for("regions_list"))
    rows = db.execute_query("SELECT * FROM region WHERE region_id=%s", (id,))
    return render_template("regions/form.html", region=rows[0] if rows else None)


@app.route("/regions/<int:id>/delete", methods=["POST"])
def region_delete(id):
    if _require_admin():
        return redirect(url_for("regions_list"))
    db.execute_update_delete("DELETE FROM region WHERE region_id=%s", (id,))
    return redirect(url_for("regions_list"))


# ---------- Crop CRUD (add/edit/delete: admin only) ----------
@app.route("/crops")
def crops_list():
    rows = db.execute_query("""
        SELECT c.*, r.name AS region_name FROM crop c
        LEFT JOIN region r ON c.region_id = r.region_id ORDER BY c.name
    """)
    return render_template("crops/list.html", crops=rows, is_admin=session.get("admin"))


@app.route("/crops/add", methods=["GET", "POST"])
def crop_add():
    if _require_admin():
        return redirect(url_for("crops_list"))
    regions = db.execute_query("SELECT region_id, name FROM region ORDER BY name")
    if request.method == "POST":
        db.execute_insert(
            """INSERT INTO crop (region_id, name, scientific_name)
               VALUES (%s, %s, %s) RETURNING crop_id""",
            (request.form.get("region_id"), request.form.get("name"),
             request.form.get("scientific_name") or None)
        )
        return redirect(url_for("crops_list"))
    return render_template("crops/form.html", crop=None, regions=regions)


@app.route("/crops/<int:id>/edit", methods=["GET", "POST"])
def crop_edit(id):
    if _require_admin():
        return redirect(url_for("crops_list"))
    regions = db.execute_query("SELECT region_id, name FROM region ORDER BY name")
    if request.method == "POST":
        db.execute_update_delete(
            """UPDATE crop SET region_id=%s, name=%s, scientific_name=%s
               WHERE crop_id=%s""",
            (request.form.get("region_id"), request.form.get("name"),
             request.form.get("scientific_name") or None, id)
        )
        return redirect(url_for("crops_list"))
    rows = db.execute_query("SELECT * FROM crop WHERE crop_id=%s", (id,))
    return render_template("crops/form.html", crop=rows[0] if rows else None, regions=regions)


@app.route("/crops/<int:id>/delete", methods=["POST"])
def crop_delete(id):
    if _require_admin():
        return redirect(url_for("crops_list"))
    db.execute_update_delete("DELETE FROM crop WHERE crop_id=%s", (id,))
    return redirect(url_for("crops_list"))


# ---------- Pest CRUD ----------
@app.route("/pests")
def pests_list():
    rows = db.execute_query("SELECT * FROM pest ORDER BY common_name")
    return render_template("pests/list.html", pests=rows, is_admin=session.get("admin"))


@app.route("/pests/add", methods=["GET", "POST"])
def pest_add():
    if _require_admin():
        return redirect(url_for("pests_list"))
    if request.method == "POST":
        db.execute_insert(
            """INSERT INTO pest (common_name, scientific_name, pest_type, description)
               VALUES (%s, %s, %s, %s) RETURNING pest_id""",
            (request.form.get("common_name"), request.form.get("scientific_name") or None,
             request.form.get("pest_type") or None, request.form.get("description") or None)
        )
        return redirect(url_for("pests_list"))
    return render_template("pests/form.html", pest=None)


@app.route("/pests/<int:id>/edit", methods=["GET", "POST"])
def pest_edit(id):
    if _require_admin():
        return redirect(url_for("pests_list"))
    if request.method == "POST":
        db.execute_update_delete(
            """UPDATE pest SET common_name=%s, scientific_name=%s, pest_type=%s, description=%s
               WHERE pest_id=%s""",
            (request.form.get("common_name"), request.form.get("scientific_name") or None,
             request.form.get("pest_type") or None, request.form.get("description") or None, id)
        )
        return redirect(url_for("pests_list"))
    rows = db.execute_query("SELECT * FROM pest WHERE pest_id=%s", (id,))
    return render_template("pests/form.html", pest=rows[0] if rows else None)


@app.route("/pests/<int:id>/delete", methods=["POST"])
def pest_delete(id):
    if _require_admin():
        return redirect(url_for("pests_list"))
    db.execute_update_delete("DELETE FROM pest WHERE pest_id=%s", (id,))
    return redirect(url_for("pests_list"))


# ---------- Treatment CRUD ----------
@app.route("/treatments")
def treatments_list():
    rows = db.execute_query("SELECT * FROM treatment ORDER BY name")
    return render_template("treatments/list.html", treatments=rows, is_admin=session.get("admin"))


@app.route("/treatments/add", methods=["GET", "POST"])
def treatment_add():
    if _require_admin():
        return redirect(url_for("treatments_list"))
    if request.method == "POST":
        db.execute_insert(
            """INSERT INTO treatment (name, type, cost_per_acre)
               VALUES (%s, %s, %s) RETURNING treatment_id""",
            (request.form.get("name"), request.form.get("type") or None,
             request.form.get("cost_per_acre") or None)
        )
        return redirect(url_for("treatments_list"))
    return render_template("treatments/form.html", treatment=None)


@app.route("/treatments/<int:id>/edit", methods=["GET", "POST"])
def treatment_edit(id):
    if _require_admin():
        return redirect(url_for("treatments_list"))
    if request.method == "POST":
        db.execute_update_delete(
            """UPDATE treatment SET name=%s, type=%s, cost_per_acre=%s
               WHERE treatment_id=%s""",
            (request.form.get("name"), request.form.get("type") or None,
             request.form.get("cost_per_acre") or None, id)
        )
        return redirect(url_for("treatments_list"))
    rows = db.execute_query("SELECT * FROM treatment WHERE treatment_id=%s", (id,))
    return render_template("treatments/form.html", treatment=rows[0] if rows else None)


@app.route("/treatments/<int:id>/delete", methods=["POST"])
def treatment_delete(id):
    if _require_admin():
        return redirect(url_for("treatments_list"))
    db.execute_update_delete("DELETE FROM treatment WHERE treatment_id=%s", (id,))
    return redirect(url_for("treatments_list"))


# ---------- PestReport CRUD (login required; only creator or admin can edit/delete) ----------
def _require_login():
    if not session.get("farmer_email"):
        return True
    return False


def _can_edit_report(report_created_by):
    if session.get("admin"):
        return True
    return (report_created_by or "").strip().lower() == (session.get("farmer_email") or "").strip().lower()


@app.route("/reports")
def pest_reports_list():
    if _require_login():
        return redirect(url_for("login", next=url_for("pest_reports_list"), reason="pest_reports"))
    rows = db.execute_query("""
        SELECT pr.report_id, pr.pest_id, pr.crop_id, pr.region_id, pr.status, pr.created_by,
               p.common_name AS pest_name, c.name AS crop_name, r.name AS region_name
        FROM pest_report pr
        LEFT JOIN pest p ON pr.pest_id = p.pest_id
        LEFT JOIN crop c ON pr.crop_id = c.crop_id
        LEFT JOIN region r ON pr.region_id = r.region_id
        ORDER BY pr.report_id
    """)
    return render_template("pest_reports/list.html", reports=rows, current_user=session.get("farmer_email"), is_admin=session.get("admin"))


@app.route("/reports/add", methods=["GET", "POST"])
def pest_report_add():
    if _require_login():
        return redirect(url_for("login", next=url_for("pest_report_add"), reason="pest_reports"))
    pests = db.execute_query("SELECT pest_id, common_name FROM pest ORDER BY common_name")
    # One row per crop name; region is selected separately below.
    crops = db.execute_query("""
        SELECT DISTINCT ON (name) crop_id, name
        FROM crop
        ORDER BY name, crop_id
    """)
    regions = db.execute_query("SELECT region_id, name FROM region ORDER BY name")
    if request.method == "POST":
        db.execute_insert(
            """INSERT INTO pest_report (pest_id, crop_id, region_id, status, created_by)
               VALUES (%s, %s, %s, %s, %s) RETURNING report_id""",
            (request.form.get("pest_id"), request.form.get("crop_id"), request.form.get("region_id"),
             request.form.get("status") or "pending", session.get("farmer_email"))
        )
        return redirect(url_for("pest_reports_list"))
    return render_template("pest_reports/form.html", report=None, pests=pests, crops=crops, regions=regions)


@app.route("/reports/<int:id>/edit", methods=["GET", "POST"])
def pest_report_edit(id):
    if _require_login():
        return redirect(url_for("login", next=url_for("pest_report_edit", id=id), reason="pest_reports"))
    rows = db.execute_query("SELECT * FROM pest_report WHERE report_id=%s", (id,))
    if not rows:
        flash("Report not found.", "danger")
        return redirect(url_for("pest_reports_list"))
    report = rows[0]
    if not _can_edit_report(report.get("created_by")):
        flash("You can only edit your own reports. (Admin can edit any.)", "danger")
        return redirect(url_for("pest_reports_list"))
    pests = db.execute_query("SELECT pest_id, common_name FROM pest ORDER BY common_name")
    crops = db.execute_query("""
        SELECT DISTINCT ON (name) crop_id, name
        FROM crop
        ORDER BY name, crop_id
    """)
    regions = db.execute_query("SELECT region_id, name FROM region ORDER BY name")
    if request.method == "POST":
        db.execute_update_delete(
            """UPDATE pest_report SET pest_id=%s, crop_id=%s, region_id=%s, status=%s
               WHERE report_id=%s""",
            (request.form.get("pest_id"), request.form.get("crop_id"), request.form.get("region_id"),
             request.form.get("status") or "pending", id)
        )
        return redirect(url_for("pest_reports_list"))
    return render_template("pest_reports/form.html", report=report, pests=pests, crops=crops, regions=regions)


@app.route("/reports/<int:id>/delete", methods=["POST"])
def pest_report_delete(id):
    if _require_login():
        return redirect(url_for("login", next=url_for("pest_reports_list"), reason="pest_reports"))
    rows = db.execute_query("SELECT created_by FROM pest_report WHERE report_id=%s", (id,))
    if not rows or not _can_edit_report(rows[0].get("created_by")):
        flash("You can only delete your own reports. (Admin can delete any.)", "danger")
        return redirect(url_for("pest_reports_list"))
    db.execute_update_delete("DELETE FROM pest_report WHERE report_id=%s", (id,))
    return redirect(url_for("pest_reports_list"))


# ---------- TreatmentApplication CRUD ----------
@app.route("/applications")
def applications_list():
    rows = db.execute_query("""
        SELECT ta.*, t.name AS treatment_name, p.common_name AS pest_name, c.name AS crop_name
        FROM treatment_application ta
        LEFT JOIN treatment t ON ta.treatment_id = t.treatment_id
        LEFT JOIN pest_report pr ON ta.pest_report_id = pr.report_id
        LEFT JOIN pest p ON pr.pest_id = p.pest_id
        LEFT JOIN crop c ON ta.crop_id = c.crop_id
        ORDER BY c.name, ta.application_date DESC
    """)
    return render_template("treatment_applications/list.html", applications=rows, is_admin=session.get("admin"))


@app.route("/applications/add", methods=["GET", "POST"])
def application_add():
    if _require_admin():
        return redirect(url_for("applications_list"))
    reports = db.execute_query("SELECT report_id FROM pest_report ORDER BY report_id DESC")
    treatments = db.execute_query("SELECT treatment_id, name FROM treatment ORDER BY name")
    crops = db.execute_query("SELECT crop_id, name FROM crop ORDER BY name")
    if request.method == "POST":
        db.execute_insert(
            """INSERT INTO treatment_application (pest_report_id, treatment_id, crop_id, application_date, effectiveness_rating, cost)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING application_id""",
            (request.form.get("pest_report_id"), request.form.get("treatment_id"), request.form.get("crop_id"),
             request.form.get("application_date"), request.form.get("effectiveness_rating") or None,
             request.form.get("cost") or None)
        )
        return redirect(url_for("applications_list"))
    return render_template("treatment_applications/form.html", application=None, reports=reports, treatments=treatments, crops=crops)


@app.route("/applications/<int:id>/edit", methods=["GET", "POST"])
def application_edit(id):
    if _require_admin():
        return redirect(url_for("applications_list"))
    reports = db.execute_query("SELECT report_id FROM pest_report ORDER BY report_id DESC")
    treatments = db.execute_query("SELECT treatment_id, name FROM treatment ORDER BY name")
    crops = db.execute_query("SELECT crop_id, name FROM crop ORDER BY name")
    if request.method == "POST":
        db.execute_update_delete(
            """UPDATE treatment_application SET pest_report_id=%s, treatment_id=%s, crop_id=%s, application_date=%s, effectiveness_rating=%s, cost=%s
               WHERE application_id=%s""",
            (request.form.get("pest_report_id"), request.form.get("treatment_id"), request.form.get("crop_id"),
             request.form.get("application_date"), request.form.get("effectiveness_rating") or None,
             request.form.get("cost") or None, id)
        )
        return redirect(url_for("applications_list"))
    rows = db.execute_query("SELECT * FROM treatment_application WHERE application_id=%s", (id,))
    return render_template("treatment_applications/form.html", application=rows[0] if rows else None, reports=reports, treatments=treatments, crops=crops)


@app.route("/applications/<int:id>/delete", methods=["POST"])
def application_delete(id):
    if _require_admin():
        return redirect(url_for("applications_list"))
    db.execute_update_delete("DELETE FROM treatment_application WHERE application_id=%s", (id,))
    return redirect(url_for("applications_list"))


# ---------- Reports (analytics) ----------
@app.route("/reports/pest-by-region")
def report_pest_by_region():
    rows = db.execute_query("""
        SELECT r.name AS region_name, p.common_name AS pest_name, COUNT(pr.report_id) AS report_count
        FROM pest_report pr
        JOIN region r ON pr.region_id = r.region_id
        JOIN pest p ON pr.pest_id = p.pest_id
        GROUP BY r.region_id, r.name, p.pest_id, p.common_name
        ORDER BY r.name, report_count DESC
    """)
    return render_template("reports/pest_by_region.html", rows=rows)


@app.route("/reports/pests-by-crop")
def report_pests_by_crop():
    rows = db.execute_query("""
        SELECT
            crop_name,
            pest_name,
            SUM(report_count) AS report_count
        FROM (
            -- Counts based on pest reports
            SELECT
                c.name AS crop_name,
                p.common_name AS pest_name,
                COUNT(pr.report_id) AS report_count
            FROM pest_report pr
            JOIN crop c ON pr.crop_id = c.crop_id
            JOIN pest p ON pr.pest_id = p.pest_id
            GROUP BY c.crop_id, c.name, p.pest_id, p.common_name

            UNION ALL

            -- Counts based on treatment applications (in case there are applications for a crop
            -- without a direct pest_report row for that crop)
            SELECT
                c2.name AS crop_name,
                p2.common_name AS pest_name,
                COUNT(ta.application_id) AS report_count
            FROM treatment_application ta
            JOIN crop c2 ON ta.crop_id = c2.crop_id
            JOIN pest_report pr2 ON ta.pest_report_id = pr2.report_id
            JOIN pest p2 ON pr2.pest_id = p2.pest_id
            GROUP BY c2.crop_id, c2.name, p2.pest_id, p2.common_name
        ) AS combined
        GROUP BY crop_name, pest_name
        ORDER BY crop_name, report_count DESC
    """)
    return render_template("reports/pests_by_crop.html", rows=rows)


@app.route("/reports/treatment-effectiveness")
def report_treatment_effectiveness():
    rows = db.execute_query("""
        SELECT t.name AS treatment_name, p.common_name AS pest_name, c.name AS crop_name,
               COUNT(ta.application_id) AS app_count,
               ROUND(AVG(ta.effectiveness_rating)::numeric, 2) AS avg_effectiveness,
               ROUND(AVG(ta.cost)::numeric, 2) AS avg_cost
        FROM treatment_application ta
        JOIN treatment t ON ta.treatment_id = t.treatment_id
        JOIN pest_report pr ON ta.pest_report_id = pr.report_id
        JOIN pest p ON pr.pest_id = p.pest_id
        JOIN crop c ON ta.crop_id = c.crop_id
        GROUP BY t.treatment_id, t.name, p.pest_id, p.common_name, c.crop_id, c.name
        ORDER BY avg_effectiveness DESC NULLS LAST
    """)
    return render_template("reports/treatment_effectiveness.html", rows=rows)


@app.route("/reports/outcomes-and-effectiveness")
def report_outcomes_and_effectiveness():
    """Treatment effectiveness by pest and crop."""
    effectiveness_rows = db.execute_query("""
        SELECT t.name AS treatment_name, p.common_name AS pest_name, c.name AS crop_name,
               COUNT(ta.application_id) AS app_count,
               ROUND(AVG(ta.effectiveness_rating)::numeric, 2) AS avg_effectiveness,
               ROUND(AVG(ta.cost)::numeric, 2) AS avg_cost
        FROM treatment_application ta
        JOIN treatment t ON ta.treatment_id = t.treatment_id
        JOIN pest_report pr ON ta.pest_report_id = pr.report_id
        JOIN pest p ON pr.pest_id = p.pest_id
        JOIN crop c ON ta.crop_id = c.crop_id
        GROUP BY t.treatment_id, t.name, p.pest_id, p.common_name, c.crop_id, c.name
        ORDER BY avg_effectiveness DESC NULLS LAST
    """)
    return render_template("reports/outcomes_and_effectiveness.html", effectiveness_rows=effectiveness_rows)


# ---------- Treatment recommendation (advanced) ----------
@app.route("/recommendation", methods=["GET", "POST"])
def recommendation():
    if not session.get("farmer_email"):
        return redirect(url_for("login", next=url_for("recommendation"), reason="recommendation"))
    # One row per crop name (crop is per-region so names repeat; use distinct for dropdown)
    crops = db.execute_query(
        "SELECT DISTINCT ON (name) crop_id, name FROM crop ORDER BY name, crop_id"
    )
    results = None
    selected_pest_id = None
    selected_crop_id = None
    selected_pest_name = None
    selected_crop_name = None
    selected_area = None

    # Read selected values (works for both initial POST and subsequent submits)
    if request.method == "POST":
        mode = (request.form.get("mode") or "").strip()
        selected_crop_id = (request.form.get("crop_id") or "").strip() or None
        selected_pest_id = (request.form.get("pest_id") or "").strip() or None
        area_str = (request.form.get("area") or "").strip()
        selected_area = area_str or None
    else:
        mode = None
        selected_crop_id = request.args.get("crop_id") or None
        area_str = ""

    # Handle reset: clear selections and skip further processing
    if mode == "reset":
        selected_crop_id = None
        selected_pest_id = None
        selected_pest_name = None
        selected_crop_name = None
        selected_area = None

    # Resolve the selected crop name (used to group multiple region-specific rows,
    # so "Beans" in different regions are treated as the same crop in reports/recommendations).
    crop_name_for_filter = None
    if selected_crop_id:
        row = db.execute_query(
            "SELECT name FROM crop WHERE crop_id = %s",
            (selected_crop_id,),
        )
        if row:
            crop_name_for_filter = row[0]["name"]
            selected_crop_name = crop_name_for_filter

    # Build pest list:
    # - If a crop is selected, include pests that either:
    #   * have been reported for any crop row with this name
    #   * OR have treatment applications recorded for any crop row with this name
    #   This keeps the dropdown consistent with both Pests by Crop and Treatment Effectiveness/Applications.
    # - If no crop is selected, show all pests.
    if crop_name_for_filter:
        pests = db.execute_query(
            """
            SELECT DISTINCT pest_id, common_name
            FROM (
                SELECT p.pest_id, p.common_name
                FROM pest p
                JOIN pest_report pr ON pr.pest_id = p.pest_id
                JOIN crop c ON pr.crop_id = c.crop_id
                WHERE c.name = %s
                UNION
                SELECT p2.pest_id, p2.common_name
                FROM pest p2
                JOIN pest_report pr2 ON pr2.pest_id = p2.pest_id
                JOIN treatment_application ta ON ta.pest_report_id = pr2.report_id
                JOIN crop c2 ON ta.crop_id = c2.crop_id
                WHERE c2.name = %s
            ) AS combined
            ORDER BY common_name
            """,
            (crop_name_for_filter, crop_name_for_filter),
        )
    else:
        pests = db.execute_query("SELECT pest_id, common_name FROM pest ORDER BY common_name")

    # If mode is recommend/download and both pest and crop have been chosen, compute recommendations
    if request.method == "POST" and mode in {"recommend", "download"} and selected_pest_id and crop_name_for_filter:
        pest_id = selected_pest_id
        # Rank treatments by effectiveness, usage, and cost (normalised 0–1, combined into recommendation_score).
        # Rank treatments by effectiveness, usage, and cost (normalised 0–1, combined into recommendation_score).
        results = db.execute_query("""
            WITH base AS (
                SELECT
                    t.treatment_id,
                    t.name AS treatment_name,
                    t.cost_per_acre,
                    COUNT(ta.application_id) AS times_used,
                    AVG(ta.effectiveness_rating) AS avg_effectiveness,
                    AVG(ta.cost) AS avg_cost
                FROM treatment t
                JOIN treatment_application ta ON ta.treatment_id = t.treatment_id
                JOIN pest_report pr ON ta.pest_report_id = pr.report_id
                JOIN crop c ON ta.crop_id = c.crop_id
                WHERE pr.pest_id = %s AND c.name = %s
                GROUP BY t.treatment_id, t.name, t.cost_per_acre
            ),
            norm AS (
                SELECT
                    b.*,
                    MIN(avg_effectiveness) OVER () AS eff_min,
                    MAX(avg_effectiveness) OVER () AS eff_max,
                    MIN(avg_cost) OVER () AS cost_min,
                    MAX(avg_cost) OVER () AS cost_max,
                    MIN(times_used) OVER () AS use_min,
                    MAX(times_used) OVER () AS use_max
                FROM base b
            )
            SELECT
                treatment_name,
                cost_per_acre,
                times_used,
                ROUND(avg_effectiveness::numeric, 2) AS avg_effectiveness,
                ROUND(avg_cost::numeric, 2) AS avg_cost,
                ROUND(
                    (
                        0.6 * (
                            CASE
                                WHEN eff_max = eff_min OR avg_effectiveness IS NULL THEN 1
                                ELSE (avg_effectiveness - eff_min) / NULLIF(eff_max - eff_min, 0)
                            END
                        )
                        + 0.2 * (
                            CASE
                                WHEN use_max = use_min OR times_used IS NULL THEN 0.5
                                ELSE (times_used - use_min)::numeric / NULLIF(use_max - use_min, 0)
                            END
                        )
                        - 0.2 * (
                            CASE
                                WHEN cost_max = cost_min OR avg_cost IS NULL THEN 0
                                ELSE (avg_cost - cost_min) / NULLIF(cost_max - cost_min, 0)
                            END
                        )
                    )::numeric,
                    3
                ) AS recommendation_score
            FROM norm
            ORDER BY recommendation_score DESC NULLS LAST, avg_effectiveness DESC NULLS LAST
        """, (pest_id, crop_name_for_filter))

        # If farmer provided an area, compute estimated total cost per treatment
        if selected_area:
            try:
                area_val = float(selected_area)
                if area_val > 0:
                    for row in results:
                        cpa = row.get("cost_per_acre")
                        if cpa is not None:
                            row["estimated_total_cost"] = round(float(cpa) * area_val, 2)
                        else:
                            row["estimated_total_cost"] = None
            except ValueError:
                # Ignore invalid area input; just skip total-cost calculation
                selected_area = None

        # If user requested download, return CSV instead of HTML
        if mode == "download":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "Treatment",
                    "Avg Effectiveness",
                    "Avg Cost",
                    "Cost Per Acre",
                    "Estimated Total Cost",
                ]
            )
            for r in results:
                writer.writerow(
                    [
                        r.get("treatment_name"),
                        r.get("avg_effectiveness"),
                        r.get("avg_cost"),
                        r.get("cost_per_acre"),
                        r.get("estimated_total_cost"),
                    ]
                )
            csv_data = output.getvalue()
            output.close()
            safe_crop = (crop_name_for_filter or "all").replace(" ", "_")
            filename = f"recommendations_pest_{pest_id}_crop_{safe_crop}.csv"
            return Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
    return render_template(
        "recommendation.html",
        pests=pests,
        crops=crops,
        results=results,
        selected_pest_id=selected_pest_id,
        selected_crop_id=selected_crop_id,
        selected_pest_name=selected_pest_name,
        selected_crop_name=selected_crop_name,
        selected_area=selected_area,
    )


# ---------- Analytics (Chart.js, like Srivani) ----------
@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


@app.route("/api/charts/reports-by-region")
def api_reports_by_region():
    rows = db.execute_query("""
        SELECT r.name AS label, COUNT(pr.report_id) AS value
        FROM region r
        LEFT JOIN pest_report pr ON pr.region_id = r.region_id
        GROUP BY r.region_id, r.name ORDER BY value DESC
    """)
    return jsonify([{"label": r["label"], "value": int(r["value"])} for r in rows])


@app.route("/api/charts/top-pests")
def api_top_pests():
    rows = db.execute_query("""
        SELECT p.common_name AS label, COUNT(pr.report_id) AS value
        FROM pest p
        LEFT JOIN pest_report pr ON pr.pest_id = p.pest_id
        GROUP BY p.pest_id, p.common_name ORDER BY value DESC LIMIT 10
    """)
    return jsonify([{"label": r["label"], "value": int(r["value"])} for r in rows])


@app.route("/api/charts/treatment-usage")
def api_treatment_usage():
    rows = db.execute_query("""
        SELECT t.name AS label, COUNT(ta.application_id) AS value
        FROM treatment t
        LEFT JOIN treatment_application ta ON ta.treatment_id = t.treatment_id
        GROUP BY t.treatment_id, t.name ORDER BY value DESC LIMIT 10
    """)
    return jsonify([{"label": r["label"], "value": int(r["value"])} for r in rows])


@app.route("/api/charts/reports-by-status")
def api_reports_by_status():
    rows = db.execute_query("""
        SELECT status AS label, COUNT(*) AS value FROM pest_report GROUP BY status
    """)
    return jsonify([{"label": r["label"] or "unknown", "value": int(r["value"])} for r in rows])


if __name__ == "__main__":
    app.run(debug=True, port=5001)
