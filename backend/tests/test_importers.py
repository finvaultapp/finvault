"""Parser tests using representative layouts of Canadian bank exports."""
from datetime import date
from decimal import Decimal

from app.importers import parse_file
from app.importers.common import detect_date_format, parse_amount


def p(name, text, **kw):
    return parse_file(name, text.encode("utf-8"), **kw)


def minimal_pdf(text: str) -> bytes:
    entries = [(50, 750 - i * 16, line) for i, line in enumerate(text.splitlines())]
    return positioned_pdf(entries)


def positioned_pdf(entries: list[tuple[int, int, str]]) -> bytes:
    def pdf_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = "\n".join(
        f"BT /F1 12 Tf {x} {y} Td ({pdf_escape(line)}) Tj ET"
        for x, y, line in entries
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = content.encode("latin1")
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_parse_amount_variants():
    assert parse_amount("$1,234.56") == Decimal("1234.56")
    assert parse_amount("(12.00)") == Decimal("-12.00")
    assert parse_amount("12.00-") == Decimal("-12.00")
    assert parse_amount("-$5.25") == Decimal("-5.25")
    assert parse_amount("1 234,56") == Decimal("1234.56")
    assert parse_amount("45.10 DR") == Decimal("-45.10")
    assert parse_amount("") is None
    assert parse_amount("abc") is None


def test_date_format_ambiguity():
    fmt, amb = detect_date_format(["01/02/2026", "03/04/2026"])
    assert fmt == "%m/%d/%Y" and amb
    fmt, amb = detect_date_format(["25/02/2026", "03/04/2026"])
    assert fmt == "%d/%m/%Y" and not amb


OFX_SGML = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CAD<BANKACCTFROM><BANKID>0003<ACCTID>12345<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260101<DTEND>20260131
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260105120000[-5:EST]<TRNAMT>-54.23<FITID>90001<NAME>LOBLAWS #1234<MEMO>POS PURCHASE
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260115<TRNAMT>2500.00<FITID>90002<NAME>PAYROLL ACME
</BANKTRANLIST><LEDGERBAL><BALAMT>3120.55<DTASOF>20260131</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_ofx_sgml_without_closing_tags():
    r = p("statement.qfx", OFX_SGML)
    assert r.format == "ofx" and r.currency == "CAD"
    assert len(r.transactions) == 2
    t = r.transactions[0]
    assert t.date == date(2026, 1, 5) and t.amount == Decimal("-54.23") and t.external_id == "90001"
    assert "LOBLAWS" in t.description and "POS PURCHASE" in t.description
    assert r.statement_balance == Decimal("3120.55")


def test_pdf_statement_full_dates():
    raw = minimal_pdf(
        "Statement\n"
        "Date Description Withdrawals Deposits Balance\n"
        "01/03/2026 LOBLAWS #123 54.23 945.77\n"
        "01/15/2026 PAYROLL ACME 2500.00 3445.77\n"
    )
    r = parse_file("statement.pdf", raw)
    assert r.format == "pdf"
    assert [t.date for t in r.transactions] == [date(2026, 1, 3), date(2026, 1, 15)]
    assert [t.amount for t in r.transactions] == [Decimal("-54.23"), Decimal("2500.00")]
    assert r.transactions[0].description == "LOBLAWS #123"
    assert any("best-effort" in w for w in r.warnings)


def test_pdf_statement_short_month_dates_use_statement_year():
    raw = minimal_pdf(
        "Statement period Jan 1, 2026 to Jan 31, 2026\n"
        "Jan 03 Jan 04 SOBEYS 64.20\n"
        "Jan 20 Jan 20 PAYMENT THANK YOU 200.00\n"
    )
    r = parse_file("card.pdf", raw, account_type="credit_card")
    assert [t.date for t in r.transactions] == [date(2026, 1, 3), date(2026, 1, 20)]
    assert [t.amount for t in r.transactions] == [Decimal("-64.20"), Decimal("200.00")]
    assert r.transactions[0].description == "SOBEYS"


def test_rbc_csv_with_usd_column():
    text = ('"Account Type","Account Number","Transaction Date","Cheque Number","Description 1","Description 2","CAD$","USD$"\n'
            'Chequing,01234-5678901,1/15/2026,,"TIM HORTONS #0412","",-3.45,\n'
            'Chequing,01234-5678901,1/16/2026,,"AMAZON.COM","SEATTLE",,-20.00\n')
    r = p("rbc.csv", text)
    assert r.preset == "rbc"
    assert [t.amount for t in r.transactions] == [Decimal("-3.45"), Decimal("-20.00")]
    assert r.transactions[1].currency == "USD"
    assert r.transactions[1].description == "AMAZON.COM SEATTLE"


def test_td_headerless():
    text = "01/03/2026,SHOPPERS DRUG MART,23.10,,1500.00\n01/04/2026,E-TRANSFER FROM JANE,,200.00,1700.00\n01/20/2026,HYDRO ONE,89.90,,1610.10\n"
    r = p("accountactivity.csv", text)
    assert r.mapping["date"] == 0 and r.mapping["debit"] == 2 and r.mapping["credit"] == 3
    assert [t.amount for t in r.transactions] == [Decimal("-23.10"), Decimal("200.00"), Decimal("-89.90")]


def test_cibc_headerless_iso_dates():
    text = "2026-02-01,COSTCO WHOLESALE,152.34,,4500********1234\n2026-02-03,PAYMENT THANK YOU,,500.00,4500********1234\n"
    r = p("cibc.csv", text, preset_id="cibc")
    assert r.transactions[0].amount == Decimal("-152.34")
    assert r.transactions[1].amount == Decimal("500.00")


def test_bmo_with_preamble():
    text = ("Following data is valid as of 20260210120000 (Year/Month/Day/Hour/Minute/Second)\n\n\n"
            "First Bank Card,Transaction Type,Date Posted, Transaction Amount,Description\n"
            "'5191230000000000',DEBIT,20260201,-45.00,[DN]METRO 123 TORONTO\n"
            "'5191230000000000',CREDIT,20260202,1200.00,[DD]PAYROLL\n")
    r = p("bmo.csv", text)
    assert r.preset == "bmo"
    assert r.transactions[0].date == date(2026, 2, 1)
    assert [t.amount for t in r.transactions] == [Decimal("-45.00"), Decimal("1200.00")]


def test_tangerine():
    text = ("Date,Transaction,Name,Memo,Amount\n"
            "2/5/2026,DEBIT,INTERAC e-Transfer To: RENT,,-1500.00\n"
            "2/6/2026,OTHER,Interest Paid,,1.23\n")
    r = p("tangerine.csv", text)
    assert r.preset == "tangerine"
    assert r.transactions[0].description.startswith("INTERAC")


def test_simplii_funds_in_out():
    text = "Date,Transaction Details,Funds Out,Funds In\n03/01/2026,BELL CANADA,85.00,\n03/02/2026,DEPOSIT,,300.00\n"
    r = p("simplii.csv", text)
    assert r.preset == "simplii"
    assert [t.amount for t in r.transactions] == [Decimal("-85.00"), Decimal("300.00")]


def test_rogers_card_inverted():
    text = ('"Date","Posted Date","Reference Number","Activity Type","Status","Card Number","Merchant Category Description",'
            '"Merchant Name","Merchant City","Merchant State/Province","Merchant Country Code","Merchant Postal Code/Zip","Amount","Rewards","Name on Card"\n'
            '"2026-03-01","2026-03-02","123","TRANS","APPROVED","************1234","Grocery Stores","SOBEYS","HALIFAX","NS","CAN","B3H","$64.20","0.96","J DOE"\n'
            '"2026-03-05","2026-03-05","124","PAYMENT","APPROVED","************1234","","PAYMENT","","","","","-$200.00","",""\n')
    r = p("rogers.csv", text)
    assert r.preset == "rogers" and r.inverted
    assert r.transactions[0].amount == Decimal("-64.20")
    assert r.transactions[1].amount == Decimal("200.00")
    assert r.transactions[0].bank_category == "Grocery Stores"


def test_credit_card_heuristic_flips_positive_purchases():
    text = "Transaction Date,Description,Amount\n2026-04-01,NETFLIX.COM,16.99\n2026-04-02,UBER EATS,32.10\n2026-04-03,SHELL,55.00\n"
    r = p("card.csv", text, account_type="credit_card")
    assert r.inverted
    assert all(t.amount < 0 for t in r.transactions)


def test_type_column_sets_sign_when_all_positive():
    text = "Date,Description,Type of Transaction,Amount,Balance\n2026-05-01,GROCERY,Debit,40.00,960.00\n2026-05-02,PAY,Credit,1000.00,1960.00\n"
    r = p("scotia.csv", text)
    assert [t.amount for t in r.transactions] == [Decimal("-40.00"), Decimal("1000.00")]


def test_french_semicolon_export():
    text = "Date;Description;Débit;Crédit;Solde\n2026-06-01;IGA MONTREAL;45,10;;1000,00\n2026-06-02;DEPOT PAIE;;1 250,00;2250,00\n"
    r = p("banque.csv", text)
    assert [t.amount for t in r.transactions] == [Decimal("-45.10"), Decimal("1250.00")]


def test_qif():
    text = "!Type:Bank\nD01/15/2026\nT-12.50\nPSTARBUCKS\n^\nD01/16/2026\nT100.00\nPREFUND\n^\n"
    r = p("export.qif", text)
    assert r.format == "qif" and len(r.transactions) == 2
    assert r.transactions[0].amount == Decimal("-12.50")


def test_manual_mapping_override():
    text = "Col A,Col B,Col C\nfoo,2026-01-01,-5.00\nbar,2026-01-02,7.00\n"
    r = p("x.csv", text, mapping={"description": 0, "date": 1, "amount": 2})
    assert [t.description for t in r.transactions] == ["foo", "bar"]


def test_td_with_all_empty_credit_column():
    text = "09/10/2026,RBC VISA PAYMENT,500.00,,1000.00\n09/12/2026,LOBLAWS,80.00,,920.00\n"
    r = p("td.csv", text)
    assert [t.amount for t in r.transactions] == [Decimal("-500.00"), Decimal("-80.00")]


def test_td_with_all_empty_debit_column():
    text = "09/10/2026,PAYROLL,,2500.00,3500.00\n09/24/2026,PAYROLL,,2500.00,6000.00\n"
    r = p("td.csv", text)
    assert [t.amount for t in r.transactions] == [Decimal("2500.00"), Decimal("2500.00")]


def word_by_word_pdf(lines: list[str]) -> bytes:
    """Like some card issuers' PDFs: every word is its own text object on the same baseline."""
    entries = []
    for row, line in enumerate(lines):
        x = 40
        for word in line.split(" "):
            entries.append((x, 760 - row * 18, word))
            x += 7 * len(word) + 8
    return positioned_pdf(entries)


CARD_HEADER = [
    "Statement Period Aug 22, 2026 - Sep 21, 2026",
    "Payment due date Oct 13, 2026 Payments & credits $6.28",
    "Credit limit $5,000.00 New purchases & debits $131.87",
    "Minimum payment $10.00 Available credit $4,868.13",
    "Trans Post Description Amount",
]


def test_pdf_card_statement_word_by_word_layout():
    raw = word_by_word_pdf(CARD_HEADER + [
        "Sep 3 Sep 4 ROGERS 1283 TORONTO ON 48.25",
        "Sep 10 Sep 11 ROGERS 5706 TORONTO ON 56.50",
        "Sep 11 Sep 11 AUTO PAYMENT-THANK-YOU -6.28",
        "Sep 14 Sep 15 FIDO MOBILE 6769 TORONTO ON 27.12",
    ])
    r = parse_file("card.pdf", raw)  # no account type given: the card cues decide the sign convention
    got = [(t.date, t.amount) for t in r.transactions]
    assert got == [(date(2026, 9, 3), Decimal("-48.25")), (date(2026, 9, 10), Decimal("-56.50")),
                   (date(2026, 9, 11), Decimal("6.28")), (date(2026, 9, 14), Decimal("-27.12"))]
    assert not any("Payments" in t.description for t in r.transactions)  # summary line is not a transaction
    assert any("match the statement" in w for w in r.warnings)


def test_pdf_card_statement_across_new_year():
    raw = word_by_word_pdf([
        "Statement Period Dec 22, 2026 - Jan 21, 2027",
        "Credit limit $5,000.00 New purchases & debits $30.00",
        "Dec 28 Dec 29 COFFEE SHOP 10.00",
        "Jan 3 Jan 4 BOOK STORE 20.00",
    ])
    r = parse_file("card.pdf", raw, account_type="credit_card")
    assert [t.date for t in r.transactions] == [date(2026, 12, 28), date(2027, 1, 3)]


def test_pdf_card_statement_totals_mismatch_is_flagged():
    raw = word_by_word_pdf([
        "Statement Period Aug 22, 2026 - Sep 21, 2026",
        "Credit limit $5,000.00 New purchases & debits $99.00",
        "Sep 3 Sep 4 GROCER 48.25",
    ])
    r = parse_file("card.pdf", raw)
    assert any("add up to 48.25" in w for w in r.warnings)
