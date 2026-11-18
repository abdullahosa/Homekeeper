/* Homekeeper setup page (sidebar, admins only). No build step, no dependencies.
 *
 * Home Assistant's integration page shows every person, module, duty and biller in one flat,
 * alphabetical list and cannot collapse or group it. This page shows the same things in
 * collapsible sections, with what is still missing next to each row. Adding and editing
 * still happens on the integration page, which is one tap away.
 */
const SECTION_TEXT = {
  people: { title: "People", empty: "No one yet. Add each family member." },
  modules: { title: "Modules", empty: "No modules yet. A module is a folder of duties, like Lawn or Bills." },
  duties: { title: "Duties", empty: "No duties yet. Add one, or import a pack." },
  billers: { title: "Billers", empty: "No billers yet. Add each company BillBot reads bills or rent from." },
};

const ISSUE_TEXT = {
  no_notify: "No phone set for notifications",
  no_owners: "No default owner",
  no_duties: "Nothing in it yet",
  no_owner: "No owner (set one here or on its module)",
  no_module: "Its module no longer exists",
  income_completes_nothing: "Does not complete any duty yet (for example the rent duty)",
};

const SETTINGS_PATH = "/config/integrations/integration/homekeeper";
const STORE_KEY = "homekeeper-setup-open";

const CSS = `
:host { display: block; background: var(--primary-background-color); min-height: 100%; color: var(--primary-text-color); }
.bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--app-header-background-color, var(--primary-color, #03a9f4));
  color: var(--app-header-text-color, #fff); position: sticky; top: 0; z-index: 2; }
.bar h1 { margin: 0; font-size: 1.25rem; font-weight: 500; flex: 1; }
.bar button { background: transparent; color: inherit; border: 1px solid #fff6; border-radius: 8px; padding: 6px 12px; font: inherit; cursor: pointer; }
main { max-width: 760px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
.summary { padding: 12px 16px; border-radius: 12px; margin-bottom: 16px; font-weight: 500;
  background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #0002); }
.summary.good { border-color: var(--success-color, #2e7d32); }
.summary.todo { border-color: var(--warning-color, #ef6c00); }
details { background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #0002);
  border-radius: 12px; margin-bottom: 12px; overflow: hidden; }
summary { display: flex; align-items: center; gap: 10px; padding: 14px 16px; cursor: pointer; list-style: none; font-weight: 600; font-size: 1.05rem; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "▸"; transition: transform .15s; display: inline-block; }
details[open] > summary::before { transform: rotate(90deg); }
:host-context([dir="rtl"]) summary::before { content: "◂"; }
.count { margin-inline-start: auto; display: flex; gap: 6px; align-items: center; font-weight: 400; font-size: .85rem; }
.pill { padding: 2px 10px; border-radius: 999px; background: var(--secondary-background-color, #eee); }
.pill.todo { background: var(--warning-color, #ef6c00); color: #fff; font-weight: 600; }
.pill.ok { background: var(--success-color, #2e7d32); color: #fff; }
.rows { border-top: 1px solid var(--divider-color, #0002); }
.row { padding: 10px 16px; border-bottom: 1px solid var(--divider-color, #0001); }
.row:last-child { border-bottom: 0; }
.row .t { font-weight: 500; overflow-wrap: anywhere; }
.row .d { font-size: .85rem; color: var(--secondary-text-color, #666); margin-top: 2px; }
.row .i { font-size: .85rem; color: var(--warning-color, #ef6c00); margin-top: 4px; font-weight: 500; }
.empty { padding: 14px 16px; color: var(--secondary-text-color, #666); }
a.go { display: inline-block; margin: 8px 16px 14px; color: var(--primary-color, #03a9f4); font-weight: 600; text-decoration: none; cursor: pointer; }
.err { padding: 16px; color: var(--error-color, #c62828); }
`;

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class HomekeeperSetup extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._open = this._readOpen();
    this._unsub = null;
    this._defaults = {};
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }

  set narrow(_value) {}
  set route(_value) {}
  set panel(_value) {}

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  async _start() {
    await this._load();
    try {
      this._unsub = await this._hass.connection.subscribeEvents(() => this._load(), "homekeeper_changed");
    } catch (_err) {
      /* the page still works without live refresh */
    }
  }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: "homekeeper/setup" });
      this._error = null;
    } catch (err) {
      this._error = err && err.message ? err.message : "Could not load the setup";
    }
    this._render();
  }

  _readOpen() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    } catch (_err) {
      return null; // null = use the defaults (sections with something to do are open)
    }
  }

  _saveOpen() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(this._open));
    } catch (_err) {
      /* remembering is a convenience only */
    }
  }

  _isOpen(kind, fallback) {
    if (this._open && kind in this._open) return !!this._open[kind];
    return fallback;
  }

  _setAll(open) {
    this._open = {};
    for (const s of this._data.sections) this._open[s.kind] = open;
    this._saveOpen();
    this._render();
  }

  _goSettings(event) {
    event.preventDefault();
    history.pushState(null, "", SETTINGS_PATH);
    window.dispatchEvent(new CustomEvent("location-changed"));
  }

  _render() {
    const root = this.shadowRoot;
    let body;
    if (this._error && !this._data) {
      body = `<div class="err">${esc(this._error)}</div>`;
    } else if (!this._data) {
      body = `<div class="empty">Loading…</div>`;
    } else {
      const todo = this._data.todo_count;
      const summary = todo
        ? `<div class="summary todo">${todo} item${todo === 1 ? "" : "s"} still need${todo === 1 ? "s" : ""} setting up. Those sections are open below.</div>`
        : `<div class="summary good">Everything you have added is complete.</div>`;
      const sections = this._data.sections
        .map((section) => {
          const text = SECTION_TEXT[section.kind];
          const needs = section.items.filter((i) => i.issues.length).length;
          const rows = section.items.length
            ? section.items
                .map(
                  (i) => `<div class="row"><div class="t">${esc(i.title)}</div><div class="d">${esc(i.detail)}</div>${i.issues
                    .map((code) => `<div class="i">⚠ ${esc(ISSUE_TEXT[code] || code)}</div>`)
                    .join("")}</div>`,
                )
                .join("")
            : `<div class="empty">${esc(text.empty)}</div>`;
          const pills = `<span class="pill">${section.items.length}</span>${
            needs ? `<span class="pill todo">${needs} to do</span>` : section.items.length ? `<span class="pill ok">✓</span>` : ""
          }`;
          // Open by default when there is something to do (or nothing added yet).
          this._defaults[section.kind] = needs > 0 || section.items.length === 0;
          const open = this._isOpen(section.kind, this._defaults[section.kind]) ? "open" : "";
          return `<details data-kind="${esc(section.kind)}" ${open}><summary>${esc(text.title)}<span class="count">${pills}</span></summary><div class="rows">${rows}</div><a class="go" href="${SETTINGS_PATH}">Add or edit ${esc(text.title.toLowerCase())} →</a></details>`;
        })
        .join("");
      body = summary + sections;
    }
    root.innerHTML = `<style>${CSS}</style>
      <div class="bar"><h1>Homekeeper</h1><button data-all="open">Expand all</button><button data-all="close">Collapse all</button></div>
      <main>${body}</main>`;
    root.querySelectorAll("a.go").forEach((a) => a.addEventListener("click", (e) => this._goSettings(e)));
    root.querySelectorAll("button[data-all]").forEach((b) =>
      b.addEventListener("click", () => this._data && this._setAll(b.dataset.all === "open")),
    );
    root.querySelectorAll("details").forEach((d) =>
      d.addEventListener("toggle", () => {
        // Rendering a section open fires this too; only remember real choices.
        if (d.open === this._isOpen(d.dataset.kind, this._defaults[d.dataset.kind])) return;
        this._open = this._open || {};
        this._open[d.dataset.kind] = d.open;
        this._saveOpen();
      }),
    );
  }
}

if (!customElements.get("homekeeper-setup")) {
  customElements.define("homekeeper-setup", HomekeeperSetup);
}
