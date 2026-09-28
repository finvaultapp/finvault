"""Parser tests using representative layouts of Canadian bank exports."""
from datetime import date
from decimal import Decimal

from app.importers import parse_file
from app.importers.common import detect_date_format, parse_amount


def p(name, text, **kw):
    return parse_file(name, text.encode("utf-8"), **kw)


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
