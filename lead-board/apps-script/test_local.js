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

const spreadsheet = new Spreadsheet();
const context = {
  SpreadsheetApp: {openById: () => spreadsheet},
  ContentService: {
    MimeType: {JSON: "application/json"},
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
  Utilities: {
    formatDate: date => {
      const pad = value => String(value).padStart(2, "0");
      return `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}-${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}`;
    }
  },
  console
};
vm.runInNewContext(fs.readFileSync(__dirname + "/Code.gs", "utf8"), context);

function post(payload) {
  const output = context.doPost({postData: {contents: JSON.stringify(payload)}});
  return JSON.parse(output.getContent());
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

console.log("PASS intake: 15 columns, computed rate 4.17");
console.log("PASS doGet: returned the intake lead");
console.log("PASS triage ACCEPT: status changed to ACCEPTED");
console.log("PASS unknown lead: returned lead not found");
