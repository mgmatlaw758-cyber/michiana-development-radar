from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .feed import get_project, query_project_feed
from .sync import OFFICIAL_HOSTS

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
    .project-title { color: var(--text); text-decoration: none; }
    .project-title:hover { color: var(--accent); }
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
      grid-template-columns: minmax(240px, 2fr) repeat(6, minmax(120px, 1fr));
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
    #high-value {
      border-color: #65481a;
      background: var(--accent-soft);
      color: #ffd07a;
    }

    #high-value:hover {
      border-color: var(--accent);
    }

    #high-value.active {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    #newly-added {
      border-color: #355c72;
      background: #132d3b;
      color: #9edcff;
    }

    #newly-added:hover {
      border-color: #8fc8ff;
    }

    #newly-added.active {
      outline: 2px solid #8fc8ff;
      outline-offset: 2px;
    }
    .result-line {
      min-height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      color: var(--muted);
      font-size: .9rem;
    }
    .opportunity-snapshot {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .opportunity-snapshot div {
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(18, 26, 34, .94);
      padding: 16px 18px;
    }

    .opportunity-snapshot span {
      display: block;
      color: var(--muted);
      font-size: .78rem;
      font-weight: 700;
      margin-bottom: 5px;
    }

    .opportunity-snapshot strong {
      font-size: 1.5rem;
    }
    .top-section {
      margin-bottom: 24px;
    }

    .top-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }

    .top-heading span {
      color: var(--accent);
      font-size: .72rem;
      font-weight: 800;
      letter-spacing: .1em;
      text-transform: uppercase;
    }

    .top-heading h2 {
      margin: 4px 0 0;
    }

    .top-heading small {
      color: var(--muted);
    }

    .top-opportunities {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }

    .top-card {
      display: block;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(18, 26, 34, .94);
      padding: 15px;
      color: var(--text);
      text-decoration: none;
    }

    .top-card:hover {
      border-color: var(--accent);
    }

    .top-card strong {
      display: block;
      color: var(--green);
      font-size: 1.25rem;
      margin-bottom: 8px;
    }

    .top-card .top-type {
      display: block;
      font-weight: 750;
      margin-bottom: 7px;
    }

    .top-card .top-jurisdiction {
      color: var(--muted);
      font-size: .8rem;
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
    "<span><strong>Jurisdiction:</strong> " +
      escapeHtml(project.jurisdiction || "Not listed") + "</span>" +
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
      .opportunity-snapshot {
        grid-template-columns: 1fr;
      }
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
    <div class="eyebrow">Michiana development intelligence</div>
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
        Jurisdiction
        <select id="jurisdiction">
          <option value="">All jurisdictions</option>
        </select>
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
      <button id="newly-added" type="button">✨ Newly Added</button>
      <button id="high-value" type="button">★ High Value Opportunities</button>
      <button id="reset" type="button">Clear filters</button>
    </section>

    <div class="result-line">
      <span id="result-status" role="status" aria-live="polite">Loading projects...</span>
      <span id="latest-date"></span>
    </div>
    <section class="opportunity-snapshot" aria-label="Opportunity snapshot">
    <div>
      <span>Matching projects</span>
      <strong id="snapshot-projects">...</strong>
    </div>
    <div>
      <span>Matching listed value</span>
      <strong id="snapshot-value">...</strong>
    </div>
    </section>
    <section class="top-section" aria-label="Top opportunities">
  <div class="top-heading">
    <div>
      <span>Priority view</span>
      <h2>Top Opportunities</h2>
    </div>
    <small>Highest listed permit values matching your filters</small>
  </div>

  <div id="top-opportunities" class="top-opportunities"></div>
</section>
    <section id="feed" class="feed" aria-label="Project results"></section>
  </main>

  <script>
    (function () {
      "use strict";

      var controls = {
        search: document.getElementById("search"),
        jurisdiction: document.getElementById("jurisdiction"),
        city: document.getElementById("city"),
        projectType: document.getElementById("project-type"),
        minValue: document.getElementById("min-value"),
        sort: document.getElementById("sort")
      };
      var feed = document.getElementById("feed");
      var status = document.getElementById("result-status");
      var requestNumber = 0;
      var debounceTimer;
      var addedWithinDays = "";

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

      function topOpportunityCard(project) {
        return '<a class="top-card" href="/projects/' +
          encodeURIComponent(project.project_id) + '">' +
            '<strong>' +
              escapeHtml(money(project.listed_permit_value_total)) +
            '</strong>' +
            '<span class="top-type">' +
              escapeHtml(project.project_type || "Commercial project") +
            '</span>' +
            '<span class="top-jurisdiction">' +
              escapeHtml(project.jurisdiction || "Jurisdiction not listed") +
            '</span>' +
          '</a>';
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
              '<h2><a class="project-title" href="/projects/' +
              encodeURIComponent(project.project_id) + '">' +
              escapeHtml(project.project_type || "Commercial project") +
              "</a></h2>" +
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
        document.getElementById("snapshot-projects").textContent =
          data.filtered_summary.project_count.toLocaleString();
        document.getElementById("snapshot-value").textContent =
          money(data.filtered_summary.listed_value_total);
        var topOpportunities = document.getElementById("top-opportunities");

        if (data.top_opportunities.length) {
          topOpportunities.innerHTML =
            data.top_opportunities.map(topOpportunityCard).join("");
        } else {
          topOpportunities.innerHTML =
            '<div class="empty">No matching opportunities.</div>';
        }
        document.getElementById("latest-date").textContent =
          data.summary.latest_issued_date
            ? "Updated through " + dateLabel(data.summary.latest_issued_date)
            : "";
        status.textContent = data.result_count.toLocaleString() +
          (data.result_count === 1 ? " project found" : " projects found");

        fillSelect(controls.city, data.facets.cities, "All cities");
        fillSelect(
          controls.jurisdiction,
          data.facets.jurisdictions,
          "All jurisdictions"
        );
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
        if (controls.jurisdiction.value) {
          params.set("jurisdiction", controls.jurisdiction.value);
        }
        if (addedWithinDays) {
          params.set("added_within_days", addedWithinDays);
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
      controls.jurisdiction.addEventListener("change", loadProjects);
      controls.projectType.addEventListener("change", loadProjects);
      document.getElementById("high-value").addEventListener("click", function () {
        controls.minValue.value = "250000";
        controls.sort.value = "value_desc";
        this.classList.add("active");
        loadProjects();
      });
      controls.sort.addEventListener("change", loadProjects);
      document.getElementById("newly-added").addEventListener("click", function () {
        if (addedWithinDays === "7") {
          addedWithinDays = "";
          this.classList.remove("active");
        } else {
          addedWithinDays = "7";
          this.classList.add("active");
        }

        loadProjects();
      });
      document.getElementById("high-value").addEventListener("click", function () {
        controls.minValue.value = "250000";
        controls.sort.value = "value_desc";
        loadProjects();
      });
      document.getElementById("reset").addEventListener("click", function () {
        controls.search.value = "";
        controls.city.value = "";
        controls.projectType.value = "";
        controls.minValue.value = "";
        controls.sort.value = "newest";
        addedWithinDays = "";
        document.getElementById("newly-added").classList.remove("active");
        document.getElementById("high-value").classList.remove("active");
        loadProjects();
      });

      loadProjects();
    }());
  </script>
</body>
</html>
"""

PROJECT_PAGE_SHELL = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__ | Michiana Development Radar</title>
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
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    a { color: #8fc8ff; }
    button { font: inherit; }
    .shell { width: min(1000px, calc(100% - 32px)); margin: 0 auto; }
    nav {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
      padding: 24px 0;
    }
    .brand {
      color: var(--accent);
      font-size: .8rem;
      font-weight: 850;
      letter-spacing: .09em;
      text-decoration: none;
      text-transform: uppercase;
    }
    .back { color: var(--muted); text-decoration: none; }
    .hero, .permit, .notice {
      border: 1px solid var(--border);
      background: rgba(18, 26, 34, .95);
      box-shadow: var(--shadow);
    }
    .hero { border-radius: 18px; padding: clamp(22px, 4vw, 38px); }
    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
    }
    .badge {
      display: inline-flex;
      border: 1px solid #65481a;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #ffd07a;
      padding: 4px 9px;
      font-size: .75rem;
      font-weight: 800;
    }
    h1 {
      margin: 9px 0 10px;
      font-size: clamp(2rem, 5vw, 3.5rem);
      letter-spacing: -.045em;
      line-height: 1;
    }
    .value {
      color: var(--green);
      font-size: clamp(1.7rem, 4vw, 2.6rem);
      font-weight: 900;
      white-space: nowrap;
    }
    .description {
      color: #d1dce2;
      font-size: 1.08rem;
      line-height: 1.55;
      max-width: 780px;
    }
    .facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 24px;
    }
    .fact {
      border: 1px solid #263541;
      border-radius: 11px;
      background: #0d141a;
      padding: 13px 14px;
    }
    .fact span {
      display: block;
      color: var(--muted);
      font-size: .75rem;
      font-weight: 750;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .fact strong { overflow-wrap: anywhere; }
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 22px;
    }
    button {
      width: auto;
      min-height: 40px;
      border: 1px solid #65481a;
      border-radius: 9px;
      background: var(--accent-soft);
      color: #ffd07a;
      cursor: pointer;
      padding: 8px 13px;
      font-weight: 800;
    }
    button:focus, a:focus { outline: 2px solid var(--accent); outline-offset: 2px; }
    .record-id { color: var(--muted); font-size: .78rem; overflow-wrap: anywhere; }
    h2 { margin: 34px 0 14px; }
    .permit-list { display: grid; gap: 12px; }
    .permit { border-radius: 14px; padding: 19px; }
    .permit-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
    }
    .permit h3 { margin: 0 0 4px; }
    .permit-value { color: var(--green); font-weight: 850; white-space: nowrap; }
    .permit-meta {
      color: var(--muted);
      display: flex;
      flex-wrap: wrap;
      gap: 7px 16px;
      font-size: .86rem;
      margin-top: 12px;
    }
    .permit-description { color: #d1dce2; line-height: 1.5; }
    .source { display: inline-block; margin-top: 13px; font-weight: 750; }
    .notice {
      border-radius: 12px;
      color: var(--muted);
      font-size: .82rem;
      line-height: 1.5;
      margin: 24px 0 60px;
      padding: 14px 16px;
    }
    @media (max-width: 650px) {
      .shell { width: min(100% - 20px, 1000px); }
      nav { align-items: flex-start; }
      .hero-top, .permit-top { display: block; }
      .value, .permit-value { margin-top: 12px; }
      .facts { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <nav class="shell">
    <a class="brand" href="/">Development Radar</a>
    <a class="back" href="/">Back to project feed</a>
  </nav>
  <main class="shell">__CONTENT__</main>
  <script>
    (function () {
      var button = document.getElementById("copy-link");
      if (!button) return;
      button.addEventListener("click", function () {
        if (!navigator.clipboard) {
          button.textContent = "Copy the browser URL";
          return;
        }
        navigator.clipboard.writeText(window.location.href).then(function () {
          button.textContent = "Link copied";
          window.setTimeout(function () {
            button.textContent = "Copy project link";
          }, 1800);
        }).catch(function () {
          button.textContent = "Copy the browser URL";
        });
      });
    }());
  </script>
</body>
</html>
"""


def _display_money(value: object) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except InvalidOperation:
        return "Value not listed"
    return "$" + f"{amount:,.0f}"


def _source_page_url(permit: dict[str, Any]) -> str | None:
    raw_url = str(permit.get("source_url") or "")
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in OFFICIAL_HOSTS
    ):
        return None
    pages = permit.get("source_pages") or []
    fragment = f"page={pages[0]}" if pages else ""
    return parsed._replace(fragment=fragment).geturl()


def render_project_page(project: dict[str, Any]) -> str:
    def text(value: object, fallback: str = "Not listed") -> str:
        cleaned = str(value or "").strip()
        return escape(cleaned or fallback)

    location = ", ".join(
        str(value)
        for value in (
            project.get("site_address"),
            project.get("city"),
            project.get("state"),
            project.get("postal_code"),
        )
        if value
    )
    contractors = ", ".join(project.get("contractors") or [])
    businesses = ", ".join(project.get("owner_businesses") or [])
    status = (
        "Probable companion permits"
        if project["permit_count"] > 1
        else "Single permit"
    )

    permit_cards: list[str] = []
    for permit in project["permits"]:
        source_url = _source_page_url(permit)
        source_link = ""
        if source_url is not None:
            pages = permit.get("source_pages") or []
            page_label = f", page {pages[0]}" if pages else ""
            source_link = (
                '<a class="source" href="'
                + escape(source_url, quote=True)
                + '" target="_blank" rel="noopener noreferrer">'
                + "Open county source PDF"
                + escape(page_label)
                + "</a>"
            )

        permit_location = ", ".join(
            str(value)
            for value in (
                permit.get("site_address"),
                permit.get("city"),
                permit.get("state"),
                permit.get("postal_code"),
            )
            if value
        )
        parcels = ", ".join(permit.get("parcel_numbers") or [])
        zoning = ", ".join(permit.get("zoning") or [])
        permit_cards.append(
            '<article class="permit">'
            '<div class="permit-top"><div><h3>'
            + text(permit.get("permit_number"))
            + "</h3><span>"
            + text(permit.get("project_type"))
            + "</span></div><div class=\"permit-value\">"
            + escape(_display_money(permit.get("estimated_cost")))
            + "</div></div>"
            '<p class="permit-description">'
            + text(permit.get("description"), "No description listed.")
            + "</p>"
            '<div class="permit-meta"><span>Issued: '
            + text(permit.get("issued_date"))
            + "</span><span>Location: "
            + text(permit_location)
            + "</span><span>Contractor: "
            + text(permit.get("general_contractor"))
            + "</span><span>Parcel: "
            + text(parcels)
            + "</span><span>Zoning: "
            + text(zoning)
            + "</span></div>"
            + source_link
            + "</article>"
        )

    facts = [
        ("Location", location),
        ("Latest permit", project.get("latest_issued_date")),
        ("Contractor", contractors),
        ("Business", businesses),
    ]
    facts_html = "".join(
        '<div class="fact"><span>'
        + escape(label)
        + "</span><strong>"
        + text(value)
        + "</strong></div>"
        for label, value in facts
    )
    content = (
        '<section class="hero"><div class="hero-top"><div><span class="badge">'
        + escape(status)
        + "</span><h1>"
        + text(project.get("project_type"), "Commercial project")
        + '</h1></div><div class="value">'
        + escape(_display_money(project.get("listed_permit_value_total")))
        + "</div></div>"
        '<p class="description">'
        + text(project.get("description"), "No project description listed.")
        + '</p><div class="facts">'
        + facts_html
        + '</div><div class="actions"><button id="copy-link" type="button">'
        + 'Copy project link</button><span class="record-id">'
        + text(project.get("project_id"))
        + "</span></div></section>"
        "<h2>Permits in this project</h2>"
        '<section class="permit-list">'
        + "".join(permit_cards)
        + "</section>"
        '<aside class="notice">Permit values are amounts listed in the public '
        "county reports and may not equal final construction cost. Companion "
        "permits are grouped from shared project signals and should be checked "
        "against the linked source documents.</aside>"
    )
    return (
        PROJECT_PAGE_SHELL
        .replace("__PAGE_TITLE__", text(project.get("project_type")))
        .replace("__CONTENT__", content)
    )



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
        if request.path.startswith("/projects/"):
            project_id = request.path.removeprefix("/projects/").rstrip("/")
            try:
                project = get_project(self.server.database_path, project_id)
            except (ValueError, KeyError):
                self._send(
                    404,
                    b"Project not found",
                    "text/plain; charset=utf-8",
                )
                return
            self._send(
                200,
                render_project_page(project).encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if request.path == "/api/health":
            self._send_json(200, {"status": "ok"})
            return
        if request.path.startswith("/api/projects/"):
            project_id = request.path.removeprefix(
                "/api/projects/"
            ).rstrip("/")
            try:
                project = get_project(self.server.database_path, project_id)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except KeyError as exc:
                self._send_json(404, {"error": str(exc.args[0])})
                return
            self._send_json(200, {"project": project})
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
                jurisdiction=first("jurisdiction"),
                added_within_days=(
                    int(first("added_within_days"))
                    if first("added_within_days")
                    else None
                ),
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
