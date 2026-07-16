(function () {
  "use strict";

  const appState = {
    csrfToken: "",
    currentView: "dashboard",
    leads: [],
    stats: null,
    sources: [],
    notesOriginal: "",
    activeModalClose: null,
  };

  const mainBody = document.getElementById("mainBody");
  const pageTitle = document.getElementById("pageTitle");
  const sidebar = document.getElementById("sidebar");
  const sidebarOverlay = document.getElementById("sidebarOverlay");
  const menuButton = document.getElementById("menuBtn");
  const toastContainer = document.getElementById("toastContainer");
  const leadCountBadge = document.getElementById("leadCountBadge");
  let navigationGeneration = 0;
  let navigationController = null;
  let sidebarReturnFocus = null;

  const viewTitles = {
    dashboard: "Dashboard",
    leads: "Live Leads",
    sources: "Public Sources",
    agent: "Agent Tools",
    about: "About",
  };

  function createElement(tagName, options) {
    const config = options || {};
    const element = document.createElement(tagName);
    if (config.className) {
      element.className = config.className;
    }
    if (config.text !== undefined) {
      element.textContent = String(config.text);
    }
    if (config.attributes) {
      Object.entries(config.attributes).forEach(function (entry) {
        element.setAttribute(entry[0], String(entry[1]));
      });
    }
    (config.children || []).forEach(function (child) {
      if (child) {
        element.appendChild(child);
      }
    });
    return element;
  }

  function clearElement(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function createButton(label, className, handler) {
    const button = createElement("button", {
      className: className,
      text: label,
      attributes: { type: "button" },
    });
    button.addEventListener("click", handler);
    return button;
  }

  function safeHttpUrl(value) {
    try {
      const parsed = new URL(String(value));
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return null;
      }
      return parsed.href;
    } catch (_error) {
      return null;
    }
  }

  function externalLink(value, label) {
    const safeUrl = safeHttpUrl(value);
    if (!safeUrl) {
      return createElement("span", { className: "invalid-link", text: "Unavailable link" });
    }
    const link = createElement("a", {
      className: "safe-link",
      text: label || safeUrl,
      attributes: { target: "_blank", rel: "noopener noreferrer" },
    });
    link.href = safeUrl;
    return link;
  }

  async function apiFetch(path, options) {
    const config = options || {};
    const method = String(config.method || "GET").toUpperCase();
    const headers = new Headers(config.headers || {});
    if (config.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      if (!appState.csrfToken) {
        throw new Error("The session is missing its CSRF token. Sign in again.");
      }
      headers.set("X-CSRF-Token", appState.csrfToken);
    }

    const response = await fetch(path, {
      method: method,
      headers: headers,
      body: config.body,
      credentials: "same-origin",
      signal: config.signal,
    });
    let data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }
    if (response.status === 401) {
      location.assign("/");
      throw new Error("Session expired");
    }
    if (!response.ok) {
      throw new Error(data.detail || "Request failed");
    }
    return data;
  }

  function showToast(message, type) {
    const safeType = ["success", "error", "info"].includes(type) ? type : "info";
    const toast = createElement("div", {
      className: "toast toast-" + safeType,
      text: message,
      attributes: { role: safeType === "error" ? "alert" : "status" },
    });
    toastContainer.appendChild(toast);
    window.setTimeout(function () {
      toast.remove();
    }, 4500);
  }

  function onSidebarKeyDown(event) {
    if (event.key === "Escape" && sidebar.classList.contains("open")) {
      event.preventDefault();
      setSidebarOpen(false, true);
    }
  }

  function setSidebarOpen(isOpen, restoreFocus) {
    const wasOpen = sidebar.classList.contains("open");
    if (wasOpen === isOpen) {
      return;
    }
    if (isOpen) {
      sidebarReturnFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : menuButton;
    }
    sidebar.classList.toggle("open", isOpen);
    sidebarOverlay.hidden = !isOpen;
    menuButton.setAttribute("aria-expanded", String(isOpen));
    menuButton.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
    if (isOpen) {
      document.addEventListener("keydown", onSidebarKeyDown);
      window.requestAnimationFrame(function () {
        const firstNavigationItem = sidebar.querySelector(".nav-item[data-view]");
        if (firstNavigationItem instanceof HTMLElement) {
          firstNavigationItem.focus();
        }
      });
      return;
    }
    document.removeEventListener("keydown", onSidebarKeyDown);
    if (restoreFocus && sidebarReturnFocus instanceof HTMLElement && sidebarReturnFocus.isConnected) {
      sidebarReturnFocus.focus();
    }
    sidebarReturnFocus = null;
  }

  function isActiveNavigation(navigation) {
    return Boolean(
      navigation
      && !navigation.signal.aborted
      && navigation.generation === navigationGeneration,
    );
  }

  function isAbortError(error) {
    return Boolean(error && typeof error === "object" && error.name === "AbortError");
  }

  function renderLoading(label) {
    clearElement(mainBody);
    mainBody.appendChild(createElement("div", {
      className: "loading-state",
      children: [
        createElement("div", { className: "spinner", attributes: { "aria-hidden": "true" } }),
        createElement("p", { text: label || "Loading local intelligence…" }),
      ],
    }));
  }

  function renderError(message) {
    clearElement(mainBody);
    const retry = createButton("Try again", "btn btn-primary", function () {
      navigateTo(appState.currentView);
    });
    mainBody.appendChild(createElement("section", {
      className: "card empty-state",
      children: [
        createElement("div", { className: "empty-state-icon", text: "!", attributes: { "aria-hidden": "true" } }),
        createElement("h2", { text: "Unable to load this view" }),
        createElement("p", { text: message }),
        retry,
      ],
    }));
  }

  function renderStartupError(message) {
    clearElement(mainBody);
    const retry = createButton("Retry startup", "btn btn-primary", function () {
      initialize();
    });
    mainBody.appendChild(createElement("section", {
      className: "card empty-state",
      children: [
        createElement("div", { className: "empty-state-icon", text: "!", attributes: { "aria-hidden": "true" } }),
        createElement("h2", { text: "Unable to start the workspace" }),
        createElement("p", { text: message }),
        retry,
      ],
    }));
  }

  function emptyState(title, message) {
    return createElement("div", {
      className: "empty-state",
      children: [
        createElement("div", { className: "empty-state-icon", text: "◇", attributes: { "aria-hidden": "true" } }),
        createElement("h3", { text: title }),
        createElement("p", { text: message }),
      ],
    });
  }

  function statCard(label, value, tone, symbol) {
    return createElement("article", {
      className: "stat-card",
      children: [
        createElement("div", { className: "stat-icon " + tone, text: symbol, attributes: { "aria-hidden": "true" } }),
        createElement("div", {
          className: "stat-content",
          children: [
            createElement("div", { className: "stat-value", text: value }),
            createElement("div", { className: "stat-label", text: label }),
          ],
        }),
      ],
    });
  }

  function normalizeText(value, fallback) {
    const text = value === null || value === undefined ? "" : String(value).trim();
    return text || fallback || "—";
  }

  function formatDate(value) {
    if (!value) {
      return "—";
    }
    const text = String(value);
    const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
    let parsed;
    if (dateOnly) {
      const year = Number(dateOnly[1]);
      const month = Number(dateOnly[2]) - 1;
      const day = Number(dateOnly[3]);
      parsed = new Date(year, month, day);
      if (parsed.getFullYear() !== year || parsed.getMonth() !== month || parsed.getDate() !== day) {
        return text;
      }
    } else {
      parsed = new Date(text);
    }
    if (Number.isNaN(parsed.getTime())) {
      return text;
    }
    return new Intl.DateTimeFormat("en-GB", {
      year: "numeric",
      month: "short",
      day: "2-digit",
    }).format(parsed);
  }

  function verdictClass(value) {
    const key = String(value || "").toLowerCase();
    if (key.includes("contact")) {
      return "verdict-contact-now";
    }
    if (key.includes("verify")) {
      return "verdict-verify-first";
    }
    if (key.includes("watch")) {
      return "verdict-watch-list";
    }
    return "verdict-park";
  }

  function scoreClass(value) {
    const score = Number(value) || 0;
    if (score >= 70) {
      return "score-high";
    }
    if (score >= 40) {
      return "score-medium";
    }
    return "score-low";
  }

  function tableCell(content, className) {
    const cell = createElement("td", { className: className || "" });
    if (content instanceof Node) {
      cell.appendChild(content);
    } else {
      cell.textContent = normalizeText(content);
    }
    return cell;
  }

  function leadsTable(leads, compact) {
    if (!leads.length) {
      return emptyState("No verified leads", "Run a live refresh when public sources are available.");
    }
    const table = createElement("table", { className: "data-table" });
    const headRow = createElement("tr");
    ["Company", "Sector", "Signal", "Seen", "Score", "Verdict"].forEach(function (heading) {
      headRow.appendChild(createElement("th", { text: heading, attributes: { scope: "col" } }));
    });
    table.appendChild(createElement("thead", { children: [headRow] }));
    const body = createElement("tbody");
    leads.slice(0, compact ? 5 : leads.length).forEach(function (lead) {
      const row = createElement("tr");
      const leadIndex = appState.leads.indexOf(lead);
      const companyButton = createButton(
        normalizeText(lead.company, "Unnamed company"),
        "table-link-button",
        function () { openLeadModal(leadIndex); },
      );
      row.appendChild(tableCell(companyButton));
      row.appendChild(tableCell(lead.sector, "cell-truncate"));
      row.appendChild(tableCell(lead.trigger_type, "cell-truncate"));
      row.appendChild(tableCell(formatDate(lead.published_or_seen_date)));
      const score = Number(lead.score && lead.score.total) || 0;
      row.appendChild(tableCell(createElement("span", {
        className: "score-circle " + scoreClass(score),
        text: score,
        attributes: { "aria-label": "Lead score " + score },
      })));
      row.appendChild(tableCell(createElement("span", {
        className: verdictClass(lead.score && lead.score.verdict),
        text: normalizeText(lead.score && lead.score.verdict, "Unscored"),
      })));
      body.appendChild(row);
    });
    table.appendChild(body);
    return createElement("div", {
      className: "table-container",
      attributes: {
        role: "region",
        tabindex: "0",
        "aria-label": "Verified live leads. Scroll horizontally within this card on small screens.",
      },
      children: [table],
    });
  }

  function detailField(label, content, fullWidth) {
    const value = createElement("div", { className: "detail-value" });
    if (content instanceof Node) {
      value.appendChild(content);
    } else {
      value.textContent = normalizeText(content);
    }
    return createElement("div", {
      className: "detail-field" + (fullWidth ? " full-width" : ""),
      children: [
        createElement("div", { className: "detail-label", text: label }),
        value,
      ],
    });
  }

  function closeActiveModal() {
    if (appState.activeModalClose) {
      appState.activeModalClose();
    }
  }

  function openLeadModal(index) {
    const lead = appState.leads[index];
    if (!lead) {
      showToast("That lead is no longer available.", "error");
      return;
    }
    closeActiveModal();
    const previouslyFocused = document.activeElement;
    const overlay = createElement("div", {
      className: "modal-overlay",
      attributes: { role: "presentation" },
    });
    const modal = createElement("section", {
      className: "modal",
      attributes: {
        role: "dialog",
        "aria-modal": "true",
        "aria-labelledby": "leadModalTitle",
      },
    });
    const title = createElement("h2", { text: normalizeText(lead.company), attributes: { id: "leadModalTitle" } });
    const closeButton = createButton("×", "modal-close", function () { close(); });
    closeButton.setAttribute("aria-label", "Close lead details");
    modal.appendChild(createElement("header", {
      className: "modal-header",
      children: [title, closeButton],
    }));

    const score = lead.score || {};
    const details = createElement("div", {
      className: "detail-grid",
      children: [
        detailField("Country", lead.country),
        detailField("Sector", lead.sector),
        detailField("Trigger type", lead.trigger_type),
        detailField("Verdict", score.verdict),
        detailField("Score", score.total),
        detailField("Seen", formatDate(lead.published_or_seen_date)),
        detailField("Signal summary", lead.trigger_summary, true),
        detailField("Evidence excerpt", lead.evidence_excerpt, true),
        detailField("Public evidence", externalLink(lead.evidence_url, "Open verified source"), true),
        detailField("Source", lead.source_name),
        detailField("Fetched", formatDate(lead.fetched_at)),
      ],
    });
    modal.appendChild(createElement("div", { className: "modal-body", children: [details] }));
    modal.appendChild(createElement("footer", {
      className: "modal-footer",
      children: [createButton("Close", "btn btn-secondary", function () { close(); })],
    }));
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    document.body.classList.add("modal-open");

    function focusableElements() {
      return Array.from(modal.querySelectorAll("a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])"));
    }

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusable = focusableElements();
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      const currentIndex = focusable.indexOf(document.activeElement);
      const nextIndex = event.shiftKey
        ? (currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1)
        : (currentIndex < 0 || currentIndex === focusable.length - 1 ? 0 : currentIndex + 1);
      focusable[nextIndex].focus();
    }

    function close() {
      document.removeEventListener("keydown", onKeyDown);
      overlay.remove();
      document.body.classList.remove("modal-open");
      appState.activeModalClose = null;
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    }

    overlay.addEventListener("mousedown", function (event) {
      if (event.target === overlay) {
        close();
      }
    });
    document.addEventListener("keydown", onKeyDown);
    appState.activeModalClose = close;
    window.requestAnimationFrame(function () { closeButton.focus(); });
  }

  async function loadLeadsAndStats(navigation) {
    const responses = await Promise.all([
      apiFetch("/api/leads", { signal: navigation.signal }),
      apiFetch("/api/leads/stats", { signal: navigation.signal }),
    ]);
    if (!isActiveNavigation(navigation)) {
      return false;
    }
    appState.leads = responses[0].leads || [];
    appState.stats = responses[1];
    leadCountBadge.textContent = String(appState.leads.length);
    return true;
  }

  async function renderDashboard(navigation) {
    const responses = await Promise.all([
      apiFetch("/api/leads", { signal: navigation.signal }),
      apiFetch("/api/leads/stats", { signal: navigation.signal }),
      apiFetch("/api/state", { signal: navigation.signal }),
    ]);
    if (!isActiveNavigation(navigation)) {
      return;
    }
    appState.leads = responses[0].leads || [];
    appState.stats = responses[1];
    const state = responses[2];
    leadCountBadge.textContent = String(appState.leads.length);
    appState.notesOriginal = state.notes === null || state.notes === undefined ? "" : String(state.notes);

    clearElement(mainBody);
    const verdicts = appState.stats.verdicts || {};
    const statsGrid = createElement("section", {
      className: "stats-grid",
      attributes: { "aria-label": "Lead summary" },
      children: [
        statCard("Verified leads", appState.stats.total, "blue", "◆"),
        statCard("Average score", appState.stats.avg_score, "purple", "◎"),
        statCard("Contact now", verdicts["Contact now"] || 0, "green", "↑"),
        statCard("Sources healthy", state.sources_ok || 0, "cyan", "◇"),
      ],
    });
    mainBody.appendChild(statsGrid);

    const leadsCard = createElement("section", {
      className: "card dashboard-card",
      children: [
        createElement("header", {
          className: "card-header",
          children: [
            createElement("h2", { text: "Recent verified leads" }),
            createButton("View all", "btn btn-ghost btn-sm", function () { navigateTo("leads"); }),
          ],
        }),
        createElement("div", { className: "card-body-compact", children: [leadsTable(appState.leads, true)] }),
      ],
    });
    mainBody.appendChild(leadsCard);

    const notesInput = createElement("textarea", {
      className: "agent-input notes-input",
      attributes: {
        rows: "5",
        maxlength: "5000",
        "aria-label": "Shared workspace notes",
        placeholder: "Add local shared notes…",
      },
    });
    notesInput.value = appState.notesOriginal;
    const saveNotes = createButton("Save notes", "btn btn-primary", async function () {
      const submittedNotes = notesInput.value;
      saveNotes.disabled = true;
      try {
        await apiFetch("/api/state", {
          method: "PUT",
          body: JSON.stringify({ notes: submittedNotes }),
          signal: navigation.signal,
        });
        if (!isActiveNavigation(navigation)) {
          return;
        }
        appState.notesOriginal = submittedNotes;
        showToast("Notes saved locally.", "success");
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        showToast(error instanceof Error ? error.message : "Could not save notes", "error");
      } finally {
        if (isActiveNavigation(navigation) && saveNotes.isConnected) {
          saveNotes.disabled = false;
        }
      }
    });
    const cancelNotes = createButton("Cancel", "btn btn-secondary", function () {
      notesInput.value = appState.notesOriginal;
      notesInput.focus();
    });
    mainBody.appendChild(createElement("section", {
      className: "card dashboard-card",
      children: [
        createElement("header", { className: "card-header", children: [createElement("h2", { text: "Workspace notes" })] }),
        createElement("div", {
          className: "card-body",
          children: [
            notesInput,
            createElement("div", { className: "notes-actions", children: [cancelNotes, saveNotes] }),
          ],
        }),
      ],
    }));
  }

  async function renderLeads(navigation) {
    if (!await loadLeadsAndStats(navigation)) {
      return;
    }
    clearElement(mainBody);
    const refreshButton = createButton("Refresh live sources", "btn btn-primary", async function () {
      refreshButton.disabled = true;
      refreshButton.setAttribute("aria-busy", "true");
      try {
        const result = await apiFetch("/api/leads/refresh", {
          method: "POST",
          signal: navigation.signal,
        });
        if (!isActiveNavigation(navigation)) {
          return;
        }
        showToast("Live refresh saved " + result.count + " verified leads.", "success");
        await renderLeads(navigation);
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        showToast(error instanceof Error ? error.message : "Live refresh failed", "error");
      } finally {
        if (isActiveNavigation(navigation) && refreshButton.isConnected) {
          refreshButton.disabled = false;
          refreshButton.removeAttribute("aria-busy");
        }
      }
    });
    mainBody.appendChild(createElement("section", {
      className: "card leads-card",
      children: [
        createElement("header", {
          className: "card-header card-header-responsive",
          children: [
            createElement("div", {
              children: [
                createElement("h2", { text: "Verified public-signal leads" }),
                createElement("p", { className: "text-sm text-secondary", text: "Every row must retain live source evidence." }),
              ],
            }),
            refreshButton,
          ],
        }),
        createElement("div", { className: "card-body-compact table-card-body", children: [leadsTable(appState.leads, false)] }),
      ],
    }));
  }

  function sourceFetchState(statusData) {
    const fetchStatus = String(statusData.fetch_status || "").trim().toLowerCase();
    if (["success", "recovered"].includes(fetchStatus)) {
      return { state: "online", label: "Last fetch succeeded" };
    }
    if (fetchStatus === "failed") {
      return { state: "offline", label: "Last fetch failed" };
    }
    return { state: "unknown", label: "Last fetch status unknown" };
  }

  async function renderSources(navigation) {
    const data = await apiFetch("/api/sources", { signal: navigation.signal });
    if (!isActiveNavigation(navigation)) {
      return;
    }
    appState.sources = data.sources || [];
    clearElement(mainBody);
    const sourceList = createElement("div", { className: "source-list" });
    appState.sources.forEach(function (source) {
      const statusData = source.last_fetch_status || {};
      const fetchState = sourceFetchState(statusData);
      const sourceUrl = source.base_url || source.fetch_url || statusData.configured_url;
      sourceList.appendChild(createElement("article", {
        className: "source-item",
        children: [
          createElement("span", {
            className: "source-status-dot " + fetchState.state,
            attributes: { "aria-label": fetchState.label },
          }),
          createElement("div", {
            className: "source-info",
            children: [
              createElement("h3", { className: "source-name", text: normalizeText(source.source_name) }),
              externalLink(sourceUrl, normalizeText(sourceUrl, "No URL configured")),
              createElement("p", {
                className: "source-meta",
                text: normalizeText(source.source_type, "public source") + " · " + normalizeText(source.country, "Sri Lanka"),
              }),
              createElement("p", { className: "text-sm text-secondary", text: normalizeText(source.limitations, source.notes) }),
            ],
          }),
        ],
      }));
    });
    mainBody.appendChild(createElement("section", {
      className: "card",
      children: [
        createElement("header", {
          className: "card-header",
          children: [
            createElement("h2", { text: "Configured public sources" }),
            createElement("span", { className: "badge badge-blue", text: data.source_count || appState.sources.length }),
          ],
        }),
        createElement("div", {
          className: "card-body",
          children: [appState.sources.length ? sourceList : emptyState("No sources configured", "Add public sources through the ADK source registry.")],
        }),
      ],
    }));
  }

  function resultField(label, value) {
    return createElement("div", {
      className: "result-field",
      children: [
        createElement("span", { className: "detail-label", text: label }),
        createElement("strong", { text: normalizeText(value) }),
      ],
    });
  }

  async function renderAgent(navigation) {
    if (!isActiveNavigation(navigation)) {
      return;
    }
    clearElement(mainBody);
    const queryInput = createElement("textarea", {
      className: "agent-input",
      attributes: {
        rows: "8",
        maxlength: "5000",
        placeholder: "Paste a public-signal description for classification or service-fit preview…",
        "aria-label": "Public-signal text",
      },
    });
    const result = createElement("div", {
      className: "agent-result",
      attributes: { role: "status", "aria-live": "polite" },
      children: [createElement("p", { className: "text-secondary", text: "Results will appear here." })],
    });

    async function runTool(path, mode) {
      const query = queryInput.value.trim();
      if (!query) {
        showToast("Enter signal text first.", "error");
        queryInput.focus();
        return;
      }
      classifyButton.disabled = true;
      fitButton.disabled = true;
      queryInput.readOnly = true;
      clearElement(result);
      result.appendChild(createElement("p", { text: "Evaluating local policy rules…" }));
      try {
        const data = await apiFetch(path, {
          method: "POST",
          body: JSON.stringify({ query: query }),
          signal: navigation.signal,
        });
        if (!isActiveNavigation(navigation)) {
          return;
        }
        clearElement(result);
        if (mode === "classify") {
          result.appendChild(resultField("Trigger", data.trigger_type));
          result.appendChild(resultField("Confidence", Math.round(Number(data.confidence) * 100) + "%"));
          result.appendChild(createElement("p", { text: normalizeText(data.reason) }));
        } else {
          result.appendChild(resultField("Trigger", data.classification && data.classification.trigger_type));
          result.appendChild(resultField("Service fit", (data.service_fit || []).join(", ") || "No direct 1BT fit detected"));
          result.appendChild(createElement("p", { className: "fit-preview-warning", text: normalizeText(data.explanation) }));
        }
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        clearElement(result);
        result.appendChild(createElement("p", {
          className: "text-danger",
          text: error instanceof Error ? error.message : "Evaluation failed",
        }));
      } finally {
        if (isActiveNavigation(navigation) && queryInput.isConnected) {
          classifyButton.disabled = false;
          fitButton.disabled = false;
          queryInput.readOnly = false;
        }
      }
    }

    const classifyButton = createButton("Classify signal", "btn btn-primary", function () {
      runTool("/api/agent/classify", "classify");
    });
    const fitButton = createButton("Preview service fit", "btn btn-secondary", function () {
      runTool("/api/agent/fit-preview", "fit");
    });
    mainBody.appendChild(createElement("section", {
      className: "card agent-panel",
      children: [
        createElement("header", {
          className: "card-header",
          children: [createElement("div", {
            children: [
              createElement("h2", { text: "Text-only policy preview" }),
              createElement("p", {
                className: "text-sm text-secondary",
                text: "Classification and service fit only. This tool never creates evidence or a lead verdict.",
              }),
            ],
          })],
        }),
        createElement("div", {
          className: "card-body agent-input-area",
          children: [
            queryInput,
            createElement("div", { className: "agent-actions", children: [classifyButton, fitButton] }),
            result,
          ],
        }),
      ],
    }));
  }

  async function renderAbout(navigation) {
    if (!isActiveNavigation(navigation)) {
      return;
    }
    clearElement(mainBody);
    const items = [
      "Local-only FastAPI workspace bound to 127.0.0.1",
      "One intentional shared account; no multi-user tenancy",
      "Runtime leads require genuine HTTP(S) public evidence",
      "Tender and procurement-only signals are rejected",
      "Saved snapshots are bootstrap-only; Refresh performs a live fetch",
    ];
    const list = createElement("ul", { className: "about-list" });
    items.forEach(function (item) {
      list.appendChild(createElement("li", { text: item }));
    });
    mainBody.appendChild(createElement("section", {
      className: "card",
      children: [
        createElement("header", { className: "card-header", children: [createElement("h2", { text: "Business Intel guardrails" })] }),
        createElement("div", {
          className: "card-body",
          children: [
            createElement("p", { text: "Sri Lanka public-signal lead intelligence for evidence-led 1BT outreach." }),
            list,
          ],
        }),
      ],
    }));
  }

  async function navigateTo(view) {
    if (!Object.prototype.hasOwnProperty.call(viewTitles, view)) {
      return;
    }
    if (navigationController) {
      navigationController.abort();
    }
    navigationController = new AbortController();
    navigationGeneration += 1;
    const navigation = {
      generation: navigationGeneration,
      signal: navigationController.signal,
    };
    appState.currentView = view;
    pageTitle.textContent = viewTitles[view];
    document.querySelectorAll(".nav-item[data-view]").forEach(function (item) {
      const active = item.dataset.view === view;
      item.classList.toggle("active", active);
      if (active) {
        item.setAttribute("aria-current", "page");
      } else {
        item.removeAttribute("aria-current");
      }
    });
    setSidebarOpen(false, false);
    renderLoading();
    try {
      if (view === "dashboard") {
        await renderDashboard(navigation);
      } else if (view === "leads") {
        await renderLeads(navigation);
      } else if (view === "sources") {
        await renderSources(navigation);
      } else if (view === "agent") {
        await renderAgent(navigation);
      } else {
        await renderAbout(navigation);
      }
      if (isActiveNavigation(navigation)) {
        mainBody.focus();
      }
    } catch (error) {
      if (!isAbortError(error) && isActiveNavigation(navigation)) {
        renderError(error instanceof Error ? error.message : "Unexpected error");
      }
    }
  }

  async function handleLogout() {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (error) {
      if (error instanceof Error && error.message !== "Session expired") {
        showToast(error.message, "error");
        return;
      }
    }
    location.assign("/");
  }

  async function initialize() {
    try {
      const session = await apiFetch("/api/auth/verify");
      appState.csrfToken = session.csrf_token;
      document.getElementById("sharedUserName").textContent = session.user;
      document.getElementById("headerUserName").textContent = session.user;
    } catch (error) {
      if (error instanceof Error && error.message === "Session expired") {
        return;
      }
      renderStartupError(error instanceof Error ? error.message : "Session verification failed");
      return;
    }

    document.querySelectorAll(".nav-item[data-view]").forEach(function (item) {
      item.addEventListener("click", function () {
        setSidebarOpen(false, false);
        navigateTo(item.dataset.view);
      });
    });
    menuButton.addEventListener("click", function () {
      setSidebarOpen(!sidebar.classList.contains("open"), true);
    });
    sidebarOverlay.addEventListener("click", function () { setSidebarOpen(false, true); });
    document.getElementById("logoutBtn").addEventListener("click", handleLogout);
    window.addEventListener("resize", function () {
      if (window.innerWidth > 768) {
        setSidebarOpen(false, false);
      }
    });
    await navigateTo("dashboard");
  }

  initialize();
}());
