// Refresh the persistent VAVE Excel handoff from a tracker .vpmt file.
import fs from "node:fs/promises";
import path from "node:path";
import {
  FileBlob,
  SpreadsheetFile,
} from "../portable-runtime/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const HEADERS = [
  "Project", "Slide Order", "Slide Title", "Page", "Column", "Row On Page",
  "Task Order", "Task Name", "Potential $", "Realized $", "Savings",
  "Savings Basis", "End Date", "Status", "Include In Total", "Source Task ID",
];
const ROWS_PER_PAGE = 14;
const ROWS_PER_COLUMN = 7;

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (!argv[index].startsWith("--")) continue;
    args[argv[index].slice(2)] = argv[index + 1];
    index += 1;
  }
  return args;
}

function requiredPath(args, name) {
  if (!args[name]) throw new Error(`Missing required --${name}`);
  return path.resolve(args[name]);
}

function hasManualVaveValue(node) {
  return node?.vave_potential !== null && node?.vave_potential !== undefined
    || node?.vave_realized !== null && node?.vave_realized !== undefined;
}

function isLeafLike(node) {
  return !Array.isArray(node?.children) || node.children.length === 0;
}

function isSectionNode(node) {
  const children = Array.isArray(node?.children) ? node.children : [];
  if (!children.length) return false;
  const namedVaveGroup = /\bvave\b/i.test(String(node?.name || ""));
  return children.some(hasManualVaveValue) || (namedVaveGroup && children.some(isLeafLike));
}

function collectSections(tasks) {
  const sections = [];
  const visit = (node) => {
    const children = Array.isArray(node?.children) ? node.children : [];
    if (isSectionNode(node)) {
      // Once a hierarchy node is a VAVE section, every immediate line is a
      // slide row. This includes newly added lines whose savings are not set yet.
      // A child that is itself a section is a group heading, not a savings line:
      // it gets its own slide, so it must not also appear as a row here.
      const nodes = children.filter((child) => !isSectionNode(child));
      if (nodes.length) sections.push({ title: node.name || "VAVE activities", nodes });
    }
    for (const child of children) visit(child);
  };

  const roots = Array.isArray(tasks) ? tasks : [];
  const rootRows = roots.filter((root) => hasManualVaveValue(root) && !isSectionNode(root));
  if (rootRows.length) sections.push({ title: "VAVE activities", nodes: rootRows });
  for (const root of roots) visit(root);
  return sections;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function displayStatus(node, explicitRealized) {
  if (explicitRealized !== null) return "REALIZED";
  const status = String(node?.status || "Not Started").trim();
  return status.toLowerCase() === "in progress" ? "On Track" : status;
}

function excelDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value || "";
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

// ROWS_PER_PAGE is the slide template's physical capacity, not a target. Once a
// section has to split, spread it evenly rather than filling page 1 and leaving
// a stub: 19 lines become 10 + 9, not 14 + 5.
function balancedPageSize(totalRows) {
  const pageCount = Math.max(1, Math.ceil(totalRows / ROWS_PER_PAGE));
  return Math.max(1, Math.ceil(totalRows / pageCount));
}

function pagePosition(index, totalRows) {
  const pageSize = balancedPageSize(totalRows);
  const page = Math.floor(index / pageSize) + 1;
  const indexOnPage = index % pageSize;
  const pageStart = (page - 1) * pageSize;
  const rowsOnPage = Math.min(pageSize, totalRows - pageStart);
  if (rowsOnPage <= ROWS_PER_COLUMN) {
    return { page, column: "Full", rowOnPage: indexOnPage + 1 };
  }
  const leftCount = Math.ceil(rowsOnPage / 2);
  return indexOnPage < leftCount
    ? { page, column: "Left", rowOnPage: indexOnPage + 1 }
    : { page, column: "Right", rowOnPage: indexOnPage - leftCount + 1 };
}

function existingOverrides(sheet) {
  const values = sheet.getUsedRange()?.values || [];
  if (values.length < 2) return new Map();
  const indexes = new Map(values[0].map((value, index) => [String(value), index]));
  const idIndex = indexes.get("Source Task ID");
  if (idIndex === undefined) return new Map();
  const result = new Map();
  for (const row of values.slice(1)) {
    const id = String(row[idIndex] || "").trim();
    if (!id) continue;
    result.set(id, {
      slideOrder: row[indexes.get("Slide Order")],
      slideTitle: row[indexes.get("Slide Title")],
      include: row[indexes.get("Include In Total")],
    });
  }
  return result;
}

function buildRows(project, sections, overrides) {
  const output = [];
  for (const [sectionIndex, section] of sections.entries()) {
    for (const [taskIndex, node] of section.nodes.entries()) {
      const potential = numberOrNull(node.vave_potential);
      const realized = numberOrNull(node.vave_realized);
      const savings = realized ?? potential ?? 0;
      const basis = realized !== null ? "Realized" : "Potential";
      const position = pagePosition(taskIndex, section.nodes.length);
      const override = overrides.get(String(node.id || ""));
      output.push([
        project.name || "VAVE Project",
        override?.slideOrder || sectionIndex + 1,
        override?.slideTitle || section.title,
        position.page,
        position.column,
        position.rowOnPage,
        taskIndex + 1,
        node.name || "",
        potential,
        realized,
        savings,
        basis,
        excelDate(node.end_date),
        displayStatus(node, realized),
        override?.include === 0 || String(override?.include).toLowerCase() === "false" ? 0 : 1,
        node.id || "",
      ]);
    }
  }
  return output;
}

function styleDataSheet(sheet, rowCount) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A1:P1").format = {
    fill: "#1F4E79",
    font: { name: "Arial", fontSize: 10, bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
  };
  sheet.getRange("A1:P1").format.rowHeight = 30;
  if (rowCount > 0) {
    const dataRange = sheet.getRange(`A2:P${rowCount + 1}`);
    dataRange.format = {
      font: { name: "Arial", fontSize: 10, color: "#202020" },
      verticalAlignment: "top",
      wrapText: true,
    };
    sheet.getRange(`I2:K${rowCount + 1}`).format.numberFormat = "$#,##0.00";
    sheet.getRange(`M2:M${rowCount + 1}`).format.numberFormat = "m/d/yyyy";
    sheet.getRange(`N2:N${rowCount + 1}`).dataValidation = {
      rule: { type: "list", values: ["On Track", "Completed", "Not Started", "At Risk", "On Hold", "REALIZED"] },
    };
    sheet.getRange(`O2:O${rowCount + 1}`).dataValidation = {
      rule: { type: "list", values: [1, 0] },
    };
    for (let row = 2; row <= rowCount + 1; row += 1) {
      sheet.getRange(`A${row}:P${row}`).format.fill = row % 2 === 0 ? "#F2F5FA" : "#FFFFFF";
    }
  }
  const widths = [20, 12, 34, 8, 10, 12, 11, 48, 13, 13, 13, 15, 13, 16, 16, 38];
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = widths[index];
  }
}

function previewStatusColor(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed" || normalized === "realized") return "#70AD47";
  if (normalized === "on track" || normalized === "in progress") return "#ED7D31";
  return "#A6A6A6";
}

function previewSheetName(title, pageNumber) {
  const suffix = pageNumber === 1 ? "" : ` (${pageNumber})`;
  return `${String(title).slice(0, 31 - suffix.length)}${suffix}`;
}

function groupPreviewPages(rows) {
  const groups = new Map();
  for (const row of rows) {
    if (row[14] === 0 || String(row[14]).toLowerCase() === "false") continue;
    const key = `${row[1]}|${row[2]}`;
    if (!groups.has(key)) groups.set(key, { slideOrder: Number(row[1]) || 1, title: String(row[2]), rows: [] });
    groups.get(key).rows.push({
      order: Number(row[6]) || groups.get(key).rows.length + 1,
      taskName: row[7],
      savings: Number(row[10]) || 0,
      endDate: row[12],
      status: row[13],
    });
  }
  const pages = [];
  for (const group of [...groups.values()].sort((a, b) => a.slideOrder - b.slideOrder)) {
    group.rows.sort((a, b) => a.order - b.order);
    const pageSize = balancedPageSize(group.rows.length);
    const pageCount = Math.ceil(group.rows.length / pageSize);
    for (let pageIndex = 0; pageIndex < pageCount; pageIndex += 1) {
      pages.push({
        ...group,
        pageNumber: pageIndex + 1,
        pageCount,
        rows: group.rows.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize),
      });
    }
  }
  return pages;
}

function writePreviewBlock(sheet, records, startColumn, headerRow, fullWidth) {
  const taskStart = startColumn;
  const taskEnd = fullWidth ? startColumn + 5 : startColumn;
  const savingsColumn = fullWidth ? startColumn + 6 : startColumn + 1;
  const endColumn = fullWidth ? startColumn + 7 : startColumn + 2;
  const statusColumn = fullWidth ? startColumn + 8 : startColumn + 3;
  const columnName = (index) => String.fromCharCode(65 + index);
  if (taskEnd > taskStart) sheet.getRange(`${columnName(taskStart)}${headerRow}:${columnName(taskEnd)}${headerRow}`).merge();
  sheet.getRange(`${columnName(taskStart)}${headerRow}:${columnName(statusColumn)}${headerRow}`).format = {
    fill: "#D9E2F3",
    font: { name: "Arial", fontSize: 10, bold: true, color: "#202020" },
    verticalAlignment: "center",
  };
  sheet.getCell(headerRow - 1, taskStart).values = [["Task Name"]];
  sheet.getCell(headerRow - 1, savingsColumn).values = [["Savings"]];
  sheet.getCell(headerRow - 1, endColumn).values = [["End"]];
  sheet.getCell(headerRow - 1, statusColumn).values = [["Status"]];
  sheet.getCell(headerRow - 1, savingsColumn).format.horizontalAlignment = "center";
  sheet.getCell(headerRow - 1, endColumn).format.horizontalAlignment = "center";
  sheet.getCell(headerRow - 1, statusColumn).format.horizontalAlignment = "center";

  for (const [offset, record] of records.entries()) {
    const rowNumber = headerRow + offset + 1;
    if (taskEnd > taskStart) sheet.getRange(`${columnName(taskStart)}${rowNumber}:${columnName(taskEnd)}${rowNumber}`).merge();
    const rowRange = sheet.getRange(`${columnName(taskStart)}${rowNumber}:${columnName(statusColumn)}${rowNumber}`);
    rowRange.format = {
      fill: offset % 2 === 0 ? "#F2F5FA" : "#FFFFFF",
      font: { name: "Arial", fontSize: 10, color: "#202020" },
      verticalAlignment: "center",
      wrapText: true,
    };
    sheet.getCell(rowNumber - 1, taskStart).values = [[record.taskName]];
    sheet.getCell(rowNumber - 1, savingsColumn).values = [[record.savings]];
    sheet.getCell(rowNumber - 1, savingsColumn).format = {
      font: { name: "Arial", fontSize: 10, bold: true, color: "#202020" },
      numberFormat: "$#,##0.00",
      horizontalAlignment: "right",
      verticalAlignment: "center",
    };
    sheet.getCell(rowNumber - 1, endColumn).values = [[record.endDate]];
    sheet.getCell(rowNumber - 1, endColumn).format = {
      font: { name: "Arial", fontSize: 10, color: "#202020" },
      numberFormat: "m/d/yyyy",
      horizontalAlignment: "center",
      verticalAlignment: "center",
    };
    sheet.getCell(rowNumber - 1, statusColumn).values = [[record.status]];
    sheet.getCell(rowNumber - 1, statusColumn).format = {
      fill: previewStatusColor(record.status),
      font: { name: "Arial", fontSize: 10, bold: true, color: "#FFFFFF" },
      horizontalAlignment: "center",
      verticalAlignment: "center",
    };
    sheet.getRange(`A${rowNumber}:I${rowNumber}`).format.rowHeight = 39;
  }
}

function rebuildPreviewSheet(workbook, page, dataSheetName, dataLastRow) {
  const name = previewSheetName(page.title, page.pageNumber);
  let sheet = workbook.worksheets.items.find((item) => item.name === name);
  if (!sheet) sheet = workbook.worksheets.add(name);
  sheet.getRange("A1:I30").unmerge();
  sheet.getRange("A1:I30").clear({ applyTo: "all" });
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(4);
  const accent = page.slideOrder % 2 === 1 ? "#4472C4" : "#ED7D31";
  const displayTitle = page.pageCount > 1 ? `${page.title} · ${page.pageNumber} of ${page.pageCount}` : page.title;

  sheet.getRange("A1:I1").merge();
  sheet.getRange("A1:I1").values = [[displayTitle]];
  sheet.getRange("A1:I1").format = {
    fill: "#1F4E79",
    font: { name: "Arial", fontSize: 20, bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
  };
  sheet.getRange("A1:I1").format.rowHeight = 42;
  sheet.getRange("A3:G3").merge();
  sheet.getRange("A3:G3").values = [[displayTitle]];
  sheet.getRange("A3:I3").format = {
    fill: accent,
    font: { name: "Arial", fontSize: 11, bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
  };
  sheet.getRange("H3").values = [["Total:"]];
  sheet.getRange("H3").format.horizontalAlignment = "right";
  const escapedSheet = dataSheetName.replace(/'/g, "''");
  const escapedTitle = page.title.replace(/"/g, '""');
  sheet.getRange("I3").formulas = [[`=SUMIFS('${escapedSheet}'!$K$2:$K$${dataLastRow},'${escapedSheet}'!$C$2:$C$${dataLastRow},"${escapedTitle}",'${escapedSheet}'!$O$2:$O$${dataLastRow},1)`]];
  sheet.getRange("I3").format = {
    fill: accent,
    font: { name: "Arial", fontSize: 11, bold: true, color: "#FFFFFF" },
    numberFormat: "$#,##0.00",
    horizontalAlignment: "right",
    verticalAlignment: "center",
  };
  sheet.getRange("A3:I3").format.rowHeight = 28;

  // A section longer than one page used to leave its overflow on a tab parked
  // after the instructions sheet, so the extra lines looked like they had never
  // been exported. Spell the continuation out on the page itself.
  if (page.pageCount > 1) {
    const nextName = previewSheetName(page.title, page.pageNumber + 1);
    const priorName = previewSheetName(page.title, page.pageNumber - 1);
    const notes = [];
    if (page.pageNumber > 1) notes.push(`continued from tab "${priorName}"`);
    if (page.pageNumber < page.pageCount) notes.push(`continues on tab "${nextName}"`);
    sheet.getRange("A2:I2").merge();
    sheet.getRange("A2:I2").values = [[`This section needs ${page.pageCount} pages — ${notes.join(", ")}.`]];
    sheet.getRange("A2:I2").format = {
      fill: "#FFF2CC",
      font: { name: "Arial", fontSize: 10, bold: true, color: "#7F6000" },
      verticalAlignment: "center",
    };
    sheet.getRange("A2:I2").format.rowHeight = 22;
  }

  if (page.rows.length <= ROWS_PER_COLUMN) {
    writePreviewBlock(sheet, page.rows, 0, 5, true);
  } else {
    const leftCount = Math.ceil(page.rows.length / 2);
    writePreviewBlock(sheet, page.rows.slice(0, leftCount), 0, 5, false);
    writePreviewBlock(sheet, page.rows.slice(leftCount), 5, 5, false);
  }
  const widths = [42, 12, 13, 16, 3, 42, 12, 13, 16];
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = widths[index];
  }
  return name;
}

function rebuildPreviewSheets(workbook, rows, dataSheetName) {
  const pages = groupPreviewPages(rows);
  const desiredNames = new Set();
  const orderedNames = [];
  for (const page of pages) {
    const name = rebuildPreviewSheet(workbook, page, dataSheetName, rows.length + 1);
    desiredNames.add(name);
    orderedNames.push(name);
  }
  // Newly added tabs land at the end of the workbook, which put page 2 of a
  // section behind the instructions tab. Put every preview tab back in slide
  // order, directly after the data sheet.
  const dataSheet = workbook.worksheets.items.find((item) => item.name === dataSheetName);
  if (dataSheet) {
    let target = dataSheet.index + 1;
    for (const name of orderedNames) {
      const sheet = workbook.worksheets.items.find((item) => item.name === name);
      if (sheet) sheet.index = target;
      target += 1;
    }
  }
  for (const sheet of workbook.worksheets.items) {
    if (!/VAVE activities(?: \(\d+\))?$/i.test(sheet.name) || desiredNames.has(sheet.name)) continue;
    sheet.getRange("A1:I30").unmerge();
    sheet.getRange("A1:I30").clear({ applyTo: "all" });
    sheet.getRange("A1:I1").merge();
    sheet.getRange("A1:I1").values = [["Preview page removed by the latest VPM Tracker refresh"]];
  }
  return pages;
}

const args = parseArgs(process.argv.slice(2));
const vpmtPath = requiredPath(args, "vpmt");
const xlsxPath = requiredPath(args, "xlsx");
const vpmt = JSON.parse(await fs.readFile(vpmtPath, "utf8"));
const candidates = (Array.isArray(vpmt.projects) ? vpmt.projects : [])
  .filter((project) => project?.is_vave)
  .map((project) => ({ project, sections: collectSections(project.tasks) }))
  .filter((item) => item.sections.length);
if (!candidates.length) throw new Error("The .vpmt file has no VAVE project sections to export.");

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
let sheet = workbook.worksheets.items.find((item) => item.name.endsWith(" VAVE Data"));
if (!sheet) throw new Error("The Excel input has no worksheet ending in ' VAVE Data'.");
const overrides = existingOverrides(sheet);
const { project, sections } = candidates[0];
const rows = buildRows(project, sections, overrides);
const oldRowCount = Math.max(0, (sheet.getUsedRange()?.values?.length || 1) - 1);
const clearCount = Math.max(oldRowCount, rows.length);
const priorTableName = sheet.tables.items.length
  ? sheet.tables.items[0].name || "VaveDataTable"
  : null;
if (sheet.tables.items.length) sheet.tables.deleteAll();
if (clearCount) sheet.getRange(`A2:P${clearCount + 1}`).clear({ applyTo: "all" });
sheet.getRange("A1:P1").values = [HEADERS];
if (rows.length) sheet.getRange(`A2:P${rows.length + 1}`).values = rows;
styleDataSheet(sheet, rows.length);
if (priorTableName) sheet.tables.add(`A1:P${rows.length + 1}`, true, priorTableName);
const previewPages = rebuildPreviewSheets(workbook, rows, sheet.name);

const instructions = workbook.worksheets.items.find((item) => item.name === "VAVE Slide Instructions");
if (instructions) {
  instructions.getRange("A15:F15").merge();
  instructions.getRange("A15:F15").values = [[`Last refreshed from ${path.basename(vpmtPath)}. Re-run Generate VAVE Slides.cmd after saving tracker changes.`]];
  instructions.getRange("A15:F15").format = { fill: "#E2F0D9", font: { bold: true, color: "#375623" }, wrapText: true };
  instructions.getRange("A15:F15").format.rowHeight = 30;
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(xlsxPath);
console.log(JSON.stringify({
  vpmtPath,
  xlsxPath,
  project: project.name,
  sections: sections.map((section) => ({ title: section.title, rows: section.nodes.length })),
  previewPages: previewPages.map((page) => ({ title: page.title, page: page.pageNumber, rows: page.rows.length })),
  totalRows: rows.length,
}));
process.exit(0);
