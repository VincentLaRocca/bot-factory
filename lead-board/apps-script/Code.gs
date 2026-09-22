const SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE";
const API_KEY_PROPERTY = "LEAD_BOARD_API_KEY";
const MAX_PAYLOAD_BYTES = 20000;
const MAX_TEXT_LENGTH = 500;
const SHEET_NAME = "LiveQueue";
const BID_SHEET_NAME = "BidCalculator";
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

function text_(value, maxLength) {
  const text = String(value || "").trim().slice(0, maxLength || MAX_TEXT_LENGTH);
  return /^[=+\-@]/.test(text) ? "'" + text : text;
}

function apiKey_() {
  return PropertiesService.getScriptProperties().getProperty(API_KEY_PROPERTY) || "";
}

function authorized_(e, data) {
  const expected = apiKey_();
  const supplied = String((data && data.api_key) || (e && e.parameter && e.parameter.api_key) || "");
  return expected && supplied && supplied === expected;
}

function validCallback_(callback) {
  return /^[A-Za-z_$][0-9A-Za-z_$]*(\.[A-Za-z_$][0-9A-Za-z_$]*)*$/.test(callback);
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
  if (callback) {
    if (!validCallback_(callback)) return ContentService.createTextOutput(JSON.stringify({
      status: "ERROR", message: "invalid callback"
    })).setMimeType(ContentService.MimeType.JSON);
    return ContentService.createTextOutput(callback + "(" + body + ")")
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(body).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const contents = e && e.postData && e.postData.contents;
    const encodedPayload = e && e.parameter && e.parameter.payload;
    const rawPayload = contents || encodedPayload || "{}";
    if (rawPayload.length > MAX_PAYLOAD_BYTES) return response_({status: "ERROR", message: "payload too large"});
    const data = JSON.parse(rawPayload);
    if (!authorized_(e, data)) return response_({status: "ERROR", message: "unauthorized"});
    const action = String(data.action || "intake").toUpperCase();
    const sheet = getSheet_();
    if (action === "INTAKE") {
      const payout = parseFloat(data.payout_offered) || 0;
      const mileage = parseFloat(data.mileage_est) || 0;
      const timestamp = nowIso_();
      const requestedId = text_(data.lead_id, 100);
      const row = [
        requestedId || makeLeadId_(), timestamp,
        normalize_(data.listener_channel, LISTENER_CHANNELS, "General Intake"),
        normalize_(data.source_medium, SOURCE_MEDIUMS, "Webhook"),
        text_(data.source_contact), text_(data.origin), text_(data.destination),
        text_(data.cargo_summary), payout, mileage, mileage > 0 ? round2(payout / mileage) : 0,
        normalize_(data.urgency_level, URGENCY, "MEDIUM"), text_(data.window_deadline),
        "NEW", timestamp
      ];
      const lock = LockService.getScriptLock();
      lock.waitLock(30000);
      try {
        const existingRow = findRowByLeadId_(sheet, row[0]);
        if (existingRow) {
          if (requestedId) return response_({status: "SUCCESS", lead_id: row[0], duplicate: true});
          return response_({status: "ERROR", message: "generated duplicate lead ID"});
        }
        sheet.appendRow(row);
      } finally {
        lock.releaseLock();
      }
      return response_({status: "SUCCESS", lead_id: row[0], row: row});
    }
    if (action === "TRIAGE") {
      const leadId = text_(data.lead_id, 100);
      const triageAction = String(data.triage_action || "").toUpperCase();
      const actions = {ACCEPT: "ACCEPTED", PREPARE_BID: "BID_PREPARED", DISMISS: "DISMISSED",
        WATCH: "WATCH", RESET: "NEW"};
      if (!actions[triageAction]) return response_({status: "ERROR", message: "unknown triage action"});
      const lock = LockService.getScriptLock();
      lock.waitLock(30000);
      let lead;
      let updatedAt;
      try {
        const rowNumber = leadId && findRowByLeadId_(sheet, leadId);
        if (!rowNumber) return response_({status: "ERROR", message: "lead not found"});
        const statusColumn = HEADERS.indexOf("triage_status") + 1;
        const updatedColumn = HEADERS.indexOf("updated_at") + 1;
        const values = sheet.getRange(rowNumber, 1, 1, HEADERS.length).getValues()[0];
        if (data.expected_updated_at && String(values[updatedColumn - 1]) !== String(data.expected_updated_at)) {
          return response_({status: "CONFLICT", message: "lead changed; refresh and try again"});
        }
        updatedAt = nowIso_();
        if (triageAction === "PREPARE_BID") {
          const bidSheet = getBidSheet_();
          if (!findRowByLeadId_(bidSheet, leadId)) {
            bidSheet.appendRow([values[0], values[5], values[6], values[7], values[8],
              values[9], values[10], updatedAt, ""]);
          }
        }
        sheet.getRange(rowNumber, statusColumn).setValue(actions[triageAction]);
        sheet.getRange(rowNumber, updatedColumn).setValue(updatedAt);
        lead = Object.fromEntries(HEADERS.map((header, index) => [header, values[index]]));
        lead.triage_status = actions[triageAction];
        lead.updated_at = updatedAt;
      } finally {
        lock.releaseLock();
      }
      if (triageAction === "ACCEPT") onAccept_(lead);
      if (triageAction === "DISMISS") onDismiss_(lead);
      return response_({status: "SUCCESS", lead_id: leadId, triage_status: lead.triage_status,
        updated_at: updatedAt});
    }
    return response_({status: "ERROR", message: "unknown action"});
  } catch (error) {
    return response_({status: "ERROR", message: String(error.message || error)});
  }
}

function doGet(e) {
  try {
    if (!authorized_(e)) return response_({status: "ERROR", message: "unauthorized"},
      e && e.parameter && e.parameter.callback);
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
