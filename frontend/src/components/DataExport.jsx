// Settings: "Download all my data" as one zip. A plain link, so the browser streams it straight to disk.
import { Download } from 'lucide-react'
import { t } from '../i18n'

export default function DataExport() {
  return (
    <section className="card" id="my-data" style={{ scrollMarginTop: 20 }}>
      <div className="card-head"><div><h2>{t('Your data')}</h2><div className="sub">{t('Everything FinVault keeps for you, in one zip file you can open anywhere.')}</div></div></div>
      <div className="card-body stack" style={{ gap: 14 }}>
        <ul className="export-list small">
          <li>{t('A JSON file for each kind of record: accounts, transactions, splits, shared costs, categories, rules, budgets, bills, goals, assets, registered plans, investments, imports and your settings.')}</li>
          <li>{t('Your transactions as a CSV file, the same as the Transactions export.')}</li>
          <li>{t('Your receipt files, and a README that explains the format.')}</li>
        </ul>
        <p className="small muted">{t('Only your own data is included. Your password, two-factor secrets and recovery codes, and saved API keys and bank-sync credentials are left out. The zip isn’t encrypted, so keep it somewhere safe.')}</p>
        <div><a className="btn" href="/api/account/export" download><Download />{t('Download all my data')}</a></div>
      </div>
    </section>
  )
}
