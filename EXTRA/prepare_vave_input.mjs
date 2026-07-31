// Create the persistent, user-editable Excel source for VAVE slide generation.
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "../portable-runtime/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const sourcePath = path.resolve(process.argv[2]);
const outputPath = path.resolve(process.argv[3]);
const qaDir = path.resolve(process.argv[4]);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const dataSheet = workbook.worksheets.items.find((sheet) => sheet.name.endsWith(" VAVE Data"));
if (!dataSheet) throw new Error("No worksheet ending in ' VAVE Data' was found.");

const instructions = workbook.worksheets.add("VAVE Slide Instructions");
instructions.showGridLines = false;
instructions.getRange("A1:F1").merge();
instructions.getRange("A1:F1").values = [["VAVE Slide Input"]];
instructions.getRange("A1:F1").format = {
  fill: "#1F4E79",
  font: { bold: true, color: "#FFFFFF", fontSize: 20 },
  verticalAlignment: "center",
};
instructions.getRange("A1:F1").format.rowHeight = 34;
instructions.getRange("A3:F3").merge();
instructions.getRange("A3:F3").values = [["Edit the sheet ending in ‘VAVE Data’, save this workbook, then run Generate VAVE Slides.cmd."]];
instructions.getRange("A3:F3").format = { font: { bold: true, color: "#1F4E79", fontSize: 12 }, wrapText: true };
instructions.getRange("A5:B11").values = [
  ["Field", "How the slide generator uses it"],
  ["Slide Order", "Orders sections in the PowerPoint."],
  ["Slide Title", "Groups rows into a section. New titles create new sections."],
  ["Task Order", "Orders tasks within each section."],
  ["Task Name / Savings / End Date / Status", "Visible slide content."],
  ["Include In Total", "Use 1/blank to include; use 0 to exclude the row and its savings."],
  ["Page / Column / Row On Page", "No manual maintenance needed; pagination is automatic."],
];
instructions.getRange("A5:B5").format = {
  fill: "#4472C4",
  font: { bold: true, color: "#FFFFFF" },
};
instructions.getRange("A6:B11").format = {
  fill: "#F2F5FA",
  font: { color: "#202020" },
  wrapText: true,
  borders: { preset: "inside", style: "thin", color: "#D9E2F3" },
};
instructions.getRange("A13:F13").merge();
instructions.getRange("A13:F13").values = [["Automatic layout: 1–7 rows = single column; 8–14 rows = two columns; more than 14 rows = continuation slides."]];
instructions.getRange("A13:F13").format = { fill: "#FFF2CC", font: { bold: true, color: "#7F6000" }, wrapText: true };
instructions.getRange("A:A").format.columnWidth = 30;
instructions.getRange("B:B").format.columnWidth = 76;
instructions.getRange("C:F").format.columnWidth = 4;
instructions.getRange("A3:F3").format.rowHeight = 36;
instructions.getRange("A6:B11").format.rowHeight = 30;
instructions.getRange("A13:F13").format.rowHeight = 34;
instructions.freezePanes.freezeRows(1);

dataSheet.getRange("N2:N250").dataValidation = {
  rule: { type: "list", values: ["On Track", "Completed", "Not Started", "At Risk", "On Hold"] },
};
dataSheet.getRange("O2:O250").dataValidation = { rule: { type: "list", values: [1, 0] } };

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(qaDir, { recursive: true });
const instructionPng = await workbook.render({ sheetName: instructions.name, range: "A1:F14", scale: 2, format: "png" });
await fs.writeFile(path.join(qaDir, "instructions.png"), new Uint8Array(await instructionPng.arrayBuffer()));
const dataPng = await workbook.render({ sheetName: dataSheet.name, range: "A1:P24", scale: 1, format: "png" });
await fs.writeFile(path.join(qaDir, "vave-data.png"), new Uint8Array(await dataPng.arrayBuffer()));
const inspect = await workbook.inspect({ kind: "sheet,table,formula", maxChars: 12000, tableMaxRows: 25, tableMaxCols: 16 });
await fs.writeFile(path.join(qaDir, "inspect.ndjson"), inspect.ndjson, "utf8");
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
await fs.writeFile(path.join(qaDir, "errors.ndjson"), errors.ndjson, "utf8");
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, dataSheet: dataSheet.name }));
