// Generate the two branded VAVE slides from the normalized Excel handoff.
import fs from "node:fs/promises";
import path from "node:path";
import {
  FileBlob,
  PresentationFile,
  SpreadsheetFile,
} from "@oai/artifact-tool";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith("--")) continue;
    args[argv[i].slice(2)] = argv[i + 1];
    i += 1;
  }
  return args;
}

function requireArg(args, key) {
  if (!args[key]) throw new Error(`Missing required --${key}`);
  return path.resolve(args[key]);
}

function shapeByName(slide, name) {
  const matches = slide.shapes.items.filter((shape) => shape.name === name);
  if (matches.length !== 1) {
    throw new Error(`Expected one shape named "${name}" on slide ${slide.index + 1}; found ${matches.length}.`);
  }
  return matches[0];
}

function shapeText(shape) {
  const proto = shape.toProto();
  return (proto.paragraphs || [])
    .map((paragraph) => (paragraph.runs || []).map((run) => run.text || "").join(""))
    .join("\n");
}

function replaceText(shape, value) {
  const next = String(value ?? "");
  const current = shapeText(shape);
  if (current) shape.text.replace(current, next);
  else shape.text = next;
}

function setFill(shape, color) {
  shape.fill = color;
  shape.line = { style: "solid", fill: color, width: 0 };
}

function currency(value) {
  const number = Number(value || 0);
  return number.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return `${value.getMonth() + 1}/${value.getDate()}/${value.getFullYear()}`;
  }
  if (typeof value === "number" && value > 20000) {
    const epoch = Date.UTC(1899, 11, 30);
    const date = new Date(epoch + value * 86400000);
    return `${date.getUTCMonth() + 1}/${date.getUTCDate()}/${date.getUTCFullYear()}`;
  }
  const text = String(value ?? "").trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${Number(match[2])}/${Number(match[3])}/${match[1]}`;
  return text;
}

function statusColor(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "on track" || normalized === "in progress") return "#ED7D31";
  if (normalized === "completed" || normalized === "realized") return "#70AD47";
  return "#A6A6A6";
}

function statusLabel(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "in progress") return "On Track";
  if (normalized === "realized") return "REALIZED";
  return String(status || "");
}

function valueAt(values, headers, name) {
  const index = headers.get(name);
  return index === undefined ? null : values[index];
}

function shouldInclude(value) {
  if (value === null || value === undefined || value === "") return true;
  if (typeof value === "boolean") return value;
  const normalized = String(value).trim().toLowerCase();
  return !["0", "false", "no", "n", "exclude"].includes(normalized);
}

async function readVavePages(xlsxPath) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
  const sheet = workbook.worksheets.items.find((item) => item.name.endsWith(" VAVE Data"));
  if (!sheet) throw new Error("No worksheet ending in ' VAVE Data' was found.");

  const values = sheet.getUsedRange().values;
  if (!values || values.length < 2) throw new Error("The VAVE Data sheet has no rows.");
  const headers = new Map(values[0].map((value, index) => [String(value), index]));
  for (const required of ["Slide Title", "Task Name", "Savings", "End Date", "Status"]) {
    if (!headers.has(required)) throw new Error(`VAVE Data is missing the "${required}" column.`);
  }

  const rows = [];
  let inheritedTitle = "";
  let inheritedSlideOrder = 1;
  for (const [index, valuesRow] of values.slice(1).entries()) {
    if (!valuesRow.some((value) => value !== null && value !== "")) continue;
    const taskName = String(valueAt(valuesRow, headers, "Task Name") || "").trim();
    if (!taskName || !shouldInclude(valueAt(valuesRow, headers, "Include In Total"))) continue;

    const explicitTitle = String(valueAt(valuesRow, headers, "Slide Title") || "").trim();
    if (explicitTitle) inheritedTitle = explicitTitle;
    if (!inheritedTitle) {
      throw new Error(`Excel row ${index + 2} has a task but no Slide Title.`);
    }

    const explicitSlideOrder = Number(valueAt(valuesRow, headers, "Slide Order"));
    if (Number.isFinite(explicitSlideOrder) && explicitSlideOrder > 0) inheritedSlideOrder = explicitSlideOrder;
    const explicitTaskOrder = Number(valueAt(valuesRow, headers, "Task Order"));
    rows.push({
      project: valueAt(valuesRow, headers, "Project"),
      slideOrder: inheritedSlideOrder,
      title: inheritedTitle,
      taskOrder: Number.isFinite(explicitTaskOrder) && explicitTaskOrder > 0 ? explicitTaskOrder : index + 1,
      sourceIndex: index,
      taskName,
      savings: Number(valueAt(valuesRow, headers, "Savings") || 0),
      endDate: formatDate(valueAt(valuesRow, headers, "End Date")),
      status: statusLabel(valueAt(valuesRow, headers, "Status") || "Not Started"),
    });
  }
  if (!rows.length) throw new Error("The VAVE Data sheet has no included task rows.");

  const groups = new Map();
  for (const row of rows) {
    const key = `${row.slideOrder}|${row.title}`;
    if (!groups.has(key)) groups.set(key, { slideOrder: row.slideOrder, title: row.title, firstIndex: row.sourceIndex, rows: [] });
    groups.get(key).rows.push(row);
  }

  const sections = [...groups.values()].sort((a, b) => a.slideOrder - b.slideOrder || a.firstIndex - b.firstIndex);
  const pages = [];
  for (const [sectionIndex, section] of sections.entries()) {
    section.rows.sort((a, b) => a.taskOrder - b.taskOrder || a.sourceIndex - b.sourceIndex);
    const totalCount = section.rows.length;
    const totalSavings = section.rows.reduce((sum, row) => sum + row.savings, 0);
    const chunks = [];
    for (let offset = 0; offset < section.rows.length; offset += 14) {
      chunks.push(section.rows.slice(offset, offset + 14));
    }
    for (const [pageIndex, chunk] of chunks.entries()) {
      pages.push({
        slideOrder: section.slideOrder,
        title: section.title,
        displayTitle: chunks.length > 1 ? `${section.title} · ${pageIndex + 1} of ${chunks.length}` : section.title,
        pageNumber: pageIndex + 1,
        pageCount: chunks.length,
        totalCount,
        totalSavings,
        accent: sectionIndex === 0 ? "#4472C4" : "#ED7D31",
        layout: chunk.length > 7 ? "two" : "single",
        rows: chunk,
      });
    }
  }
  return pages;
}

const twoColumnSlots = {
  left: [
    ["Rectangle 13", "TextBox 14", "TextBox 15", "TextBox 16", "Rounded Rectangle 17", "TextBox 18"],
    ["Rectangle 19", "TextBox 20", "TextBox 21", "TextBox 22", "Rounded Rectangle 23", "TextBox 24"],
    ["Rectangle 25", "TextBox 26", "TextBox 27", "TextBox 28", "Rounded Rectangle 29", "TextBox 30"],
    ["Rectangle 31", "TextBox 32", "TextBox 33", "TextBox 34", "Rounded Rectangle 35", "TextBox 36"],
    ["Rectangle 37", "TextBox 38", "TextBox 39", "TextBox 40", "Rounded Rectangle 41", "TextBox 42"],
    ["Rectangle 43", "TextBox 44", "TextBox 45", "TextBox 46", "Rounded Rectangle 47", "TextBox 48"],
    ["Rectangle 49", "TextBox 50", "TextBox 51", "TextBox 52", "Rounded Rectangle 53", "TextBox 54"],
  ],
  right: [
    ["Rectangle 60", "TextBox 61", "TextBox 62", "TextBox 63", "Rounded Rectangle 64", "TextBox 65"],
    ["Rectangle 66", "TextBox 67", "TextBox 68", "TextBox 69", "Rounded Rectangle 70", "TextBox 71"],
    ["Rectangle 72", "TextBox 73", "TextBox 74", "TextBox 75", "Rounded Rectangle 76", "TextBox 77"],
    ["Rectangle 78", "TextBox 79", "TextBox 80", "TextBox 81", "Rounded Rectangle 82", "TextBox 83"],
    ["Rectangle 84", "TextBox 85", "TextBox 86", "TextBox 87", "Rounded Rectangle 88", "TextBox 89"],
    ["Rectangle 90", "TextBox 91", "TextBox 92", "TextBox 93", "Rounded Rectangle 94", "TextBox 95"],
  ],
};

function deleteSlot(slide, slot) {
  for (const name of slot) shapeByName(slide, name).delete();
}

function fillSlot(slide, slot, row) {
  const [, taskName, savingsName, dateName, pillName, statusName] = slot;
  replaceText(shapeByName(slide, taskName), row.taskName);
  replaceText(shapeByName(slide, savingsName), currency(row.savings));
  replaceText(shapeByName(slide, dateName), row.endDate);
  const pill = shapeByName(slide, pillName);
  setFill(pill, statusColor(row.status));
  replaceText(shapeByName(slide, statusName), row.status);
}

function addTextBox(slide, name, position, text, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = [[{
    run: String(text),
    textStyle: {
      fontSize: options.fontSize || "10pt",
      typeface: options.typeface || "Aptos",
      color: options.color || "#202020",
      bold: Boolean(options.bold),
    },
  }]];
  shape.text.style = {
    alignment: options.alignment || "left",
    verticalAlignment: "middle",
    wrap: options.wrap || "none",
    autoFit: options.autoFit || "shrinkText",
    insets: { top: 0.5, right: 2, bottom: 0.5, left: 2 },
  };
  return shape;
}

function addSeventhRightRow(slide, row) {
  slide.shapes.add({
    geometry: "rect",
    name: "Generated Right Row 7",
    position: { left: 657.6, top: 616.32, width: 580.8, height: 61.44 },
    fill: "#F2F5FA",
    line: { style: "solid", fill: "#F2F5FA", width: 0 },
  });
  addTextBox(
    slide,
    "Generated Right Task 7",
    { left: 669.12, top: 632.1, width: 316, height: 33.3 },
    row.taskName,
    { wrap: "square" },
  );
  addTextBox(
    slide,
    "Generated Right Savings 7",
    { left: 996, top: 632.72, width: 54, height: 17.13 },
    currency(row.savings),
    { bold: true, alignment: "right" },
  );
  addTextBox(
    slide,
    "Generated Right Date 7",
    { left: 1067, top: 632.72, width: 70, height: 17.13 },
    row.endDate,
    { alignment: "center" },
  );
  const pill = slide.shapes.add({
    geometry: "roundRect",
    name: "Generated Right Status Pill 7",
    position: { left: 1145.47, top: 630.72, width: 86.4, height: 26.88 },
    fill: statusColor(row.status),
    line: { style: "solid", fill: statusColor(row.status), width: 0 },
  });
  pill.borderRadius = "rounded-lg";
  addTextBox(
    slide,
    "Generated Right Status 7",
    { left: 1151, top: 632.24, width: 75, height: 17.13 },
    row.status,
    { bold: true, color: "#FFFFFF", alignment: "center" },
  );
}

function setTopCopy(slide, page) {
  setFill(shapeByName(slide, "Rectangle 5"), page.accent);
  const title = shapeByName(slide, "TextBox 2");
  replaceText(title, page.displayTitle);
  // The source single-column title has a malformed resize-to-fit transform.
  // Normalizing only that frame avoids clipping while the two-column source
  // title remains most stable when its inherited geometry is left untouched.
  if (page.layout === "single") {
    title.position = { left: 33.6, top: 14.4, width: 777.6, height: 43.2 };
    title.text.autoFit = "none";
  }
  replaceText(shapeByName(slide, "TextBox 6"), `${page.totalCount} savings opportunities`);
  replaceText(shapeByName(slide, "TextBox 7"), `Total: ${currency(page.totalSavings)}`);
}

function populateTwoColumnSlide(slide, page) {
  if (page.rows.length < 1 || page.rows.length > 14) {
    throw new Error(`Two-column slide requires 1-14 rows; received ${page.rows.length}.`);
  }
  setTopCopy(slide, page);
  const leftCount = Math.ceil(page.rows.length / 2);
  const leftRows = page.rows.slice(0, leftCount);
  const rightRows = page.rows.slice(leftCount);

  for (let i = 0; i < twoColumnSlots.left.length; i += 1) {
    if (leftRows[i]) fillSlot(slide, twoColumnSlots.left[i], leftRows[i]);
    else deleteSlot(slide, twoColumnSlots.left[i]);
  }
  for (let i = 0; i < twoColumnSlots.right.length; i += 1) {
    if (rightRows[i]) fillSlot(slide, twoColumnSlots.right[i], rightRows[i]);
    else deleteSlot(slide, twoColumnSlots.right[i]);
  }
  if (rightRows[6]) addSeventhRightRow(slide, rightRows[6]);
  slide.speakerNotes.textFrame.setText(
    `[Sources]\n- ${page.sourceName}; sheet: VAVE Data; section: ${page.title}`,
  );
}

const singleColumnSlots = [
  ["Rectangle 13", "TextBox 14", "TextBox 15", "TextBox 16", "Rounded Rectangle 17", "TextBox 18"],
  ["Rectangle 19", "TextBox 20", "TextBox 21", "TextBox 22", "Rounded Rectangle 23", "TextBox 24"],
  ["Rectangle 25", "TextBox 26", "TextBox 27", "TextBox 28", "Rounded Rectangle 29", "TextBox 30"],
  ["Rectangle 31", "TextBox 32", "TextBox 33", "TextBox 34", "Rounded Rectangle 35", "TextBox 36"],
  ["Rectangle 37", "TextBox 38", "TextBox 39", "TextBox 40", "Rounded Rectangle 41", "TextBox 42"],
  ["Rectangle 43", "TextBox 44", "TextBox 45", "TextBox 46", "Rounded Rectangle 47", "TextBox 48"],
  ["Rectangle 49", "TextBox 50", "TextBox 51", "TextBox 52", "Rounded Rectangle 53", "TextBox 54"],
];

function populateSingleColumnSlide(slide, page) {
  if (page.rows.length < 1 || page.rows.length > 7) {
    throw new Error(`Single-column slide requires 1-7 rows; received ${page.rows.length}.`);
  }
  setTopCopy(slide, page);
  for (let i = page.rows.length; i < singleColumnSlots.length; i += 1) {
    deleteSlot(slide, singleColumnSlots[i]);
  }

  for (let i = 0; i < page.rows.length; i += 1) {
    fillSlot(slide, singleColumnSlots[i], page.rows[i]);
  }
  slide.speakerNotes.textFrame.setText(
    `[Sources]\n- ${page.sourceName}; sheet: VAVE Data; section: ${page.title}`,
  );
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const xlsxPath = requireArg(args, "xlsx");
  const starterPptxPath = requireArg(args, "template");
  const outputPath = requireArg(args, "out");
  const qaDir = args["qa-dir"] ? path.resolve(args["qa-dir"]) : path.join(path.dirname(outputPath), "qa");

  const pages = await readVavePages(xlsxPath);
  for (const page of pages) page.sourceName = path.basename(xlsxPath);

  const presentation = await PresentationFile.importPptx(await FileBlob.load(starterPptxPath));
  if (presentation.slides.items.length !== 2) {
    throw new Error(`The VAVE starter template must contain exactly 2 slides; found ${presentation.slides.items.length}.`);
  }

  const twoColumnTemplate = presentation.slides.items[0];
  const singleColumnTemplate = presentation.slides.items[1];
  let usedTwoColumnTemplate = false;
  let usedSingleColumnTemplate = false;
  const outputSlides = pages.map((page) => {
    if (page.layout === "two" && !usedTwoColumnTemplate) {
      usedTwoColumnTemplate = true;
      return twoColumnTemplate;
    }
    if (page.layout === "single" && !usedSingleColumnTemplate) {
      usedSingleColumnTemplate = true;
      return singleColumnTemplate;
    }
    return page.layout === "two" ? twoColumnTemplate.duplicate() : singleColumnTemplate.duplicate();
  });
  if (!usedTwoColumnTemplate) twoColumnTemplate.delete();
  if (!usedSingleColumnTemplate) singleColumnTemplate.delete();
  for (const [index, slide] of outputSlides.entries()) {
    slide.moveTo(index);
    if (pages[index].layout === "two") populateTwoColumnSlide(slide, pages[index]);
    else populateSingleColumnSlide(slide, pages[index]);
  }

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.mkdir(qaDir, { recursive: true });
  for (const [index, slide] of presentation.slides.items.entries()) {
    const number = String(index + 1).padStart(2, "0");
    await writeBlob(
      path.join(qaDir, `slide-${number}.png`),
      await presentation.export({ slide, format: "png", scale: 2 }),
    );
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(qaDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
  }
  await writeBlob(
    path.join(qaDir, "montage.webp"),
    await presentation.export({ format: "webp", montage: true, scale: 1 }),
  );
  const inspect = await presentation.inspect({
    kind: "slide,textbox,shape,notes,layout",
    include: "id,slide,name,bbox,text,textPreview,isPlaceholder",
    maxChars: 100000,
  });
  await fs.writeFile(path.join(qaDir, "final-inspect.ndjson"), inspect.ndjson, "utf8");
  await fs.writeFile(path.join(qaDir, "content.json"), JSON.stringify({ pages }, null, 2), "utf8");

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
  console.log(JSON.stringify({ outputPath, pages: pages.map((page) => ({ title: page.title, rows: page.rows.length })) }));
  process.exitCode = 0;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
