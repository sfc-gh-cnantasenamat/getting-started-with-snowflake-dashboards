-- Revenue Pulse bootstrap. Paste and run this in a Snowsight SQL file (role ACCOUNTADMIN).
-- It creates the dedicated database and a Git repository object over the public companion repo,
-- so every later script runs straight from Snowflake with EXECUTE IMMEDIATE FROM.
USE ROLE ACCOUNTADMIN;

CREATE DATABASE IF NOT EXISTS REVENUE_PULSE_DB
  COMMENT = 'Revenue Pulse developer guide (synthetic data). Safe to drop after the guide.';

CREATE SCHEMA IF NOT EXISTS REVENUE_PULSE_DB.DASHBOARD_DEMO
  COMMENT = 'Revenue Pulse Snowflake Dashboards demo (synthetic data)';

CREATE API INTEGRATION IF NOT EXISTS REVENUE_PULSE_GIT_API
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/sfc-gh-cnantasenamat/')
  ENABLED = TRUE
  COMMENT = 'Read access to the public Revenue Pulse companion repo';

CREATE GIT REPOSITORY IF NOT EXISTS REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO
  API_INTEGRATION = REVENUE_PULSE_GIT_API
  ORIGIN = 'https://github.com/sfc-gh-cnantasenamat/getting-started-with-snowflake-dashboards.git';

ALTER GIT REPOSITORY REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO FETCH;

LS @REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO/branches/main/sql/;
