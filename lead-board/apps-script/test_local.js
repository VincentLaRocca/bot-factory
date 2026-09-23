const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class Range {
  constructor(sheet, row, column, rowCount, columnCount) {
    this.sheet = sheet;
    this.row = row;
    this.column = column;
    this.rowCount = rowCount;
    this.columnCount = columnCount;
  }

  getValues() {
    return Array.from({length: this.rowCount}, (_, rowOffset) =>
      Array.from({length: this.columnCount}, (_, columnOffset) =>
        this.sheet.rows[this.row + rowOffset - 1]?.[this.column + columnOffset - 1] ?? ""));
  }

  setValues(values) {
    values.forEach((valuesRow, rowOffset) => {
      const targetRow = this.row + rowOffset - 1;
      while (this.sheet.rows.length <= targetRow) this.sheet.rows.push([]);
      valuesRow.forEach((value, columnOffset) => {
        this.sheet.rows[targetRow][this.column + columnOffset - 1] = value;
      });
    });
    return this;
  }

  setValue(value) {
    return this.setValues([[value]]);
  }

  setFontWeight() {
    return this;
  }
}

class Sheet {
  constructor(name) {
    this.name = name;
    this.rows = [];
  }

  getName() {
    return this.name;
  }

  getRange(row, column, rowCount = 1, columnCount = 1) {
    return new Range(this, row, column, rowCount, columnCount);
  }

  getLastRow() {
    return this.rows.length;
  }

  appendRow(row) {
    this.rows.push(row.slice());
  }

  setFrozenRows() {}
}

class Spreadsheet {
  constructor() {
    this.sheets = new Map();
  }

  getSheetByName(name) {
    return this.sheets.get(name);
  }

  insertSheet(name) {
    const sheet = new Sheet(name);
    this.sheets.set(name, sheet);
    return sheet;
  }
}

const source = fs.readFileSync(__dirname + "/Code.gs", "utf8");

function loadContext(code) {
  const spreadsheet = new Spreadsheet();
  const cache = new Map();
  const properties = new Map();
  const scriptCache = {
    get: key => cache.get(key) || null,
    put: (key, value) => cache.set(key, value),
    reset: () => cache.clear()
  };
  const scriptProperties = {
    getProperty: key => properties.get(key) || null,
    setProperty: (key, value) => properties.set(key, value),
    deleteProperty: key => properties.delete(key)
  };
  const context = {
    SpreadsheetApp: {openById: () => spreadsheet},
    ContentService: {
      MimeType: {JSON: "application/json", XML: "text/xml"},
      createTextOutput: content => ({
        content,
        mimeType: null,
        setMimeType(mimeType) {
          this.mimeType = mimeType;
          return this;
        },
        getContent() {
          return this.content;
        }
      })
    },
    MimeType: {JAVASCRIPT: "application/javascript"},
    LockService: {
      getScriptLock: () => ({
        waitLock() {},
        releaseLock() {}
      })
    },
    CacheService: {
      getScriptCache: () => scriptCache
    },
    PropertiesService: {
      getScriptProperties: () => scriptProperties
    },
    Utilities: {
      formatDate: date => {
        const pad = value => String(value).padStart(2, "0");
        return `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}-${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}`;
      }
    },
    console
  };
  vm.runInNewContext(code, context);
  return {context, spreadsheet, cache: scriptCache, properties: scriptProperties};
}

const loaded = loadContext(source);
const context = loaded.context;
const spreadsheet = loaded.spreadsheet;

function post(payload) {
  const output = context.doPost({parameter: {}, postData: {contents: JSON.stringify(payload)}});
  return JSON.parse(output.getContent());
}

function postSms(body, from = "+18045550123", extra = {}) {
  const output = context.doPost({
    parameter: Object.assign({From: from, Body: body}, extra),
    postData: {contents: "From=" + encodeURIComponent(from) + "&Body=" + encodeURIComponent(body)}
  });
  return output.getContent();
}

const intake = post({
  listener_channel: "trade distress",
  source_medium: "sms",
  source_contact: "Mike · field lead (Baker Bros HVAC)",
  origin: "Scott's Addition · Richmond",
  destination: "Carrier Enterprise · Midlothian",
  cargo_summary: "2 TXV valves + recovery tank",
  payout_offered: "75",
  mileage_est: "18",
  urgency_level: "critical",
  window_deadline: "Pickup by 12:40 PM"
});
assert.strictEqual(intake.status, "SUCCESS");
assert.strictEqual(intake.row.length, 15);
assert.strictEqual(intake.row[10], 4.17);

const board = JSON.parse(context.doGet({parameter: {}}).getContent());
assert.strictEqual(board.status, "SUCCESS");
assert.strictEqual(board.count, 1);
assert.strictEqual(board.leads[0].lead_id, intake.lead_id);
assert.strictEqual(board.leads[0].triage_status, "NEW");

const accepted = post({action: "triage", lead_id: intake.lead_id, triage_action: "ACCEPT"});
assert.deepStrictEqual(accepted, {
  status: "SUCCESS",
  lead_id: intake.lead_id,
  triage_status: "ACCEPTED"
});

const missing = post({action: "triage", lead_id: "LD-missing", triage_action: "ACCEPT"});
assert.deepStrictEqual(missing, {status: "ERROR", message: "lead not found"});

const liveQueue = spreadsheet.getSheetByName("LiveQueue");
const rowsBeforeInvalidJson = liveQueue.rows.length;
const invalidJson = context.doPost({parameter: {}, postData: {contents: "hello"}});
assert.strictEqual(JSON.parse(invalidJson.getContent()).status, "ERROR");
assert.strictEqual(liveQueue.rows.length, rowsBeforeInvalidJson);

const freeText = "PICKUP Carrier Enterprise Midlothian TO Scott's Addition Richmond: " +
  "2 TXV valves + recovery tank $75 18mi by 12:40pm URGENT";
const freeTextResponse = postSms(freeText);
assert(freeTextResponse.includes("<Response><Message>Logged LD-"));
const freeTextRow = liveQueue.rows[liveQueue.rows.length - 1];
assert.strictEqual(freeTextRow[2], "Trade Distress");
assert.strictEqual(freeTextRow[3], "SMS");
assert(freeTextRow[4].startsWith("+18045550123"));
assert.strictEqual(freeTextRow[5], "Carrier Enterprise Midlothian");
assert.strictEqual(freeTextRow[6], "Scott's Addition Richmond");
assert.strictEqual(freeTextRow[8], 75);
assert.strictEqual(freeTextRow[9], 18);
assert.strictEqual(freeTextRow[10], 4.17);
assert.strictEqual(freeTextRow[11], "CRITICAL");
assert.strictEqual(freeTextRow[12], "By 12:40pm");
assert(freeTextRow[7].includes("TXV"));

const rowsBeforeRetry = liveQueue.rows.length;
const retryFirst = postSms(freeText, "+18045550123", {MessageSid: "SM123"});
const retrySecond = postSms(freeText, "+18045550123", {MessageSid: "SM123"});
assert.strictEqual(liveQueue.rows.length, rowsBeforeRetry + 1);
const retryFirstLeadId = retryFirst.match(/<Message>Logged ([^:]+):/)[1];
const retrySecondLeadId = retrySecond.match(/<Message>Logged ([^:]+):/)[1];
assert.strictEqual(retryFirstLeadId, retrySecondLeadId);

const rowsBeforeDurableRetry = liveQueue.rows.length;
const durableFirst = postSms(freeText, "+18045550123", {MessageSid: "SM999"});
loaded.cache.reset();
const durableSecond = postSms(freeText, "+18045550123", {MessageSid: "SM999"});
assert.strictEqual(liveQueue.rows.length, rowsBeforeDurableRetry + 1);
const durableFirstLeadId = durableFirst.match(/<Message>Logged ([^:]+):/)[1];
const durableSecondLeadId = durableSecond.match(/<Message>Logged ([^:]+):/)[1];
assert.strictEqual(durableFirstLeadId, durableSecondLeadId);

const rowsBeforeNoSid = liveQueue.rows.length;
postSms("no sid still appends");
assert.strictEqual(liveQueue.rows.length, rowsBeforeNoSid + 1);

postSms("from: Ferguson Chester; to: Jobsite Hopewell; cargo: 6 boxes PEX; " +
  "pay: 55; miles: 21; urgency: low; by: EOD");
const structuredRow = liveQueue.rows[liveQueue.rows.length - 1];
assert.strictEqual(structuredRow[5], "Ferguson Chester");
assert.strictEqual(structuredRow[6], "Jobsite Hopewell");
assert.strictEqual(structuredRow[7], "6 boxes PEX");
assert.strictEqual(structuredRow[8], 55);
assert.strictEqual(structuredRow[9], 21);
assert.strictEqual(structuredRow[11], "LOW");
assert.strictEqual(structuredRow[12], "EOD");

postSms("hey call me");
const garbageRow = liveQueue.rows[liveQueue.rows.length - 1];
assert.strictEqual(garbageRow[5], "");
assert.strictEqual(garbageRow[7], "hey call me");
assert.strictEqual(garbageRow[8], 0);
assert.strictEqual(garbageRow[10], 0);

const capLoaded = loadContext(source);
for (let i = 0; i < 205; i++) capLoaded.context.smsRemember_("CAP" + i, ["CAP" + i]);
const remembered = JSON.parse(capLoaded.properties.getProperty("sms_index"));
assert.strictEqual(remembered.length, 150);
assert.strictEqual(remembered[0], "CAP55");
assert.strictEqual(remembered[149], "CAP204");
assert.strictEqual(capLoaded.properties.getProperty("sms:CAP54"), null);
assert.deepStrictEqual(JSON.parse(capLoaded.properties.getProperty("sms:CAP55")), ["CAP55"]);

const tokenSource = source.replace('const SMS_INTAKE_TOKEN = "";',
  'const SMS_INTAKE_TOKEN = "test-secret";');
const tokenLoaded = loadContext(tokenSource);
const unauthorized = tokenLoaded.context.doPost({
  parameter: {From: "+18045550123", Body: "hey call me", token: "wrong"},
  postData: {contents: ""}
});
assert(unauthorized.getContent().includes("<Message>Unauthorized</Message>"));
assert.strictEqual(tokenLoaded.spreadsheet.getSheetByName("LiveQueue"), undefined);

console.log("PASS intake: 15 columns, computed rate 4.17");
console.log("PASS doGet: returned the intake lead");
console.log("PASS triage ACCEPT: status changed to ACCEPTED");
console.log("PASS unknown lead: returned lead not found");
console.log("PASS non-JSON POST: returned ERROR without appending");
console.log("PASS Twilio free text: route, payout, miles, urgency, deadline, and SMS source");
console.log("PASS Twilio retry dedup: same MessageSid appended one row and reused lead ID");
console.log("PASS Twilio durable retry: reused lead after cache reset");
console.log("PASS Twilio history cap: retained the latest 150 MessageSids and evicted old rows");
console.log("PASS Twilio no MessageSid: appended normally");
console.log("PASS Twilio structured text: parsed labeled fields");
console.log("PASS Twilio garbage text: logged raw cargo with zero numeric fields");
console.log("PASS Twilio token: rejected wrong token without appending");
