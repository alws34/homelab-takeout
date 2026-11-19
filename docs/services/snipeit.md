# Snipe-IT

Worker type: `snipeit` · Method: REST API

## What's Backed Up

Hardware, licenses, accessories, consumables, components, users, locations,
manufacturers, categories, companies, departments, status labels, suppliers,
and custom fields — each as a paginated JSON export, bundled into a `tar.gz`.

An endpoint this token may not read (403) or this version doesn't have (404) is
written as `[]` and listed in `skipped.json`. Any other error (a server error, a
timeout) fails the run, so an incomplete backup is never uploaded or counted towards
retention. If every endpoint answers 403/404, the URL is probably wrong and the run
fails too.

## Setup

1. Open Snipe-IT → **Settings → API → Create Token**.
2. Set the variables below in `.env`.
3. Enable the `snipeit` service in `config/services.json`.

## `.env` Variables

| Variable          | Required | Notes                                    |
|--------------------|----------|---------------------------------------------|
| `SNIPEIT_URL`      | Yes      | Base URL, e.g. `http://snipeit:80`         |
| `SNIPEIT_API_KEY`  | Yes      | Token from Settings → API → Create Token   |

## Restoring

This export is a **readable reference**, not a file the app can import directly. To rebuild, set up a fresh instance and re-create the records from the JSON (by hand, or with a short script against the same API endpoints the worker read from).
