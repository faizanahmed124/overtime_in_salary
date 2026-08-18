frappe.query_reports["Salary Summary"] = {
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
            fieldname: "branch",
            label:     __("Branch"),
            fieldtype: "Link",
            options:   "Branch",
        },
        {
            fieldname: "employment_type",
            label:     __("Employment Type"),
            fieldtype: "Link",
            options:   "Employment Type",
        },
        {
            fieldname: "mode_of_payment",
            label:     __("Mode of Payment"),
            fieldtype: "Link",
            options:   "Mode of Payment",
        },
    ],

    onload: function (report) {
        report.page.add_inner_button(__("🖨️ Print Report"), function () {
            let filters = report.get_values();
            let data    = report.data;
            let columns = report.columns;   // ← actual columns from Python (all components)

            if (!data || data.length === 0) {
                frappe.msgprint("No data to print. Please load the report first.");
                return;
            }

            // ── Helpers ──────────────────────────────────────────
            function strip(str) {
                return (str || "").replace(/<[^>]+>/g, "").trim();
            }

            function fmt(val) {
                let n = parseFloat(val);
                if (!n) return "—";
                return "Rs\u00a0" + n.toLocaleString("en-PK", {
                    minimumFractionDigits: 0, maximumFractionDigits: 0,
                });
            }

            function fmtInt(val) {
                return (val || 0);
            }

            // ── Build thead from actual report columns ────────────
            let thead_html = columns.map(function (c) {
                let isNum = ["Currency", "Float", "Int"].indexOf(c.fieldtype) !== -1;
                let align = isNum ? ' class="right"' : '';
                return `<th${align}>${c.label}</th>`;
            }).join("");

            // ── Build tbody ───────────────────────────────────────
            let rows_html = "";

            data.forEach(function (row, idx) {
                let dept    = row.department || "";
                let isGrand = dept.indexOf("Grand Total") !== -1;

                let cells = columns.map(function (c) {
                    let val  = row[c.fieldname];
                    let text = "";

                    if (c.fieldname === "department") {
                        text = `<span class="dept-cell">${strip(dept)}</span>`;
                    } else if (c.fieldtype === "Int") {
                        text = fmtInt(val);
                    } else if (c.fieldtype === "Currency" || c.fieldtype === "Float") {
                        text = fmt(val);
                    } else {
                        text = val || "—";
                    }

                    let isNum = ["Currency", "Float", "Int"].indexOf(c.fieldtype) !== -1;
                    let cls   = isNum ? "right" : "left";

                    if (c.fieldname === "net_salary" && !isGrand) cls += " net-col";
                    if (c.fieldname === "net_salary" &&  isGrand) cls  = "right golden";
                    if (c.fieldname === "gross_salary")           cls += " gross-col";

                    return `<td class="${cls}">${text}</td>`;
                }).join("");

                let trClass = isGrand ? "grand-total-row"
                            : (idx % 2 === 0 ? "even" : "odd");
                rows_html += `<tr class="${trClass}">${cells}</tr>`;
            });

            // ── Meta ─────────────────────────────────────────────
            let company         = filters.company         || "";
            let from_date       = filters.from_date       || "";
            let to_date         = filters.to_date         || "";
            let branch          = filters.branch          || "All Branches";
            let mode_of_payment = filters.mode_of_payment || "All";
            let dept_filter     = filters.department      || "All Departments";
            let print_dt        = frappe.datetime.now_datetime();

            let html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Salary Summary — ${company}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

        @page { size: landscape; margin: 15mm 12mm; }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'DM Sans', sans-serif;
            background: #fff;
            color: #1a1a2e;
            padding: 28px 36px;
            font-size: 10px;
        }

        /* ── HEADER ── */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 3px solid #1a1a2e;
            padding-bottom: 14px;
            margin-bottom: 18px;
        }

        .company-name {
            font-family: 'Playfair Display', serif;
            font-size: 22px;
            font-weight: 900;
            color: #1a1a2e;
        }

        .report-title {
            font-size: 10px;
            font-weight: 500;
            color: #666;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-top: 4px;
        }

        .header-right { text-align: right; }

        .badge {
            display: inline-block;
            background: #1a1a2e;
            color: #fff;
            font-size: 8px;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            padding: 3px 12px;
            border-radius: 20px;
            margin-bottom: 8px;
        }

        .meta-grid {
            display: grid;
            grid-template-columns: auto auto;
            gap: 2px 12px;
        }

        .meta-label { font-size: 8px;  color: #999; text-transform: uppercase; letter-spacing: 1px; text-align: right; }
        .meta-value { font-size: 10px; font-weight: 600; color: #1a1a2e; text-align: right; }

        .accent-bar {
            height: 3px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90d9 50%, #e8c84a 100%);
            border-radius: 2px;
            margin-bottom: 18px;
        }

        /* ── TABLE ── */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 9.5px;
            table-layout: auto;
        }

        thead tr {
            background: #fff;
            color: #000;
            border-bottom: 2px solid #000;
        }

        thead th {
            padding: 8px 7px;
            font-size: 8px;
            font-weight: 900;
            color: #000;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            white-space: nowrap;
            border-right: 1px solid #ddd;
        }

        thead th.right { text-align: right; }

        /* Separator between earnings / deductions */
        thead th.sep-earn { border-left: 3px solid #5E81F4; }
        thead th.sep-ded  { border-left: 3px solid #F45E7A; }
        thead th.sep-net  { border-left: 3px solid #e8c84a; }

        tbody tr.even { background: #f8f9fc; }
        tbody tr.odd  { background: #ffffff; }

        tbody td {
            padding: 6px 7px;
            border-bottom: 1px solid #eef0f5;
            border-right: 1px solid #f0f0f0;
            white-space: nowrap;
        }

        td.left     { text-align: left; font-weight: 700; color: #1a1a2e; }
        td.right    { text-align: right; }
        td.net-col  { font-weight: 700; color: #1a5276; }
        td.gross-col{ font-weight: 600; color: #1a5276; }

        span.dept-cell { font-weight: 700; }

        /* Grand total row */
        tr.grand-total-row td {
            background: #fff !important;
            color: #000 !important;
            font-weight: 900;
            font-size: 10px;
            padding: 8px 7px;
            border-top: 2px solid #000;
            border-bottom: 2px solid #000;
        }

        tr.grand-total-row td.golden {
            color: #000 !important;
            font-weight: 900;
            font-size: 11px;
        }

        /* ── FOOTER ── */
        .footer {
            margin-top: 28px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-top: 1px solid #ddd;
            padding-top: 12px;
        }

        .note { font-size: 8px; color: #aaa; line-height: 1.8; }

        .signatures { display: flex; gap: 48px; }
        .sig-block  { text-align: center; }
        .sig-line   { width: 120px; border-top: 1.5px solid #1a1a2e; margin-bottom: 5px; }
        .sig-label  { font-size: 8px; color: #666; letter-spacing: 1px; text-transform: uppercase; }

        @media print {
            body  { padding: 0; }
            thead { display: table-header-group; }
        }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <div class="company-name">${company}</div>
            <div class="report-title">Department Wise Salary Summary — All Earnings &amp; Deductions</div>
        </div>
        <div class="header-right">
            <div class="badge">Payroll Report</div>
            <div class="meta-grid">
                <span class="meta-label">Period</span>
                <span class="meta-value">${from_date} → ${to_date}</span>
                <span class="meta-label">Branch</span>
                <span class="meta-value">${branch}</span>
                <span class="meta-label">Mode</span>
                <span class="meta-value">${mode_of_payment}</span>
                <span class="meta-label">Department</span>
                <span class="meta-value">${dept_filter}</span>
                <span class="meta-label">Printed</span>
                <span class="meta-value">${print_dt}</span>
            </div>
        </div>
    </div>

    <div class="accent-bar"></div>

    <table>
        <thead><tr>${thead_html}</tr></thead>
        <tbody>${rows_html}</tbody>
    </table>

    <div class="footer">
        <div class="note">
            Generated: ${print_dt} &nbsp;|&nbsp; All amounts in PKR<br>
            Confidential — Internal Use Only
        </div>
        <div class="signatures">
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Prepared By</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Accounts</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Audit</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">General Manager</div></div>
        </div>
    </div>

</body>
</html>`;

            let w = window.open("", "_blank", "width=1400,height=800");
            w.document.write(html);
            w.document.close();
            w.focus();
            setTimeout(function () { w.print(); }, 800);
        });
    },
};