/**
 * Build the Capstone 2 PRD as a Word document from docs/PRD.md.
 *
 * The submission wants the PRD as Word or PDF, and docs/PRD.md is the source of
 * truth — so this regenerates the .docx rather than anyone maintaining two
 * copies that drift apart.
 *
 *   npm install docx
 *   node scripts/build_prd_docx.js docs/PRD.md docs/Capstone2_PRD_Surgical_Oncology_Dashboard.docx
 *
 * Handles the subset of Markdown the PRD actually uses: ATX headings, tables,
 * bullet and task lists, blockquotes, fenced code, horizontal rules, and inline
 * bold / italic / code / links.
 */

const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, HeadingLevel, LevelFormat, PageBreak,
  Packer, Paragraph, ShadingType, Table, TableCell, TableRow, TextRun, WidthType,
} = require("docx");

const SRC = process.argv[2];
const OUT = process.argv[3];

const TEAL = "028090";
const INK = "13343B";
const MUTED = "5B7B7A";
const RED = "9A281B";

// US Letter, in DXA (1440 = 1 inch).
const PAGE = { width: 12240, height: 15840 };
const MARGIN = 1080; // 0.75"
const CONTENT_WIDTH = PAGE.width - MARGIN * 2;

// ---------------------------------------------------------------- inline text

function inlineRuns(text, base = {}) {
  const runs = [];
  // Order matters: code first so ** inside `code` is not treated as bold.
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let match;

  const push = (value, extra) => {
    if (value) runs.push(new TextRun({ text: value, ...base, ...extra }));
  };

  while ((match = pattern.exec(text)) !== null) {
    push(decode(text.slice(last, match.index)));
    const token = match[0];
    if (token.startsWith("`")) {
      push(decode(token.slice(1, -1)), { font: "Consolas", size: 18, color: RED });
    } else if (token.startsWith("**")) {
      push(decode(token.slice(2, -2)), { bold: true });
    } else if (token.startsWith("*")) {
      push(decode(token.slice(1, -1)), { italics: true });
    } else {
      // [label](url) -> keep the label; the URL is noise on paper.
      push(decode(token.slice(1, token.indexOf("]"))));
    }
    last = pattern.lastIndex;
  }
  push(decode(text.slice(last)));
  return runs.length ? runs : [new TextRun({ text: "", ...base })];
}

function decode(text) {
  return text
    .replace(/&middot;/g, "·").replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–").replace(/&larr;/g, "←")
    .replace(/&rarr;/g, "→").replace(/&amp;/g, "&")
    .replace(/&ldquo;/g, "“").replace(/&rdquo;/g, "”")
    .replace(/&nbsp;/g, " ")
    .replace(/\[ \]/g, "☐").replace(/\[x\]/gi, "☒")
    .replace(/✅/g, "[done]").replace(/⚠️?/g, "[!]")
    .replace(/\u{1F7E1}/gu, "[draft]");
}

// ------------------------------------------------------------------ elements

function heading(text, level) {
  const levels = [
    HeadingLevel.HEADING_1, HeadingLevel.HEADING_2,
    HeadingLevel.HEADING_3, HeadingLevel.HEADING_4,
  ];
  return new Paragraph({
    heading: levels[Math.min(level, 4) - 1],
    spacing: { before: level === 1 ? 360 : 260, after: 130 },
    keepNext: true,
    children: inlineRuns(text.replace(/^#+\s*/, "")),
  });
}

function body(text, extra = {}) {
  return new Paragraph({
    spacing: { after: 130, line: 276 },
    children: inlineRuns(text),
    ...extra,
  });
}

function bullet(text, depth = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level: Math.min(depth, 2) },
    spacing: { after: 80, line: 276 },
    children: inlineRuns(text),
  });
}

function numbered(text) {
  return new Paragraph({
    numbering: { reference: "numbers", level: 0 },
    spacing: { after: 80, line: 276 },
    children: inlineRuns(text),
  });
}

function quote(lines) {
  // A callout: left rule, tinted, kept together.
  return lines.map((line, i) => new Paragraph({
    spacing: { before: i === 0 ? 180 : 0, after: i === lines.length - 1 ? 180 : 0, line: 276 },
    indent: { left: 340 },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: TEAL, space: 12 } },
    shading: { type: ShadingType.CLEAR, fill: "F4F8F7" },
    children: inlineRuns(line),
  }));
}

function code(lines) {
  return lines.map((line, i) => new Paragraph({
    spacing: { before: i === 0 ? 140 : 0, after: i === lines.length - 1 ? 160 : 0 },
    shading: { type: ShadingType.CLEAR, fill: "F2F5F5" },
    indent: { left: 200 },
    children: [new TextRun({ text: line || " ", font: "Consolas", size: 17, color: INK })],
  }));
}

function rule() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "D6E2E1", space: 1 } },
    children: [new TextRun("")],
  });
}

function splitRow(line) {
  return line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

function table(rows) {
  const header = splitRow(rows[0]);
  const bodyRows = rows.slice(2).map(splitRow);
  const columns = header.length;

  // Dual widths, both DXA, summing to the content width — percentages break in
  // Google Docs and unequal sums make Word guess.
  const each = Math.floor(CONTENT_WIDTH / columns);
  const widths = Array(columns).fill(each);
  widths[columns - 1] += CONTENT_WIDTH - each * columns;

  const cell = (text, isHeader, index) => new TableCell({
    width: { size: widths[index], type: WidthType.DXA },
    shading: isHeader
      ? { type: ShadingType.CLEAR, fill: TEAL }
      : { type: ShadingType.CLEAR, fill: "FFFFFF" },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({
      spacing: { after: 0, line: 250 },
      children: inlineRuns(text, isHeader ? { bold: true, color: "FFFFFF", size: 18 } : { size: 18 }),
    })],
  });

  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    rows: [
      new TableRow({
        tableHeader: true,
        children: header.map((text, i) => cell(text, true, i)),
      }),
      ...bodyRows.map((row) => new TableRow({
        children: Array.from({ length: columns }, (_, i) => cell(row[i] || "", false, i)),
      })),
    ],
  });
}

// -------------------------------------------------------------------- parsing

function parse(markdown) {
  const lines = markdown.split(/\r?\n/);
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i++; continue; }

    if (/^```/.test(line)) {
      const block = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) block.push(lines[i++]);
      i++;
      out.push(...code(block));
      continue;
    }

    if (/^\|/.test(line) && /^\|[\s:|-]+\|/.test(lines[i + 1] || "")) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
      out.push(table(rows));
      out.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun("")] }));
      continue;
    }

    if (/^>/.test(line)) {
      const block = [];
      while (i < lines.length && /^>/.test(lines[i])) {
        block.push(lines[i++].replace(/^>\s?/, ""));
      }
      // A quote can contain a table — Appendix A puts the conditional rules in
      // one. Emit prose as a quote and the table as a real table, rather than
      // letting the pipe syntax through as literal text.
      let prose = [];
      for (let j = 0; j < block.length; j++) {
        if (/^\|/.test(block[j]) && /^\|[\s:|-]+\|/.test(block[j + 1] || "")) {
          if (prose.length) { out.push(...quote(joinWrapped(prose))); prose = []; }
          const rows = [];
          while (j < block.length && /^\|/.test(block[j])) rows.push(block[j++]);
          j--;
          out.push(table(rows));
          out.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun("")] }));
          continue;
        }
        prose.push(block[j]);
      }
      if (prose.length) out.push(...quote(joinWrapped(prose)));
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { out.push(rule()); i++; continue; }

    if (/^#{1,6}\s/.test(line)) {
      out.push(heading(line, line.match(/^#+/)[0].length));
      i++;
      continue;
    }

    if (/^\s*[-*]\s/.test(line)) {
      const depth = Math.floor((line.match(/^\s*/)[0].length) / 2);
      let text = line.replace(/^\s*[-*]\s+/, "");
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1]) && !/^\s*[-*]\s/.test(lines[i + 1])) {
        text += " " + lines[++i].trim();
      }
      out.push(bullet(text, depth));
      i++;
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      let text = line.replace(/^\d+\.\s+/, "");
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1]) && !/^\d+\.\s/.test(lines[i + 1])) {
        text += " " + lines[++i].trim();
      }
      out.push(numbered(text));
      i++;
      continue;
    }

    // Plain paragraph: gather wrapped lines.
    let text = line.trim();
    while (i + 1 < lines.length && lines[i + 1].trim()
           && !/^[#>|`\-*\d]/.test(lines[i + 1].trim())) {
      text += " " + lines[++i].trim();
    }
    out.push(body(text));
    i++;
  }
  return out;
}

function joinWrapped(block) {
  const out = [];
  let buffer = "";
  for (const line of block) {
    if (!line.trim()) {
      if (buffer) { out.push(buffer); buffer = ""; }
      continue;
    }
    buffer = buffer ? `${buffer} ${line.trim()}` : line.trim();
  }
  if (buffer) out.push(buffer);
  return out;
}

// ----------------------------------------------------------------- the document

const markdown = fs.readFileSync(SRC, "utf8");

// The title block is rendered by hand; the rest is parsed.
const firstHeadingEnd = markdown.indexOf("\n## ");
const front = markdown.slice(0, firstHeadingEnd);
const rest = markdown.slice(firstHeadingEnd);

const title = (front.match(/^#\s+(.+)$/m) || [, "PRD"])[1];
const meta = [...front.matchAll(/^\*\*(.+?):\*\*\s*(.+)$/gm)].map((m) => [m[1], m[2]]);

const cover = [
  new Paragraph({
    spacing: { before: 1800, after: 120 },
    children: [new TextRun({ text: title, bold: true, size: 46, color: TEAL })],
  }),
  new Paragraph({
    spacing: { after: 500 },
    children: [new TextRun({
      text: "Product Requirements Document", size: 26, color: MUTED,
    })],
  }),
  new Paragraph({
    spacing: { after: 500 },
    shading: { type: ShadingType.CLEAR, fill: "FBE4E0" },
    border: { left: { style: BorderStyle.SINGLE, size: 24, color: RED, space: 12 } },
    indent: { left: 240 },
    children: [new TextRun({
      text: "NOT FOR CLINICAL USE — a prototype running on synthetic data only. "
          + "It has not been validated, reviewed or approved for clinical use, and no "
          + "real patient record has been near it.",
      bold: true, color: RED, size: 21,
    })],
  }),
  ...meta.map(([key, value]) => new Paragraph({
    spacing: { after: 70 },
    children: [
      new TextRun({ text: `${key}:  `, bold: true, size: 21, color: INK }),
      ...inlineRuns(value, { size: 21, color: INK }),
    ],
  })),
  new Paragraph({ children: [new PageBreak()] }),
];

const document = new Document({
  creator: "Tuqa Al-Ghazawi",
  title,
  description: "Capstone 2 PRD - Surgical Oncology Patient Flow Dashboard",
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [0, 1, 2].map((level) => ({
          level,
          format: LevelFormat.BULLET,
          text: ["•", "◦", "▪"][level],
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 340 + level * 320, hanging: 220 } } },
        })),
      },
      {
        reference: "numbers",
        levels: [{
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 340, hanging: 220 } } },
        }],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 21, color: INK } },
      heading1: { run: { font: "Calibri", size: 32, bold: true, color: TEAL } },
      heading2: { run: { font: "Calibri", size: 26, bold: true, color: TEAL } },
      heading3: { run: { font: "Calibri", size: 23, bold: true, color: INK } },
      heading4: { run: { font: "Calibri", size: 21, bold: true, color: MUTED } },
    },
  },
  sections: [{
    properties: {
      page: { size: PAGE, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } },
    },
    children: [...cover, ...parse(rest)],
  }],
});

Packer.toBuffer(document).then((buffer) => {
  fs.writeFileSync(OUT, buffer);
  console.log(`Wrote ${OUT} (${(buffer.length / 1024).toFixed(0)} KB)`);
});
