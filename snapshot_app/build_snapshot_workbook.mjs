import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath, verifyDir] = process.argv.slice(2);
if (!inputPath || !outputPath) throw new Error("Usage: build_snapshot_workbook.mjs INPUT.json OUTPUT.xlsx [VERIFY_DIR]");

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();

function excelColumn(index) {
  let output = "";
  for (let number = index + 1; number; number = Math.floor((number - 1) / 26)) {
    output = String.fromCharCode(65 + ((number - 1) % 26)) + output;
  }
  return output;
}

function addSheet(name, dataset, color, tableName) {
  const sheet = workbook.worksheets.add(name);
  const columns = dataset.columns;
  const rows = dataset.rows;
  const lastColumn = excelColumn(columns.length - 1);
  const lastRow = rows.length + 3;
  sheet.showGridLines = false;
  sheet.tabColor = color;
  sheet.getRange("A1").values = [[`${name} — ${payload.metadata.snapshot_et}`]];
  sheet.getRange(`A1:${lastColumn}1`).format = {
    font: { name: "Arial", size: 14, bold: true, color: "#102635" },
    rowHeight: 26,
    verticalAlignment: "center",
  };
  sheet.getRange("A2").values = [[`Created ${payload.metadata.created_at_utc}`]];
  sheet.getRange(`A2:${lastColumn}2`).format = {
    font: { name: "Arial", size: 9, italic: true, color: "#64747D" },
    rowHeight: 20,
  };
  sheet.getRange(`A3:${lastColumn}3`).values = [columns];
  const identifierColumns = new Set(["series_ticker", "ticker", "event_ticker", "event_id", "event_slug", "market_id", "condition_id", "market_slug", "token_id"]);
  columns.forEach((column, index) => {
    if (identifierColumns.has(column)) {
      const letter = excelColumn(index);
      sheet.getRange(`${letter}4:${letter}${lastRow}`).format.numberFormat = "@";
    }
  });
  if (rows.length) sheet.getRange(`A4:${lastColumn}${lastRow}`).values = rows;
  const used = sheet.getRange(`A3:${lastColumn}${lastRow}`);
  used.format.font = { name: "Arial", size: 9, color: "#102635" };
  used.format.verticalAlignment = "center";
  sheet.getRange(`A3:${lastColumn}3`).format = {
    fill: color,
    font: { name: "Arial", size: 9, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    rowHeight: 32,
    borders: { preset: "inside", style: "thin", color: "#FFFFFF" },
  };
  if (rows.length) {
    const table = sheet.tables.add(`A3:${lastColumn}${lastRow}`, true, tableName);
    table.style = "TableStyleMedium2";
  }
  sheet.freezePanes.freezeRows(3);

  columns.forEach((column, index) => {
    const letter = excelColumn(index);
    const range = sheet.getRange(`${letter}4:${letter}${lastRow}`);
    if (["requested_snapshot_utc", "observed_at_utc", "market_open_time", "market_close_time"].includes(column)) {
      range.format.numberFormat = "yyyy-mm-dd hh:mm";
    } else if (["yes_bid", "yes_ask", "midpoint", "last_trade_price", "price"].includes(column)) {
      range.format.numberFormat = "0.0000";
    } else if (["observation_lag_seconds", "minute_volume", "open_interest"].includes(column)) {
      range.format.numberFormat = "#,##0";
    }
  });

  used.format.autofitColumns();
  used.format.autofitRows();
  const widths = {
    requested_snapshot_et: 19, requested_snapshot_timezone: 12, requested_snapshot_utc: 22,
    observed_at_utc: 22, observation_lag_seconds: 15, series_ticker: 20, series_title: 34,
    ticker: 30, event_ticker: 27, market_title: 42, outcome: 28, data_status: 23,
    event_id: 12, event_slug: 46, event_title: 42, market_id: 14, condition_id: 28,
    market_slug: 46, market_question: 58, token_id: 28, market_open_time: 22, market_close_time: 22,
  };
  columns.forEach((column, index) => {
    if (widths[column]) sheet.getRange(`${excelColumn(index)}:${excelColumn(index)}`).format.columnWidth = widths[column];
  });
  if (rows.length) {
    const statusIndex = columns.indexOf("data_status");
    if (statusIndex >= 0) {
      const statusRange = sheet.getRange(`${excelColumn(statusIndex)}4:${excelColumn(statusIndex)}${lastRow}`);
      statusRange.conditionalFormats.add("notContainsText", {
        text: "ok", format: { fill: "#FCE8E6", font: { color: "#A12B2B", bold: true } },
      });
    }
  }
  return { sheet, lastColumn, lastRow };
}

const kalshi = addSheet("Kalshi series", payload.kalshi, "#08783F", "KalshiSnapshot");
const polymarket = addSheet("Polymarket series", payload.polymarket, "#4C54E8", "PolymarketSnapshot");
workbook.recalculate();

if (verifyDir) {
  await fs.mkdir(verifyDir, { recursive: true });
  for (const item of [kalshi, polymarket]) {
    const preview = await workbook.render({
      sheetName: item.sheet.name,
      range: `A1:${item.lastColumn}${Math.min(item.lastRow, 18)}`,
      scale: 1,
      format: "png",
    });
    await fs.writeFile(`${verifyDir}/${item.sheet.name.replaceAll(" ", "_")}.png`, new Uint8Array(await preview.arrayBuffer()));
  }
  const inspection = await workbook.inspect({ kind: "sheet,table", maxChars: 5000, tableMaxRows: 5, tableMaxCols: 8 });
  await fs.writeFile(`${verifyDir}/inspection.ndjson`, inspection.ndjson, "utf8");
  const errors = await workbook.inspect({
    kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 }, summary: "formula error scan",
  });
  await fs.writeFile(`${verifyDir}/formula_errors.ndjson`, errors.ndjson, "utf8");
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
