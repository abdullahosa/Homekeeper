/* Homekeeper card. No build step, no dependencies.
 *
 *   type: custom:homekeeper-card
 *   mode: list | wall          (wall = big tiles for a tablet on the wall)
 *   language: en | ar          (default: Home Assistant's language)
 *   person: <person id>        (show only this person's duties; default: everyone)
 *   module: <module id>        (show only one module)
 *   horizon_days: 14           (how far ahead to show upcoming duties)
 *   confirm: true              (tap Done twice; set false for one tap)
 *   title: Homekeeper
 */
const STR = {
  en: {
    overdue: "Overdue", due_today: "Due today", in_days: (n) => `In ${n} day${n === 1 ? "" : "s"}`,
    days_late: (n) => `${n} day${n === 1 ? "" : "s"} late`, tomorrow: "Tomorrow",
    done: "Done", confirm: "Tap again to confirm", snooze: "Snooze 1 day", snoozed: "Snoozed",
    caught_up: "All caught up", upcoming: "Coming up", everyone: "Everyone", all: "All",
    owner: "Owner", problems: "Needs attention", loading: "Loading…", not_ready: "Homekeeper is not set up",
    failed: "That did not work", until: "until",
  },
  ar: {
    overdue: "متأخرة", due_today: "مستحقة اليوم", in_days: (n) => `بعد ${n} يوم`,
    days_late: (n) => `متأخرة ${n} يوم`, tomorrow: "غداً",
    done: "تم", confirm: "اضغط مرة أخرى للتأكيد", snooze: "تأجيل يوم", snoozed: "مؤجلة",
    caught_up: "كل شيء منجز", upcoming: "قريباً", everyone: "الجميع", all: "الكل",
    owner: "المسؤول", problems: "يحتاج انتباه", loading: "جارٍ التحميل…", not_ready: "Homekeeper غير مُعد",
    failed: "لم تنجح العملية", until: "حتى",
  },
};

const CSS = `
:host { display: block; }
ha-card, .card { display: block; padding: 16px; box-sizing: border-box; }
.card { background: var(--ha-card-background, var(--card-background-color, #fff));
  color: var(--primary-text-color, #222); border-radius: var(--ha-card-border-radius, 12px);
  box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color, #0001); }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
h2 { margin: 0; font-size: 1.25rem; font-weight: 600; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: .85rem; font-weight: 600;
  background: var(--success-color, #2e7d32); color: #fff; }
.badge.bad { background: var(--error-color, #c62828); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip { border: 1px solid var(--divider-color, #0003); background: transparent; color: inherit;
  border-radius: 999px; padding: 4px 12px; cursor: pointer; font: inherit; font-size: .85rem; }
.chip[aria-pressed="true"] { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
  border-color: var(--primary-color, #03a9f4); }
.list { display: flex; flex-direction: column; gap: 8px; }
.row { display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; align-items: center;
  padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color, #f5f5f5);
  border-inline-start: 5px solid var(--divider-color, #999); }
.row.overdue { border-inline-start-color: var(--error-color, #c62828); }
.row.due { border-inline-start-color: var(--warning-color, #ef6c00); }
.row.upcoming { border-inline-start-color: var(--info-color, #0288d1); }
.row.snoozed { opacity: .7; }
.title { font-weight: 600; font-size: 1rem; overflow-wrap: anywhere; }
.meta { font-size: .85rem; color: var(--secondary-text-color, #666); margin-top: 2px; }
.meta .late { color: var(--error-color, #c62828); font-weight: 600; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
button.act { font: inherit; border-radius: 8px; border: 0; cursor: pointer; padding: 8px 14px; min-height: 40px;
  background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); font-weight: 600; }
button.act.ghost { background: transparent; color: var(--primary-text-color, #222);
  border: 1px solid var(--divider-color, #0004); font-weight: 500; }
button.act.confirming { background: var(--success-color, #2e7d32); }
button.act:focus-visible, .chip:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
h3 { margin: 16px 0 8px; font-size: .9rem; text-transform: uppercase; letter-spacing: .05em;
  color: var(--secondary-text-color, #666); }
.empty { text-align: center; padding: 32px 8px; font-size: 1.1rem; color: var(--secondary-text-color, #666); }
.err { margin-top: 8px; color: var(--error-color, #c62828); font-size: .9rem; }
.warn { margin-top: 12px; padding: 8px 12px; border-radius: 8px; font-size: .9rem;
  background: color-mix(in srgb, var(--warning-color, #ef6c00) 18%, transparent); }

/* wall panel */
.wall { padding: 24px; }
.wall h2 { font-size: 2rem; }
.wall .badge { font-size: 1.2rem; padding: 4px 16px; }
.wall .chip { font-size: 1.15rem; padding: 10px 20px; min-height: 48px; }
.wall .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.wall .tile { display: flex; flex-direction: column; justify-content: space-between; gap: 16px; min-height: 190px;
  padding: 20px; border-radius: 18px; background: var(--secondary-background-color, #f5f5f5);
  border-top: 10px solid var(--divider-color, #999); }
.wall .tile.overdue { border-top-color: var(--error-color, #c62828); }
.wall .tile.due { border-top-color: var(--warning-color, #ef6c00); }
.wall .tile.upcoming { border-top-color: var(--info-color, #0288d1); }
.wall .tile .title { font-size: 1.7rem; line-height: 1.2; }
.wall .tile .meta { font-size: 1.15rem; }
.wall button.act { font-size: 1.4rem; min-height: 64px; width: 100%; border-radius: 14px; }
.wall button.act.ghost { font-size: 1rem; min-height: 48px; }
.wall .empty { font-size: 2.2rem; padding: 64px 8px; }
.wall h3 { font-size: 1.1rem; }
`;

class HomekeeperCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._person = null;   // chip filter
    this._module = null;
    this._confirming = null;
    this._loading = false;
    this._unsub = null;
    this._timer = null;
  }

  setConfig(config) {
    this._config = { mode: "list", horizon_days: 14, confirm: true, ...config };
    this._person = config.person && config.person !== "me" ? config.person : null;
    this._module = config.module || null;
    this._render();
  }

  getCardSize() { return this._config && this._config.mode === "wall" ? 8 : 5; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }
  static getStubConfig() { return { mode: "list" }; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) { this._start(); }
  }

  connectedCallback() { if (this._hass && !this._unsub) { this._start(); } }
  disconnectedCallback() { this._stop(); }

  async _start() {
    this._stop();
    this._load();
    try {
      this._unsub = await this._hass.connection.subscribeEvents(() => this._load(), "homekeeper_changed");
    } catch (e) { /* the periodic refresh below still keeps it fresh */ }
    this._timer = setInterval(() => this._load(), 5 * 60 * 1000);
  }

  _stop() {
    if (this._unsub) { try { this._unsub(); } catch (e) { /* closed */ } this._unsub = null; }
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  }

  async _load() {
    if (!this._hass || this._loading) { return; }
    this._loading = true;
    try {
      this._data = await this._hass.callWS({
        type: "homekeeper/overview", horizon_days: this._config.horizon_days,
      });
      this._error = null;
      if (this._config.person === "me" && this._data.me) { this._person = this._data.me; }
    } catch (e) {
      this._error = (e && e.code === "not_loaded") ? "not_ready" : "failed";
      this._data = this._data || null;
    }
    this._loading = false;
    this._render();
  }

  get _lang() {
    const l = this._config.language || (this._hass && this._hass.language) || "en";
    return l.toLowerCase().startsWith("ar") ? "ar" : "en";
  }
  get _t() { return STR[this._lang]; }

  _title(item) { return item.title[this._lang] || item.title.en || item.duty_id; }
  _moduleTitle(m) { return (m.title && (m.title[this._lang] || m.title.en)) || m.id; }

  _when(item) {
    const t = this._t;
    if (item.state === "snoozed") { return `${t.snoozed} ${t.until} \u2066${item.snoozed_until || ""}\u2069`.trim(); }
    if (item.days < 0) { return t.days_late(-item.days); }
    if (item.days === 0) { return t.due_today; }
    if (item.days === 1) { return t.tomorrow; }
    return t.in_days(item.days);
  }

  _visible() {
    if (!this._data) { return []; }
    return this._data.items.filter((i) =>
      (!this._person || i.owners.includes(this._person)) &&
      (!this._module || i.module === this._module));
  }

  async _call(service, data) {
    try {
      await this._hass.callService("homekeeper", service, data);
      this._error = null;
    } catch (e) {
      this._error = "failed";
    }
    await this._load();
  }

  _onDone(item) {
    const need = this._config.confirm !== false;
    if (need && this._confirming !== item.duty_id) {
      this._confirming = item.duty_id;
      clearTimeout(this._confirmTimer);
      this._confirmTimer = setTimeout(() => { this._confirming = null; this._render(); }, 4000);
      this._render();
      return;
    }
    this._confirming = null;
    const by = this._config.person && this._config.person !== "me" ? this._config.person
      : (this._data && this._data.me) || undefined;
    this._call("complete", { duty_id: item.duty_id, method: "button", ...(by ? { by } : {}) });
  }

  _onSnooze(item) { this._call("snooze", { duty_id: item.duty_id, hours: 24 }); }

  _chip(label, pressed, onClick) {
    const b = document.createElement("button");
    b.className = "chip"; b.textContent = label; b.setAttribute("aria-pressed", String(pressed));
    b.addEventListener("click", onClick);
    return b;
  }

  _actions(item) {
    const t = this._t;
    const box = document.createElement("div");
    box.className = "actions";
    const done = document.createElement("button");
    done.className = "act" + (this._confirming === item.duty_id ? " confirming" : "");
    done.textContent = this._confirming === item.duty_id ? t.confirm : t.done;
    done.addEventListener("click", () => this._onDone(item));
    box.append(done);
    if (item.state === "overdue" || item.state === "due") {
      const sn = document.createElement("button");
      sn.className = "act ghost"; sn.textContent = t.snooze;
      sn.addEventListener("click", () => this._onSnooze(item));
      box.append(sn);
    }
    return box;
  }

  _meta(item) {
    const t = this._t;
    const meta = document.createElement("div");
    meta.className = "meta";
    const when = document.createElement("span");
    when.textContent = this._when(item);
    if (item.state === "overdue") { when.className = "late"; }
    meta.append(when);
    const owners = item.owners
      .map((id) => (this._data.people.find((p) => p.id === id) || {}).name).filter(Boolean).join(", ");
    const parts = [];
    if (item.amount != null) { parts.push(`$${Number(item.amount).toFixed(2)}`); }
    if (owners) { parts.push(owners); }
    if (parts.length) { meta.append(document.createTextNode(` · ${parts.join(" · ")}`)); }
    return meta;
  }

  _render() {
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = document.createElement("style");
    style.textContent = CSS;
    root.append(style);
    if (!this._config) { return; }
    const wall = this._config.mode === "wall";
    const t = this._t;
    const card = document.createElement("div");
    card.className = "card" + (wall ? " wall" : "");
    card.setAttribute("dir", this._lang === "ar" ? "rtl" : "ltr");
    root.append(card);

    if (!this._data) {
      const p = document.createElement("div");
      p.className = this._error ? "err" : "empty";
      p.textContent = this._error ? t[this._error] : t.loading;
      card.append(p);
      return;
    }

    const items = this._visible();
    const needs = items.filter((i) => i.state === "overdue" || i.state === "due");
    const later = items.filter((i) => i.state === "upcoming" || i.state === "snoozed");

    const header = document.createElement("header");
    const h = document.createElement("h2");
    h.textContent = this._config.title || "Homekeeper";
    const badge = document.createElement("span");
    const overdue = items.filter((i) => i.state === "overdue").length;
    badge.className = "badge" + (overdue ? " bad" : "");
    badge.textContent = overdue ? `${overdue} ${t.overdue}` : (needs.length ? `${needs.length}` : "✓");
    header.append(h, badge);
    card.append(header);

    // filters: people, then modules (hidden when the card is pinned to one)
    if (!this._config.person && this._data.people.length > 1) {
      const chips = document.createElement("div");
      chips.className = "chips";
      chips.append(this._chip(t.everyone, !this._person, () => { this._person = null; this._render(); }));
      this._data.people.forEach((p) => chips.append(
        this._chip(p.name, this._person === p.id, () => { this._person = p.id; this._render(); })));
      card.append(chips);
    }
    if (!this._config.module && this._data.modules.length > 1) {
      const chips = document.createElement("div");
      chips.className = "chips";
      chips.append(this._chip(t.all, !this._module, () => { this._module = null; this._render(); }));
      this._data.modules.forEach((m) => chips.append(
        this._chip(this._moduleTitle(m), this._module === m.id, () => { this._module = m.id; this._render(); })));
      card.append(chips);
    }

    const section = (list) => {
      const box = document.createElement("div");
      box.className = wall ? "tiles" : "list";
      list.forEach((item) => {
        const row = document.createElement("div");
        row.className = (wall ? "tile " : "row ") + item.state;
        const text = document.createElement("div");
        const title = document.createElement("div");
        title.className = "title"; title.textContent = this._title(item);
        text.append(title, this._meta(item));
        row.append(text, this._actions(item));
        box.append(row);
      });
      return box;
    };

    if (needs.length) { card.append(section(needs)); }
    else {
      const e = document.createElement("div");
      e.className = "empty"; e.textContent = `✓ ${t.caught_up}`;
      card.append(e);
    }
    if (later.length) {
      const h3 = document.createElement("h3");
      h3.textContent = t.upcoming;
      card.append(h3, section(later));
    }

    if (this._error) {
      const e = document.createElement("div");
      e.className = "err"; e.setAttribute("role", "alert"); e.textContent = t[this._error] || t.failed;
      card.append(e);
    }
    const problems = this._data.health && this._data.health.problems;
    if (problems && problems.length && !wall) {
      const w = document.createElement("div");
      w.className = "warn";
      w.textContent = `${t.problems}: ${problems.join(", ")}`;
      card.append(w);
    }
  }
}

if (!customElements.get("homekeeper-card")) {
  customElements.define("homekeeper-card", HomekeeperCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "homekeeper-card")) {
  window.customCards.push({
    type: "homekeeper-card",
    name: "Homekeeper",
    description: "What needs doing at home, with one-tap Done. Includes a big-button wall-panel mode.",
  });
}
