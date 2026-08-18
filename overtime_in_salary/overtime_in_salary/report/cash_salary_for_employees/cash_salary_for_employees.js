frappe.query_reports["Cash Salary For Employees"] = {

    filters: [
        {
            fieldname: "company",
            label:     __("Company"),
            fieldtype: "Link",
            options:   "Company",
            default:   frappe.defaults.get_default("company"),
            reqd:      1,
        },
        {
            fieldname: "from_date",
            label:     __("From Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_start(),
            reqd:      1,
        },
        {
            fieldname: "to_date",
            label:     __("To Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_end(),
            reqd:      1,
        },
        {
            fieldname: "employment_type",
            label:     __("Employment Type"),
            fieldtype: "Link",
            options:   "Employment Type",
        },
    ],

    // ─────────────────────────────────────────────────────────────
    onload: function (report) {

        // ── Print Salary Slips ────────────────────────────────────
        report.page.add_inner_button(__("🖨️ Print Salary Slips"), function () {
            let filters  = report.get_values();
            let data     = report.data;

            if (!data || data.length === 0) {
                frappe.msgprint("No data to print. Please load the report first.");
                return;
            }

            // Employee rows only (skip grand total)
            let employees = data.filter(r => r.employee && !r._is_total);

            if (!employees.length) {
                frappe.msgprint("No employee records found.");
                return;
            }

            let company   = filters.company   || frappe.defaults.get_default("company") || "";
            let from_date = filters.from_date || "";
            let to_date   = filters.to_date   || "";
            let period    = _monthLabel(from_date);
            let print_dt  = frappe.datetime.now_datetime();

            // ── Currency formatter ────────────────────────────────
            function fmtPKR(val) {
                let n = parseFloat(val || 0);
                if (!n) return "0";
                return n.toLocaleString("en-PK", {
                    minimumFractionDigits: 0, maximumFractionDigits: 0
                });
            }

            // ── Build portrait-centered slip ──────────────────────
            function buildSlip(emp) {
                let ded = {};
                try { ded = JSON.parse(emp._ded || "{}"); } catch(e) {}

                let eobiAmt = 0;
                Object.entries(ded).forEach(([k, v]) => {
                    if (k.toLowerCase().indexOf("eobi") !== -1) eobiAmt = v;
                });

                let net = fmtPKR(emp.net_salary);

                return `
                <div class="slip">
                    <div class="s-id">${emp.employee || ""}</div>
                    <div class="s-name">${emp.employee_name || "—"}</div>
                    <div class="s-dept">${emp.department || ""}</div>
                    <div class="s-divider"></div>
                    ${eobiAmt ? `
                    <div class="s-row">
                        <span class="s-lbl">EOBI</span>
                        <span class="s-val">${fmtPKR(eobiAmt)}</span>
                    </div>` : ""}
                    <div class="s-net">
                        <span class="s-net-lbl">PAID SALARY</span>
                        <span class="s-net-val">Rs ${net}</span>
                    </div>
                </div>`;
            }

            // ── Arrange slips in rows of 3 ────────────────────────
            let COLS = 4;
            let slipGroups = "";
            for (let i = 0; i < employees.length; i += COLS) {
                let group = employees.slice(i, i + COLS);
                let cards = group.map(buildSlip).join("");
                // Pad last row if needed
                while (group.length < COLS) {
                    cards += `<div class="slip slip-empty"></div>`;
                    group.push({});
                }
                slipGroups += `<div class="slip-row">${cards}</div>`;
            }

            // ── Full print HTML ───────────────────────────────────
            let html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Cash Salary Slips — ${company} — ${period}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

        @page {
            size: A4 portrait;
            size: 210mm 297mm;
            margin: 6mm 5mm;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'DM Sans', sans-serif;
            background: #fff;
            font-size: 8pt;
            color: #111;
        }

        /* 4 slips per row — portrait */
        .slip-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0;
            page-break-inside: avoid;
        }

        /* Individual slip */
        .slip {
            border: 1px dashed #999;
            padding: 3mm 2.5mm 2.5mm;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 0.8mm;
            position: relative;
        }

        .slip-empty { border-color: transparent; }

        /* Scissor mark */
        .slip:not(:last-child)::after {
            content: "✂";
            position: absolute;
            right: -5px; top: 50%;
            transform: translateY(-50%);
            font-size: 7pt; color: #ccc;
            background: #fff;
        }

        /* Employee ID — top center, biggest, bold */
        .s-id {
            font-size: 9pt;
            font-weight: 900;
            color: #111;
            letter-spacing: 0.5px;
            line-height: 1.2;
        }

        /* Employee Name */
        .s-name {
            font-size: 7.5pt;
            font-weight: 800;
            color: #222;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            width: 100%;
            text-align: center;
            line-height: 1.3;
        }

        /* Department */
        .s-dept {
            font-size: 6pt;
            font-weight: 600;
            color: #666;
            line-height: 1.2;
        }

        /* Divider */
        .s-divider {
            width: 80%;
            border-top: 0.8px solid #ccc;
            margin: 1mm 0 0.5mm;
        }

        /* EOBI row */
        .s-row {
            display: flex;
            justify-content: space-between;
            width: 100%;
            padding: 0 1mm;
        }

        .s-lbl {
            font-size: 6.5pt;
            font-weight: 700;
            color: #c0392b;
        }

        .s-val {
            font-size: 6.5pt;
            font-weight: 700;
            color: #c0392b;
        }

        /* Net Pay bar */
        .s-net {
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #fff;
            color: #000;
            border: 1.5px solid #000;
            padding: 1.5mm 2mm;
            border-radius: 1.5px;
            margin-top: 1mm;
        }

        .s-net-lbl {
            font-size: 5.5pt;
            font-weight: 900;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #000;
        }

        .s-net-val {
            font-size: 9pt;
            font-weight: 900;
            color: #000;
        }

        @media print { body { padding: 0; } }
    </style>
</head>
<body>
    ${slipGroups}
</body>
</html>`;

            let w = window.open("", "_blank", "width=720,height=980");
            w.document.write(html);
            w.document.close();
            w.focus();
            setTimeout(function () { w.print(); }, 800);
        });

        // ── Full Sheet Summary Print ──────────────────────────────
        report.page.add_inner_button(__("📄 Print Summary"), function () {
            let filters  = report.get_values();
            let data     = report.data;
            let columns  = report.columns;

            if (!data || data.length === 0) {
                frappe.msgprint("No data to print.");
                return;
            }

            let company   = filters.company   || "";
            let from_date = filters.from_date || "";
            let to_date   = filters.to_date   || "";
            let print_dt  = frappe.datetime.now_datetime();

            function fmt(val) {
                let n = parseFloat(val || 0);
                if (!n) return "—";
                return "Rs\u00a0" + n.toLocaleString("en-PK", {
                    minimumFractionDigits: 0, maximumFractionDigits: 0
                });
            }

            let thead = columns.map(c => {
                let isNum = ["Currency","Float","Int"].indexOf(c.fieldtype) !== -1;
                return `<th${isNum ? ' class="r"' : ''}>${c.label}</th>`;
            }).join("");

            let tbody = data.map(function(row, idx) {
                let isGrand = row._is_total;
                let cells = columns.map(c => {
                    let v    = row[c.fieldname];
                    let text = "";
                    if (c.fieldname === "employee_name")
                        text = (v || "").replace(/<[^>]+>/g, "");
                    else if (c.fieldtype === "Currency") text = fmt(v);
                    else if (c.fieldtype === "Int")      text = (v || 0);
                    else text = v || "—";

                    let isNum = ["Currency","Float","Int"].indexOf(c.fieldtype) !== -1;
                    let cls   = isNum ? "r" : "";
                    if (c.fieldname === "net_salary" && isGrand) cls = "r gold";
                    return `<td class="${cls}">${text}</td>`;
                }).join("");

                return `<tr class="${isGrand ? "grand" : (idx%2===0?"e":"o")}">${cells}</tr>`;
            }).join("");

            let html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@page { size:A4 landscape; margin:12mm; }
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'DM Sans',sans-serif;font-size:9pt;color:#111;}
h1{font-size:16pt;font-weight:900;margin-bottom:2mm;}
.sub{font-size:8pt;color:#666;margin-bottom:5mm;}
table{width:100%;border-collapse:collapse;font-size:8pt;}
thead tr{background:#fff;color:#000;border-bottom:2px solid #000;}
thead th{padding:6px 7px;font-size:7.5pt;font-weight:900;color:#000;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap;}
th.r,td.r{text-align:right;}
tr.e{background:#f8f9fc;}tr.o{background:#fff;}
td{padding:5px 7px;border-bottom:1px solid #eee;}
tr.grand td{background:#111!important;color:#fff!important;font-weight:700;padding:7px;}
td.gold{color:#e8c84a!important;font-size:10pt;}
@media print{thead{display:table-header-group;}}
</style></head><body>
<h1>${company}</h1>
<div class="sub">Cash Salary — ${from_date} to ${to_date} &nbsp;|&nbsp; Printed: ${print_dt}</div>
<table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table>
</body></html>`;

            let w = window.open("", "_blank", "width=1200,height=800");
            w.document.write(html);
            w.document.close();
            w.focus();
            setTimeout(() => w.print(), 800);
        });
    },
};

// ── Helper: "July 2026" from a date string ──────────────────────
function _monthLabel(dateStr) {
    if (!dateStr) return "";
    try {
        let d = new Date(dateStr);
        return d.toLocaleDateString("en-PK", { month: "long", year: "numeric" });
    } catch(e) { return dateStr; }
}