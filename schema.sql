-- Agriculture Pest Management System
-- PostgreSQL schema (6 tables from ER diagram)

DROP TABLE IF EXISTS treatment_application;
DROP TABLE IF EXISTS pest_report;
DROP TABLE IF EXISTS treatment;
DROP TABLE IF EXISTS pest;
DROP TABLE IF EXISTS crop;
DROP TABLE IF EXISTS region;
DROP TABLE IF EXISTS farmer_signup;

CREATE TABLE farmer_signup (
    farmer_id     SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_farmer_signup_email_lower ON farmer_signup (LOWER(email));

CREATE TABLE region (
    region_id   SERIAL PRIMARY KEY,
    state_code  VARCHAR(10) NOT NULL,
    name        VARCHAR(100) NOT NULL
);

CREATE TABLE crop (
    crop_id         SERIAL PRIMARY KEY,
    region_id       INTEGER NOT NULL REFERENCES region(region_id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(150)
);

CREATE TABLE pest (
    pest_id         SERIAL PRIMARY KEY,
    common_name     VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(150),
    pest_type       VARCHAR(50),
    description     TEXT
);

CREATE TABLE treatment (
    treatment_id   SERIAL PRIMARY KEY,
    name           VARCHAR(150) NOT NULL,
    type           VARCHAR(50),
    cost_per_acre  DECIMAL(10, 2)
);

CREATE TABLE pest_report (
    report_id   SERIAL PRIMARY KEY,
    pest_id     INTEGER NOT NULL REFERENCES pest(pest_id) ON DELETE CASCADE,
    crop_id     INTEGER NOT NULL REFERENCES crop(crop_id) ON DELETE CASCADE,
    region_id   INTEGER NOT NULL REFERENCES region(region_id) ON DELETE CASCADE,
    status      VARCHAR(50) DEFAULT 'pending',
    created_by  VARCHAR(255)
);

CREATE TABLE treatment_application (
    application_id       SERIAL PRIMARY KEY,
    pest_report_id       INTEGER NOT NULL REFERENCES pest_report(report_id) ON DELETE CASCADE,
    treatment_id        INTEGER NOT NULL REFERENCES treatment(treatment_id) ON DELETE CASCADE,
    crop_id             INTEGER NOT NULL REFERENCES crop(crop_id) ON DELETE CASCADE,
    application_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    effectiveness_rating INTEGER,
    cost                DECIMAL(10, 2)
);

CREATE INDEX idx_pest_report_region ON pest_report(region_id);
CREATE INDEX idx_pest_report_crop ON pest_report(crop_id);
CREATE INDEX idx_pest_report_pest ON pest_report(pest_id);
CREATE INDEX idx_treatment_app_report ON treatment_application(pest_report_id);
CREATE INDEX idx_treatment_app_treatment ON treatment_application(treatment_id);
