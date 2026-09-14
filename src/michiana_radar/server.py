from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .feed import query_project_feed

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Michiana Development Radar</title>
  <style>
    :root {
      color-scheme: dark;
      --background: #0b1015;
      --panel: #121a22;
      --panel-light: #18232d;
      --border: #2b3945;
      --text: #edf4f7;
      --muted: #98a9b5;
      --accent: #f5a623;
      --accent-soft: #3e2c0f;
      --green: #6ed7a5;
      --shadow: 0 18px 48px rgba(0, 0, 0, .24);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 15% -10%, #203649 0, transparent 35rem),
        var(--background);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }

    button, input, select { font: inherit; }
    a { color: #8fc8ff; }
    .shell { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
    header { padding: 42px 0 22px; }
    .eyebrow {
      color: var(--accent);
      font-size: .75rem;
      font-weight: 800;
      letter-spacing: .13em;
      text-transform: uppercase;
    }
    h1 {
      margin: 8px 0;
      font-size: clamp(2rem, 5vw, 3.8rem);
      line-height: .98;
      letter-spacing: -.05em;
    }
    .subtitle { color: var(--muted); max-width: 720px; margin: 0; }

    .summary {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin: 22px 0;
    }
    .stat, .controls, .card {
      border: 1px solid var(--border);
      background: rgba(18, 26, 34, .94);
      box-shadow: var(--shadow);
    }
    .stat { border-radius: 14px; padding: 16px 18px; }
    .stat strong { display: block; font-size: 1.5rem; }
    .stat span { color: var(--muted); font-size: .82rem; }

    .controls {
      display: grid;
      grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(130px, 1fr));
      gap: 12px;
      padding: 16px;
      border-radius: 16px;
      position: sticky;
      top: 10px;
      z-index: 5;
      backdrop-filter: blur(16px);
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: .75rem;
      font-weight: 700;
      letter-spacing: .03em;
    }
    input, select, button {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--border);
      border-radius: 9px;
      background: #0d141a;
      color: var(--text);
      padding: 9px 11px;
    }
    input:focus, select:focus, button:focus {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    button {
      cursor: pointer;
      background: var(--panel-light);
      font-weight: 750;
      align-self: end;
    }
    button:hover { border-color: var(--accent); }

    .result-line {
      min-height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      color: var(--muted);
      font-size: .9rem;
    }
    .feed { display: grid; gap: 14px; padding-bottom: 60px; }
    .card { border-radius: 16px; overflow: hidden; }
    .card-main { padding: 20px; }
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 20px;
    }
    .value {
      color: var(--green);
      font-size: 1.45rem;
      font-weight: 850;
      white-space: nowrap;
    }
    h2 { margin: 5px 0 8px; font-size: 1.2rem; }
    .description { color: #d1dce2; margin: 0 0 14px; line-height: 1.5; }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
      color: var(--muted);
      font-size: .86rem;
    }
    .meta strong { color: var(--text); font-weight: 700; }
    .badge {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border: 1px solid #65481a;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #ffd07a;
      padding: 3px 8px;
      font-size: .72rem;
      font-weight: 750;
    }
    details { border-top: 1px solid var(--border); }
    summary {
      cursor: pointer;
      padding: 13px 20px;
      color: var(--muted);
      font-weight: 700;
    }
    .permit-list {
      list-style: none;
      margin: 0;
      padding: 0 20px 18px;
      display: grid;
      gap: 9px;
    }
    .permit {
      background: #0d141a;
      border: 1px solid #24313b;
      border-radius: 10px;
      padding: 11px 12px;
      font-size: .84rem;
      color: var(--muted);
    }
    .permit strong { color: var(--text); }
    .empty, .error {
      border: 1px dashed var(--border);
      border-radius: 16px;
      padding: 40px 20px;
      text-align: center;
      color: var(--muted);
    }
    .error { color: #ff9d9d; border-color: #7b3d3d; }

    @media (max-width: 900px) {
      .controls { grid-template-columns: repeat(2, 1fr); position: static; }
      .search-field { grid-column: 1 / -1; }
    }
    @media (max-width: 600px) {
      .shell { width: min(100% - 20px, 1180px); }
      header { padding-top: 28px; }
      .summary { grid-template-columns: 1fr; }
      .controls { grid-template-columns: 1fr; }
      .search-field { grid-column: auto; }
      .card-top { display: block; }
      .value { margin-bottom: 10px; }
    }
  </style>
</head>
<body>
  <header class="shell">
    <div class="eyebrow">Elkhart County intelligence</div>
    <h1>Development Radar</h1>
    <p class="subtitle">
      Search current commercial construction activity without digging through
      hundreds of county PDF pages.
    </p>
    <section class="summary" aria-label="Database summary">
      <div class="stat"><strong id="project-count">...</strong><span>probable projects</span></div>
      <div class="stat"><strong id="permit-count">...</strong><span>commercial permits</span></div>
      <div class="stat"><strong id="total-value">...</strong><span>listed permit value</span></div>
    </section>
  </header>

  <main class="shell">
    <section class="controls" aria-label="Project filters">
      <label class="search-field">
        Search
        <input id="search" type="search" placeholder="Contractor, address or permit number">
      </label>
      <label>
        City
        <select id="city"><option value="">All cities</option></select>
      </label>
      <label>
        Project type
        <select id="project-type"><option value="">All project types</option></select>
      </label>
      <label>
        Minimum value
        <input id="min-value" type="number" min="0" step="1000" placeholder="$0">
      </label>
      <label>
        Sort
        <select id="sort">
          <option value="newest">Newest first</option>
          <option value="value_desc">Highest value</option>
          <option value="value_asc">Lowest value</option>
          <option value="oldest">Oldest first</option>
        </select>
      </label>
      <button id="reset" type="button">Clear filters</button>
    </section>

    <div class="result-line">
      <span id="result-status" role="status" aria-live="polite">Loading projects...</span>
      <span id="latest-date"></span>
    </div>
    <section id="feed" class="feed" aria-label="Project results"></section>
  </main>

  <script>
    (function () {
      "use strict";

      var controls = {
        search: document.getElementById("search"),
        city: document.getElementById("city"),
        projectType: document.getElementById("project-type"),
        minValue: document.getElementById("min-value"),
        sort: document.getElementById("sort")
      };
      var feed = document.getElementById("feed");
      var status = document.getElementById("result-status");
      var requestNumber = 0;
      var debounceTimer;

      function escapeHtml(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
          return {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
          }[character];
        });
      }

      function money(value) {
        var number = Number(value || 0);
        return new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0
        }).format(number);
      }

      function dateLabel(value) {
        if (!value) return "Date not listed";
        return new Intl.DateTimeFormat("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric"
        }).format(new Date(value + "T00:00:00"));
      }

      function fillSelect(select, values, allLabel) {
        var selected = select.value;
        select.innerHTML = '<option value="">' + escapeHtml(allLabel) + "</option>";
        values.forEach(function (value) {
          var option = document.createElement("option");
          option.value = value;
          option.textContent = value;
          select.appendChild(option);
        });
        select.value = selected;
      }

      function safeSourceLink(permit) {
        try {
          var parsed = new URL(permit.source_url);
          if (parsed.protocol !== "https:") return "";
          return '<a href="' + escapeHtml(parsed.href) +
            '" target="_blank" rel="noopener noreferrer">source PDF</a>';
        } catch (error) {
          return "";
        }
      }

      function projectCard(project) {
        var location = [
          project.site_address,
          project.city,
          project.state,
          project.postal_code
        ].filter(Boolean).join(", ");
        var contractors = project.contractors.length
          ? project.contractors.join(", ")
          : "Not listed";
        var businesses = project.owner_businesses.length
          ? '<span><strong>Business:</strong> ' +
            escapeHtml(project.owner_businesses.join(", ")) + "</span>"
          : "";
        var companion = project.permit_count > 1
          ? '<span class="badge">Probable companion permits</span>'
          : '<span class="badge">Single permit</span>';
        var permits = project.permits.map(function (permit) {
          var source = safeSourceLink(permit);
          return '<li class="permit"><strong>' +
            escapeHtml(permit.permit_number) + "</strong> · " +
            escapeHtml(permit.project_type) + " · " +
            escapeHtml(money(permit.estimated_cost)) + " · " +
            escapeHtml(dateLabel(permit.issued_date)) +
            (source ? " · " + source : "") + "</li>";
        }).join("");

        return '<article class="card">' +
          '<div class="card-main">' +
            '<div class="card-top"><div>' + companion +
              "<h2>" + escapeHtml(project.project_type || "Commercial project") + "</h2>" +
            '</div><div class="value">' +
              escapeHtml(money(project.listed_permit_value_total)) +
            "</div></div>" +
            '<p class="description">' +
              escapeHtml(project.description || "No project description listed.") +
            "</p>" +
            '<div class="meta">' +
              "<span><strong>Location:</strong> " +
                escapeHtml(location || "Not listed") + "</span>" +
              "<span><strong>Issued:</strong> " +
                escapeHtml(dateLabel(project.latest_issued_date)) + "</span>" +
              "<span><strong>Contractor:</strong> " +
                escapeHtml(contractors) + "</span>" +
              businesses +
            "</div>" +
          "</div>" +
          "<details><summary>View " + project.permit_count +
            (project.permit_count === 1 ? " permit" : " permits") +
          '</summary><ul class="permit-list">' + permits + "</ul></details>" +
        "</article>";
      }

      function render(data) {
        document.getElementById("project-count").textContent =
          data.summary.project_count.toLocaleString();
        document.getElementById("permit-count").textContent =
          data.summary.permit_count.toLocaleString();
        document.getElementById("total-value").textContent =
          money(data.summary.listed_value_total);
        document.getElementById("latest-date").textContent =
          data.summary.latest_issued_date
            ? "Updated through " + dateLabel(data.summary.latest_issued_date)
            : "";
        status.textContent = data.result_count.toLocaleString() +
          (data.result_count === 1 ? " project found" : " projects found");

        fillSelect(controls.city, data.facets.cities, "All cities");
        fillSelect(
          controls.projectType,
          data.facets.project_types,
          "All project types"
        );

        if (!data.projects.length) {
          feed.innerHTML =
            '<div class="empty">No projects match those filters.</div>';
          return;
        }
        feed.innerHTML = data.projects.map(projectCard).join("");
      }

      function loadProjects() {
        var thisRequest = ++requestNumber;
        var params = new URLSearchParams();
        if (controls.search.value.trim()) {
          params.set("q", controls.search.value.trim());
        }
        if (controls.city.value) params.set("city", controls.city.value);
        if (controls.projectType.value) {
          params.set("project_type", controls.projectType.value);
        }
        if (controls.minValue.value) {
          params.set("min_value", controls.minValue.value);
        }
        params.set("sort", controls.sort.value);
        params.set("limit", "200");

        status.textContent = "Loading projects...";
        fetch("/api/projects?" + params.toString(), {
          headers: { "Accept": "application/json" }
        })
          .then(function (response) {
            return response.json().then(function (body) {
              if (!response.ok) throw new Error(body.error || "Request failed");
              return body;
            });
          })
          .then(function (data) {
            if (thisRequest === requestNumber) render(data);
          })
          .catch(function (error) {
            if (thisRequest !== requestNumber) return;
            status.textContent = "Could not load projects";
            feed.innerHTML = '<div class="error">' +
              escapeHtml(error.message) + "</div>";
          });
      }

      function queueLoad() {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(loadProjects, 220);
      }

      controls.search.addEventListener("input", queueLoad);
      controls.minValue.addEventListener("input", queueLoad);
      controls.city.addEventListener("change", loadProjects);
      controls.projectType.addEventListener("change", loadProjects);
      controls.sort.addEventListener("change", loadProjects);
      document.getElementById("reset").addEventListener("click", function () {
        controls.search.value = "";
        controls.city.value = "";
        controls.projectType.value = "";
        controls.minValue.value = "";
        controls.sort.value = "newest";
        loadProjects();
      });

      loadProjects();
    }());
  </script>
</body>
</html>
"""


class RadarHTTPServer(ThreadingHTTPServer):
    database_path: Path

    def __init__(
        self,
        server_address: tuple[str, int],
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)
        super().__init__(server_address, RadarRequestHandler)


class RadarRequestHandler(BaseHTTPRequestHandler):
    server: RadarHTTPServer

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; "
                "img-src 'self' data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/":
            self._send(
                200,
                DASHBOARD_HTML.encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if request.path == "/api/health":
            self._send_json(200, {"status": "ok"})
            return
        if request.path != "/api/projects":
            self._send_json(404, {"error": "Not found"})
            return

        parameters = parse_qs(request.query, keep_blank_values=True)

        def first(name: str, default: str = "") -> str:
            return parameters.get(name, [default])[0]

        try:
            payload = query_project_feed(
                self.server.database_path,
                search=first("q"),
                city=first("city"),
                project_type=first("project_type"),
                contractor=first("contractor"),
                min_value=first("min_value") or None,
                max_value=first("max_value") or None,
                sort=first("sort", "newest"),
                limit=int(first("limit", "50")),
                offset=int(first("offset", "0")),
            )
        except (ValueError, FileNotFoundError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        self._send_json(200, payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_dashboard_server(
    database_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> RadarHTTPServer:
    database_path = Path(database_path)
    if not database_path.is_file():
        raise FileNotFoundError(f"Radar database not found: {database_path}")
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    return RadarHTTPServer((host, port), database_path)


def serve_dashboard(
    database_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    server = create_dashboard_server(
        database_path,
        host=host,
        port=port,
    )
    bound_host, bound_port = server.server_address[:2]
    display_host = "localhost" if bound_host in {"127.0.0.1", "::1"} else bound_host
    print(f"Development Radar is running at http://{display_host}:{bound_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Development Radar.")
    finally:
        server.server_close()
