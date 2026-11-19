/* Homekeeper card. No build step, no dependencies.
 *
 *   type: custom:homekeeper-card
 *   mode: list | wall | bills  (wall = big tiles for a tablet; bills = every biller's
 *                               latest bill: amount, due date, status, Pay link, Mark paid)
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
    failed: "That did not work", until: "until", login: "Log in",
    bills: "Bills", pay: "Pay", mark_paid: "Mark paid", total_due: (a) => `${a} due`,
    no_billers: "No billers yet. Add them in Homekeeper's settings.",
    st: { overdue: "Overdue", due: "Due", autopay: "Autopay", paid: "Paid", received: "Received",
      none: "No bill yet", none_income: "No payment yet" },
    received_on: (d) => `Received ${d}`, due_on: (d) => `Due ${d}`,
  },
  ar: {
    overdue: "متأخرة", due_today: "مستحقة اليوم", in_days: (n) => `بعد ${n} يوم`,
    days_late: (n) => `متأخرة ${n} يوم`, tomorrow: "غداً",
    done: "تم", confirm: "اضغط مرة أخرى للتأكيد", snooze: "تأجيل يوم", snoozed: "مؤجلة",
    caught_up: "كل شيء منجز", upcoming: "قريباً", everyone: "الجميع", all: "الكل",
    owner: "المسؤول", problems: "يحتاج انتباه", loading: "جارٍ التحميل…", not_ready: "Homekeeper غير مُعد",
    failed: "لم تنجح العملية", until: "حتى", login: "تسجيل الدخول",
    bills: "الفواتير", pay: "ادفع", mark_paid: "تم الدفع", total_due: (a) => `${a} مستحق`,
    no_billers: "لا توجد جهات فواتير بعد. أضفها من إعدادات Homekeeper.",
    st: { overdue: "متأخرة", due: "مستحقة", autopay: "دفع تلقائي", paid: "مدفوعة", received: "تم الاستلام",
      none: "لا توجد فاتورة", none_income: "لا توجد دفعة" },
    received_on: (d) => `استُلمت ${d}`, due_on: (d) => `تستحق ${d}`,
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
.login { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 12px; margin-top: 4px;
  font-size: .85rem; color: var(--secondary-text-color, #666); overflow-wrap: anywhere; }
.login a { color: var(--primary-color, #03a9f4); font-weight: 600; text-decoration: none;
  display: inline-flex; align-items: center; min-height: 32px; }
.login a:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
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
.wall .login { font-size: 1rem; }
.wall .login a { min-height: 44px; }
.wall .empty { font-size: 2.2rem; padding: 64px 8px; }
.total { font-size: .9rem; color: var(--secondary-text-color, #666); margin: -6px 0 12px; }
.bill { display: grid; grid-template-columns: auto 1fr auto; gap: 8px 12px; align-items: center;
  padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color, #f5f5f5);
  border-inline-start: 5px solid var(--divider-color, #999); }
.bill.overdue { border-inline-start-color: var(--error-color, #c62828); }
.bill.due { border-inline-start-color: var(--warning-color, #ef6c00); }
.bill.autopay { border-inline-start-color: var(--info-color, #0288d1); }
.bill.paid, .bill.received { border-inline-start-color: var(--success-color, #2e7d32); }
.bill.none { opacity: .75; }
.bill ha-icon { color: var(--secondary-text-color, #666); --mdc-icon-size: 26px; width: 26px; }
.bill .sub { font-size: .85rem; color: var(--secondary-text-color, #666); }
.pill { display: inline-block; font-size: .75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px;
  margin-inline-end: 6px; background: var(--divider-color, #0002); color: var(--primary-text-color, #222); }
.pill.overdue { background: var(--error-color, #c62828); color: #fff; }
.pill.due { background: var(--warning-color, #ef6c00); color: #fff; }
.pill.autopay { background: var(--info-color, #0288d1); color: #fff; }
.pill.paid, .pill.received { background: var(--success-color, #2e7d32); color: #fff; }
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
  get _bills() { return this._config && this._config.mode === "bills"; }
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

  // Where to check the bill and where the password is kept. Never the password itself.
  _login(item, label) {
    const url = String(item.login_url || "").trim();
    const web = /^https?:\/\/./i.test(url);  // never a javascript: or other link
    if (!web && !item.login_note) { return null; }
    const box = document.createElement("div");
    box.className = "login";
    if (web) {
      const a = document.createElement("a");
      a.textContent = `${label || this._t.login} ↗`;
      a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
      box.append(a);
    }
    if (item.login_note) {
      const note = document.createElement("span");
      note.textContent = `🔑 ${item.login_note}`;
      box.append(note);
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

    if (this._bills) { this._renderBills(card); return; }

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
        const login = this._login(item);
        if (login) { text.append(login); }
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

HomekeeperCard.prototype._money = function (amount) {
  return typeof amount === "number"
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount) : "";
};

HomekeeperCard.prototype._date = function (iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) { return ""; }
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));  // a calendar day, no time zone
  const locale = this._lang === "ar" ? "ar-u-nu-latn" : "en-US";
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }).format(d);
};

// One row per biller: BillBot's latest bill (or rent payment), with a Pay / Log in link
// and Mark paid while Homekeeper has the bill open.
HomekeeperCard.prototype._renderBills = function (card) {
  const t = this._t;
  const rows = (this._data.bills || []).filter((b) => !this._module || b.module === this._module);
  const open = rows.filter((b) => b.kind === "bill" && ["due", "overdue", "autopay"].includes(b.status));
  const late = rows.filter((b) => b.status === "overdue").length;

  const header = document.createElement("header");
  const h = document.createElement("h2");
  h.textContent = this._config.title || t.bills;
  const badge = document.createElement("span");
  badge.className = "badge" + (late ? " bad" : "");
  badge.textContent = late ? `${late} ${t.st.overdue}` : (open.length ? `${open.length}` : "✓");
  header.append(h, badge);
  card.append(header);
  const sum = open.filter((b) => b.status !== "autopay" && typeof b.amount === "number")
    .reduce((n, b) => n + b.amount, 0);
  if (sum > 0) {
    const total = document.createElement("div");
    total.className = "total"; total.textContent = t.total_due(this._money(sum));
    card.append(total);
  }
  if (!rows.length) {
    const e = document.createElement("div");
    e.className = "empty"; e.textContent = t.no_billers;
    card.append(e);
    return;
  }

  const other = this._lang === "ar" ? "en" : "ar";
  const people = Object.fromEntries((this._data.people || []).map((p) => [p.id, p.name]));
  const box = document.createElement("div");
  box.className = "list";
  rows.forEach((b) => {
    const row = document.createElement("div");
    row.className = `bill ${b.status}`;
    const icon = document.createElement("ha-icon");
    icon.setAttribute("icon", b.icon || (b.kind === "income" ? "mdi:cash-plus" : "mdi:receipt-text"));
    const text = document.createElement("div");
    const title = document.createElement("div");
    title.className = "title";
    const names = { en: b.name, ar: b.name_ar };
    title.textContent = names[this._lang] || b.name;
    text.append(title);
    if (names[other] && names[other] !== title.textContent) {
      const sub = document.createElement("div");
      sub.className = "sub"; sub.textContent = names[other];
      text.append(sub);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const pill = document.createElement("span");
    pill.className = `pill ${b.status}`;
    pill.textContent = b.kind === "income" && b.status === "none" ? t.st.none_income : t.st[b.status];
    meta.append(pill);
    const bits = [];
    if (b.amount !== null && b.amount !== undefined) { bits.push(this._money(b.amount)); }
    if (b.date) {
      if (b.kind === "income") { bits.push(t.received_on(this._date(b.date))); }
      else if (["due", "overdue", "autopay"].includes(b.status) && typeof b.days === "number") {
        const when = this._when({ state: b.status, days: b.days });
        const span = document.createElement("span");
        span.textContent = `${this._date(b.date)} · ${when}`;
        if (b.days < 0) { span.className = "late"; }
        bits.push(span);
      } else { bits.push(t.due_on(this._date(b.date))); }
    }
    const owners = (b.owners || []).map((o) => people[o] || o).join(", ");
    if (owners && ["due", "overdue"].includes(b.status)) { bits.push(owners); }
    bits.forEach((bit) => {
      meta.append(document.createTextNode(meta.childNodes.length > 1 ? " · " : ""));
      meta.append(bit);
    });
    text.append(meta);
    const payable = b.kind === "bill" && ["due", "overdue", "autopay"].includes(b.status);
    const login = this._login(b, payable ? t.pay : t.login);
    if (login) { text.append(login); }
    const actions = document.createElement("div");
    actions.className = "actions";
    if (b.duty_id) {
      const item = { duty_id: b.duty_id };
      const done = document.createElement("button");
      done.className = "act" + (this._confirming === b.duty_id ? " confirming" : "");
      done.textContent = this._confirming === b.duty_id ? t.confirm : t.mark_paid;
      done.addEventListener("click", () => this._onDone(item));
      actions.append(done);
    }
    row.append(icon, text, actions);
    box.append(row);
  });
  card.append(box);
  if (this._error) {
    const e = document.createElement("div");
    e.className = "err"; e.setAttribute("role", "alert"); e.textContent = t[this._error] || t.failed;
    card.append(e);
  }
};

if (!customElements.get("homekeeper-card")) {
  customElements.define("homekeeper-card", HomekeeperCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "homekeeper-card")) {
  window.customCards.push({
    type: "homekeeper-card",
    name: "Homekeeper",
    description: "What needs doing at home, with one-tap Done. Includes a big-button wall-panel mode and a bills table.",
  });
}
