const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  LevelFormat,
  Packer,
  PageBreak,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableOfContents,
  TableRow,
  TextRun,
  WidthType,
} = require("docx");

const A4_WIDTH = 11906;
const A4_HEIGHT = 16838;
const PAGE_MARGIN = 1440;
const CONTENT_WIDTH = A4_WIDTH - PAGE_MARGIN * 2;

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
      continue;
    }
    args[key] = next;
    i += 1;
  }
  return args;
}

function readUtf8(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function readJson(filePath) {
  return JSON.parse(readUtf8(filePath));
}

function ensureDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item)).filter(Boolean).join("；");
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, val]) => `${key}: ${formatValue(val)}`)
      .join("；");
  }
  return String(value);
}

function buildRuns(text) {
  const content = text || "";
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  const runs = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      runs.push(new TextRun({ text: content.slice(lastIndex, match.index) }));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      runs.push(new TextRun({ text: token.slice(2, -2), bold: true }));
    } else if (token.startsWith("`")) {
      runs.push(new TextRun({ text: token.slice(1, -1), font: "Courier New" }));
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < content.length) {
    runs.push(new TextRun({ text: content.slice(lastIndex) }));
  }

  return runs.length > 0 ? runs : [new TextRun("")];
}

function headingLevel(level) {
  if (level === 1) {
    return HeadingLevel.HEADING_1;
  }
  if (level === 2) {
    return HeadingLevel.HEADING_2;
  }
  return HeadingLevel.HEADING_3;
}

function isTableSeparator(line) {
  return /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line);
}

function parsePipeRow(line) {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const raw = lines[index];
    const line = raw.trim();

    if (!line) {
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2],
      });
      index += 1;
      continue;
    }

    if (
      line.includes("|") &&
      index + 1 < lines.length &&
      isTableSeparator(lines[index + 1].trim())
    ) {
      const headers = parsePipeRow(line);
      const rows = [];
      index += 2;
      while (index < lines.length) {
        const tableLine = lines[index].trim();
        if (!tableLine || !tableLine.includes("|")) {
          break;
        }
        rows.push(parsePipeRow(tableLine));
        index += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    const bullet = /^\s*-\s+(.*)$/.exec(raw);
    if (bullet) {
      const items = [];
      while (index < lines.length) {
        const itemMatch = /^\s*-\s+(.*)$/.exec(lines[index]);
        if (!itemMatch) {
          break;
        }
        items.push(itemMatch[1].trim());
        index += 1;
      }
      blocks.push({ type: "bullet_list", items });
      continue;
    }

    const numbered = /^\s*\d+\.\s+(.*)$/.exec(raw);
    if (numbered) {
      const items = [];
      while (index < lines.length) {
        const itemMatch = /^\s*\d+\.\s+(.*)$/.exec(lines[index]);
        if (!itemMatch) {
          break;
        }
        items.push(itemMatch[1].trim());
        index += 1;
      }
      blocks.push({ type: "number_list", items });
      continue;
    }

    const parts = [];
    while (index < lines.length) {
      const current = lines[index].trim();
      if (!current) {
        break;
      }
      if (/^(#{1,3})\s+/.test(current)) {
        break;
      }
      if (/^\s*-\s+/.test(lines[index]) || /^\s*\d+\.\s+/.test(lines[index])) {
        break;
      }
      if (
        current.includes("|") &&
        index + 1 < lines.length &&
        isTableSeparator(lines[index + 1].trim())
      ) {
        break;
      }
      parts.push(current);
      index += 1;
    }
    blocks.push({ type: "paragraph", text: parts.join(" ") });
  }

  return blocks;
}

function createStyledTable(headers, rows) {
  const safeHeaders = headers.length > 0 ? headers : ["字段", "值"];
  const safeRows = rows.length > 0 ? rows : [["无数据"]];
  const colCount = safeHeaders.length;
  const baseWidth = Math.floor(CONTENT_WIDTH / colCount);
  const columnWidths = safeHeaders.map((_, idx) =>
    idx === colCount - 1 ? CONTENT_WIDTH - baseWidth * (colCount - 1) : baseWidth
  );

  const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

  const headerRow = new TableRow({
    children: safeHeaders.map((header, idx) =>
      new TableCell({
        borders,
        width: { size: columnWidths[idx], type: WidthType.DXA },
        shading: { fill: "D9EAF7", type: ShadingType.CLEAR },
        margins: cellMargins,
        children: [
          new Paragraph({
            children: [new TextRun({ text: header, bold: true })],
          }),
        ],
      })
    ),
  });

  const bodyRows = safeRows.map((row) =>
    new TableRow({
      children: safeHeaders.map((_, idx) =>
        new TableCell({
          borders,
          width: { size: columnWidths[idx], type: WidthType.DXA },
          margins: cellMargins,
          children: [
            new Paragraph({
              children: buildRuns(formatValue(row[idx] || "")),
            }),
          ],
        })
      ),
    })
  );

  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths,
    rows: [headerRow, ...bodyRows],
  });
}

function blocksToChildren(blocks) {
  const children = [];
  blocks.forEach((block) => {
    if (block.type === "heading") {
      children.push(
        new Paragraph({
          heading: headingLevel(block.level),
          children: buildRuns(block.text),
        })
      );
      return;
    }
    if (block.type === "paragraph") {
      children.push(
        new Paragraph({
          spacing: { after: 160 },
          children: buildRuns(block.text),
        })
      );
      return;
    }
    if (block.type === "bullet_list") {
      block.items.forEach((item) => {
        children.push(
          new Paragraph({
            numbering: { reference: "bullets", level: 0 },
            children: buildRuns(item),
          })
        );
      });
      return;
    }
    if (block.type === "number_list") {
      block.items.forEach((item) => {
        children.push(
          new Paragraph({
            numbering: { reference: "numbers", level: 0 },
            children: buildRuns(item),
          })
        );
      });
      return;
    }
    if (block.type === "table") {
      children.push(createStyledTable(block.headers, block.rows));
      return;
    }
  });
  return children;
}

function normalizePayload(payload) {
  const overview = payload["分析概览"] || payload.overview || {};
  const keyFindings = payload["核心发现"] || payload.key_findings || [];
  const featureRows = payload["特征有效性汇总"] || payload.feature_summary || [];
  const directSegments = payload["分群画像"] || payload.segment_profiles || [];
  const segmentRows = directSegments.length > 0
    ? directSegments
    : [
        ...(payload["分群画像_重点"] || []),
        ...(payload["分群画像_简略"] || []),
      ];

  return {
    overview,
    keyFindings,
    featureRows,
    segmentRows,
  };
}

function flattenOverview(overview) {
  const rows = [];
  Object.entries(overview || {}).forEach(([section, value]) => {
    if (Array.isArray(value)) {
      rows.push([section, formatValue(value)]);
      return;
    }
    if (value && typeof value === "object") {
      Object.entries(value).forEach(([key, val]) => {
        rows.push([`${section}-${key}`, formatValue(val)]);
      });
      return;
    }
    rows.push([section, formatValue(value)]);
  });
  return rows;
}

function pickColumns(records, preferredColumns, limit) {
  const subset = (records || []).slice(0, limit);
  const seen = new Set();
  const headers = [];

  preferredColumns.forEach((col) => {
    if (subset.some((row) => Object.prototype.hasOwnProperty.call(row, col))) {
      headers.push(col);
      seen.add(col);
    }
  });

  subset.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!seen.has(key)) {
        headers.push(key);
        seen.add(key);
      }
    });
  });

  const rows = subset.map((row) => headers.map((header) => formatValue(row[header])));
  return { headers, rows, total: records.length };
}

function buildAppendixChildren(data, appendixMode, maxFeatureRows, maxSegmentRows) {
  const children = [];
  const includeFeature = appendixMode === "both" || appendixMode === "feature";
  const includeSegment = appendixMode === "both" || appendixMode === "segment";

  children.push(
    new Paragraph({
      pageBreakBefore: true,
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun("附录：结构化分析摘要")],
    })
  );

  const overviewRows = flattenOverview(data.overview);
  if (overviewRows.length > 0) {
    children.push(
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("附录一：分析概览")],
      })
    );
    children.push(createStyledTable(["指标", "值"], overviewRows));
  }

  if (Array.isArray(data.keyFindings) && data.keyFindings.length > 0) {
    children.push(
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("附录二：核心发现")],
      })
    );
    data.keyFindings.forEach((item) => {
      children.push(
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: buildRuns(formatValue(item)),
        })
      );
    });
  }

  if (includeFeature && Array.isArray(data.featureRows) && data.featureRows.length > 0) {
    const featureTable = pickColumns(
      data.featureRows,
      [
        "特征名称",
        "特征类别",
        "特征类型",
        "全局IV",
        "IV预测力",
        "IV可信度",
        "跨分群一致性",
        "综合评级",
      ],
      maxFeatureRows
    );
    children.push(
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("附录三：特征有效性汇总")],
      })
    );
    children.push(
      new Paragraph({
        children: [
          new TextRun(
            `以下附录展示前 ${featureTable.rows.length} 行特征记录，共 ${featureTable.total} 行。`
          ),
        ],
      })
    );
    children.push(createStyledTable(featureTable.headers, featureTable.rows));
  }

  if (includeSegment && Array.isArray(data.segmentRows) && data.segmentRows.length > 0) {
    const segmentTable = pickColumns(
      data.segmentRows,
      [
        "分群维度",
        "分群名称",
        "样本数",
        "坏客户数",
        "坏客户率",
        "模型AUC",
        "AUC类型",
        "Top3预测特征_IV",
        "Top3风险特征_相关性",
        "风险特征概要",
      ],
      maxSegmentRows
    );
    children.push(
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun("附录四：分群画像")],
      })
    );
    children.push(
      new Paragraph({
        children: [
          new TextRun(
            `以下附录展示前 ${segmentTable.rows.length} 行分群记录，共 ${segmentTable.total} 行。`
          ),
        ],
      })
    );
    children.push(createStyledTable(segmentTable.headers, segmentTable.rows));
  }

  return children;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const llmJsonPath = args["llm-json"];
  const reportMarkdownPath = args["report-markdown"];
  const outputPath = args.output;
  const appendixMode = args["appendix-mode"] || "both";
  const maxFeatureRows = Number(args["max-feature-rows"] || "50");
  const maxSegmentRows = Number(args["max-segment-rows"] || "30");

  if (!llmJsonPath || !reportMarkdownPath || !outputPath) {
    throw new Error("缺少必要参数：--llm-json、--report-markdown、--output");
  }

  const payload = normalizePayload(readJson(llmJsonPath));
  const reportMarkdown = readUtf8(reportMarkdownPath);
  const reportBlocks = parseMarkdown(reportMarkdown);
  const reportChildren = blocksToChildren(reportBlocks);
  const title = args.title || path.basename(outputPath, ".docx");

  const children = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 2200, after: 400 },
      children: [new TextRun({ text: title, bold: true, size: 36 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [new TextRun({ text: "风险特征深度解读报告", size: 24 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: new Date().toISOString().slice(0, 10), size: 20 })],
    }),
    new Paragraph({ children: [new PageBreak()] }),
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun("目录")],
    }),
    new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" }),
    new Paragraph({ children: [new PageBreak()] }),
    ...reportChildren,
  ];

  if (appendixMode !== "none") {
    children.push(...buildAppendixChildren(payload, appendixMode, maxFeatureRows, maxSegmentRows));
  }

  const doc = new Document({
    styles: {
      default: {
        document: {
          run: {
            font: "Arial",
            size: 22,
          },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 32, bold: true, font: "Arial" },
          paragraph: { spacing: { before: 240, after: 180 }, outlineLevel: 0 },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 28, bold: true, font: "Arial" },
          paragraph: { spacing: { before: 200, after: 140 }, outlineLevel: 1 },
        },
        {
          id: "Heading3",
          name: "Heading 3",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 24, bold: true, font: "Arial" },
          paragraph: { spacing: { before: 160, after: 120 }, outlineLevel: 2 },
        },
      ],
    },
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "•",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 720, hanging: 360 } } },
            },
          ],
        },
        {
          reference: "numbers",
          levels: [
            {
              level: 0,
              format: LevelFormat.DECIMAL,
              text: "%1.",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 720, hanging: 360 } } },
            },
          ],
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: A4_WIDTH, height: A4_HEIGHT },
            margin: {
              top: PAGE_MARGIN,
              right: PAGE_MARGIN,
              bottom: PAGE_MARGIN,
              left: PAGE_MARGIN,
            },
          },
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                  new TextRun("第 "),
                  new TextRun({ children: [PageNumber.CURRENT] }),
                  new TextRun(" 页"),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });

  ensureDir(outputPath);
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`[OK] 已写出 docx: ${outputPath}`);
}

main().catch((error) => {
  console.error(`[ERROR] ${error.message}`);
  process.exit(1);
});
