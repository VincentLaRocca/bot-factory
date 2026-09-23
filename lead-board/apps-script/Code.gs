const SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE";
const SHEET_NAME = "LiveQueue";
const BID_SHEET_NAME = "BidCalculator";
const SMS_INTAKE_TOKEN = "";
const HEADERS = [
  "lead_id", "timestamp", "listener_channel", "source_medium", "source_contact",
  "origin", "destination", "cargo_summary", "payout_offered", "mileage_est",
  "rate_per_mile", "urgency_level", "window_deadline", "triage_status", "updated_at"
];
const LISTENER_CHANNELS = ["Trade Distress", "Commercial / B2B", "Open Boards", "Local Community", "General Intake"];
const SOURCE_MEDIUMS = ["SMS", "Email", "Direct Form", "Board Scraping", "Webhook"];
const URGENCY = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const STATUSES = ["NEW", "WATCH", "BID_PREPARED", "ACCEPTED", "DISMISSED"];

function normalize_(value, allowed, fallback) {
  const normalized = String(value || "").trim().toLowerCase();
  const match = allowed.find(item => item.toLowerCase() === normalized);
  return match || fallback;
}

function getSheet_() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = spreadsheet.insertSheet(SHEET_NAME);
  const firstRow = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  if (firstRow.every(value => String(value || "").trim() === "")) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function getBidSheet_() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = spreadsheet.getSheetByName(BID_SHEET_NAME);
  if (!sheet) sheet = spreadsheet.insertSheet(BID_SHEET_NAME);
  const headers = ["lead_id", "origin", "destination", "cargo_summary", "payout_offered",
    "mileage_est", "rate_per_mile", "prepared_at", "proposed_bid"];
  const firstRow = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  if (firstRow.every(value => String(value || "").trim() === "")) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function round2(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function nowIso_() {
  return new Date().toISOString();
}

function makeLeadId_() {
  const stamp = Utilities.formatDate(new Date(), "America/New_York", "yyyyMMdd-HHmmss");
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let suffix = "";
  for (let i = 0; i < 4; i++) suffix += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  return "LD-" + stamp + "-" + suffix;
}

function findRowByLeadId_(sheet, leadId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return 0;
  const values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(leadId)) return i + 2;
  }
  return 0;
}

function response_(data, callback) {
  const body = JSON.stringify(data);
  if (callback) return ContentService.createTextOutput(callback + "(" + body + ")")
    .setMimeType(ContentService.MimeType.JAVASCRIPT);
  return ContentService.createTextOutput(body).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    if (e && e.parameter && e.parameter.Body !== undefined && e.parameter.From !== undefined) {
      return handleSms_(e);
    }
    const contents = e && e.postData && e.postData.contents;
    const encodedPayload = e && e.parameter && e.parameter.payload;
    const trimmedContents = String(contents || "").trim();
    const data = JSON.parse(trimmedContents.startsWith("{") ? trimmedContents :
      (encodedPayload || "{}"));
    const action = String(data.action || "intake").toUpperCase();
    if (action === "INTAKE") {
      const row = appendLead_(data);
      return response_({status: "SUCCESS", lead_id: row[0], row: row});
    }
    if (action === "TRIAGE") {
      const sheet = getSheet_();
      const leadId = data.lead_id;
      const triageAction = String(data.triage_action || "").toUpperCase();
      const actions = {ACCEPT: "ACCEPTED", PREPARE_BID: "BID_PREPARED", DISMISS: "DISMISSED",
        WATCH: "WATCH", RESET: "NEW"};
      const rowNumber = leadId && findRowByLeadId_(sheet, leadId);
      if (!rowNumber) return response_({status: "ERROR", message: "lead not found"});
      if (!actions[triageAction]) return response_({status: "ERROR", message: "unknown triage action"});
      const statusColumn = HEADERS.indexOf("triage_status") + 1;
      const updatedColumn = HEADERS.indexOf("updated_at") + 1;
      const values = sheet.getRange(rowNumber, 1, 1, HEADERS.length).getValues()[0];
      const updatedAt = nowIso_();
      sheet.getRange(rowNumber, statusColumn).setValue(actions[triageAction]);
      sheet.getRange(rowNumber, updatedColumn).setValue(updatedAt);
      if (triageAction === "PREPARE_BID") {
        getBidSheet_().appendRow([values[0], values[5], values[6], values[7], values[8],
          values[9], values[10], nowIso_(), ""]);
      }
      const lead = Object.fromEntries(HEADERS.map((header, index) => [header, values[index]]));
      lead.triage_status = actions[triageAction];
      lead.updated_at = updatedAt;
      if (triageAction === "ACCEPT") onAccept_(lead);
      if (triageAction === "DISMISS") onDismiss_(lead);
      return response_({status: "SUCCESS", lead_id: leadId, triage_status: actions[triageAction]});
    }
    return response_({status: "ERROR", message: "unknown action"});
  } catch (error) {
    return response_({status: "ERROR", message: String(error.message || error)});
  }
}

function appendLead_(fields) {
  const payout = parseFloat(fields.payout_offered) || 0;
  const mileage = parseFloat(fields.mileage_est) || 0;
  const timestamp = nowIso_();
  const row = [
    fields.lead_id || makeLeadId_(), timestamp,
    normalize_(fields.listener_channel, LISTENER_CHANNELS, "General Intake"),
    normalize_(fields.source_medium, SOURCE_MEDIUMS, "Webhook"),
    fields.source_contact || "", fields.origin || "", fields.destination || "",
    fields.cargo_summary || "", payout, mileage, mileage > 0 ? round2(payout / mileage) : 0,
    normalize_(fields.urgency_level, URGENCY, "MEDIUM"), fields.window_deadline || "",
    "NEW", timestamp
  ];
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    getSheet_().appendRow(row);
  } finally {
    lock.releaseLock();
  }
  return row;
}

function handleSms_(e) {
  if (SMS_INTAKE_TOKEN && e.parameter.token !== SMS_INTAKE_TOKEN) {
    console.log("Unauthorized SMS intake");
    return twiml_("Unauthorized");
  }
  const lead = parseSmsBody_(e.parameter.Body);
  const row = appendLead_({
    listener_channel: lead.listener_channel || "Trade Distress",
    source_medium: "SMS",
    source_contact: e.parameter.From + (lead.contact ? " · " + lead.contact : ""),
    origin: lead.origin,
    destination: lead.destination,
    cargo_summary: lead.cargo_summary || e.parameter.Body,
    payout_offered: lead.payout_offered,
    mileage_est: lead.mileage_est,
    urgency_level: lead.urgency_level,
    window_deadline: lead.window_deadline
  });
  const message = "Logged " + row[0] + ": " + row[5] + " → " + row[6] +
    " $" + row[8] + " (" + row[9] + " mi)";
  return twiml_(message);
}

function twiml_(message) {
  const body = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>' +
    xmlEscape_(message) + "</Message></Response>";
  return ContentService.createTextOutput(body).setMimeType(ContentService.MimeType.XML);
}

function xmlEscape_(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

function parseSmsBody_(text) {
  const raw = String(text || "").trim();
  const result = {
    origin: "", destination: "", cargo_summary: "", payout_offered: 0,
    mileage_est: 0, urgency_level: "", window_deadline: "",
    listener_channel: "", contact: ""
  };
  const aliases = {
    from: "origin", origin: "origin", pickup: "origin",
    to: "destination", dest: "destination", destination: "destination", dropoff: "destination",
    cargo: "cargo_summary", load: "cargo_summary", items: "cargo_summary",
    pay: "payout_offered", payout: "payout_offered", price: "payout_offered", rate: "payout_offered",
    miles: "mileage_est", mi: "mileage_est", mileage: "mileage_est",
    urgency: "urgency_level", priority: "urgency_level",
    by: "window_deadline", deadline: "window_deadline", window: "window_deadline",
    channel: "listener_channel", contact: "contact", name: "contact"
  };
  const structured = {};
  const pieces = raw.split(/[\n;]+/);
  pieces.forEach(piece => {
    const match = piece.match(/^\s*([^:=]+?)\s*[:=]\s*(.*?)\s*$/);
    if (!match) return;
    const key = match[1].toLowerCase().replace(/[\s_]/g, "");
    if (aliases[key]) structured[aliases[key]] = match[2].trim();
  });
  if (Object.keys(structured).length >= 2) {
    Object.keys(structured).forEach(key => {
      result[key] = structured[key];
    });
    result.origin = stripRoutePunctuation_(result.origin);
    result.destination = stripRoutePunctuation_(result.destination);
    result.payout_offered = numberFromText_(result.payout_offered);
    result.mileage_est = numberFromText_(result.mileage_est);
    if (result.urgency_level) result.urgency_level = urgencyFromText_(result.urgency_level);
    if (result.window_deadline) result.window_deadline = result.window_deadline.trim();
    return result;
  }

  const payoutMatch = raw.match(/\$\s?(\d+(?:\.\d+)?)/);
  const milesMatch = raw.match(/(\d+(?:\.\d+)?)\s?(?:mi|miles?)\b/i);
  const deadlineMatch = raw.match(/\bby\s+(\d{1,2}(?::\d{2})?\s?(?:am|pm)?|eod|noon|tonight|today|tomorrow[^,;$]*)/i);
  const routePatterns = [
    /(?:pickup|from|pu)\s+(.+?)\s+(?:to|->|→)\s+(.+?)(?=\s*[:;,]|\s+\$|\s+\d+(?:\.\d+)?\s?mi|\s+by\b|$)/i,
    /^(.+?)\s+(?:to|->|→)\s+(.+?)(?=[:;,]|\s+\$|\s+\d|\s+by\b|$)/i
  ];
  let routeMatch = null;
  for (let i = 0; i < routePatterns.length && !routeMatch; i++) {
    routeMatch = raw.match(routePatterns[i]);
  }
  if (routeMatch) {
    result.origin = stripRoutePunctuation_(routeMatch[1]);
    result.destination = stripRoutePunctuation_(routeMatch[2]);
  }
  result.payout_offered = payoutMatch ? parseFloat(payoutMatch[1]) : 0;
  result.mileage_est = milesMatch ? parseFloat(milesMatch[1]) : 0;
  result.window_deadline = deadlineMatch ? "By " + deadlineMatch[1].trim() : "";
  result.urgency_level = urgencyFromText_(raw);

  let cargo = routeMatch ? raw.slice(routeMatch.index + routeMatch[0].length) : raw;
  if (cargo.trim().charAt(0) === ":") cargo = cargo.trim().slice(1);
  if (payoutMatch) cargo = cargo.replace(payoutMatch[0], "");
  if (milesMatch) cargo = cargo.replace(milesMatch[0], "");
  if (deadlineMatch) cargo = cargo.replace(deadlineMatch[0], "");
  cargo = cargo.replace(/\b(?:URGENT|ASAP|CRITICAL|STAT|RUSH|HIGH|HOT|LOW|FLEX|FLEXIBLE|WHENEVER)\b/ig, "");
  result.cargo_summary = cargo.replace(/\s+/g, " ").replace(/^[\s:;,]+|[\s:;,]+$/g, "").trim() || raw;
  return result;
}

function numberFromText_(value) {
  const match = String(value || "").match(/\d+(?:\.\d+)?/);
  return match ? parseFloat(match[0]) : 0;
}

function urgencyFromText_(text) {
  const value = String(text || "").toUpperCase();
  if (/\b(?:URGENT|ASAP|CRITICAL|STAT)\b/.test(value)) return "CRITICAL";
  if (/\b(?:RUSH|HIGH|HOT)\b/.test(value)) return "HIGH";
  if (/\b(?:LOW|FLEX|FLEXIBLE|WHENEVER)\b/.test(value)) return "LOW";
  return "MEDIUM";
}

function stripRoutePunctuation_(value) {
  return String(value || "").trim().replace(/[.,;:]+$/, "").trim();
}

function doGet(e) {
  try {
    const sheet = getSheet_();
    const values = sheet.getLastRow() < 2 ? [] : sheet.getRange(2, 1,
      sheet.getLastRow() - 1, HEADERS.length).getValues();
    const requested = String((e && e.parameter && e.parameter.status) || "")
      .split(",").map(value => value.trim().toUpperCase()).filter(value => value && value !== "ALL");
    const statuses = requested.flatMap(status =>
      status === "ACTIVE" ? ["NEW", "WATCH", "BID_PREPARED"] : [status]);
    const limitValue = parseInt((e && e.parameter && e.parameter.limit) || "200", 10);
    const limit = Number.isFinite(limitValue) && limitValue > 0 ? limitValue : 200;
    const leads = values.map(row => Object.fromEntries(HEADERS.map((header, index) => [header, row[index]])))
      .filter(lead => !statuses.length || statuses.includes(String(lead.triage_status).toUpperCase()))
      .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
      .slice(0, limit);
    return response_({status: "SUCCESS", generated_at: nowIso_(), count: leads.length, leads: leads},
      e && e.parameter && e.parameter.callback);
  } catch (error) {
    return response_({status: "ERROR", message: String(error.message || error)});
  }
}

function notifyDispatch_(lead) {
  console.log("Dispatch notification stub", lead.lead_id, lead.triage_status);
  // MailApp.sendEmail("dispatch@example.com", "Lead accepted", JSON.stringify(lead));
}

function onAccept_(lead) {
  notifyDispatch_(lead);
}

function onDismiss_(lead) {
  notifyDispatch_(lead);
}
